from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Hashable, Iterable, MutableMapping, Sized
from dataclasses import dataclass
from functools import partial, wraps
from typing import Any, TypedDict, cast, overload

from dynamo.typedefs import MISSING, CoroFunction

log = logging.getLogger(__name__)

FAST_TYPES: set[type] = {int, str, float, bytes, type(None)}


@dataclass(slots=True)
class CacheInfo:
    """Cache info for the async_cache decorator."""

    hits: int = 0
    misses: int = 0
    currsize: int = 0
    full: bool = False

    def clear(self) -> None:
        """Reset all counters to zero."""
        self.hits = self.misses = self.currsize = 0
        self.full = False


type WrappedCoro[**P, T] = Callable[P, CoroFunction[P, T]]


class CacheParameters(TypedDict):
    maxsize: int | None
    ttl: float | None


class CachedTask[**P, T]:
    __wrapped__: Callable[P, CoroFunction[P, T]]
    __call__: Callable[P, asyncio.Task[T]]

    cache_info: Callable[[], CacheInfo]
    cache_clear: CoroFunction[[], None]
    cache_parameters: Callable[[], CacheParameters]
    invalidate: CoroFunction[P, bool]
    get_containing: CoroFunction[P, T | None]


class HashedSeq[T](list[T]):
    __slots__ = ("_hash_value",)

    def __init__(self, iterable: Iterable[T], hash_function: Callable[[object], int] = hash) -> None:
        super().__init__(iterable)
        # Compute hash once and store it to avoid recomputation
        self._hash_value = hash_function(tuple(self))

    def __hash__(self) -> int:  # type: ignore
        return self._hash_value


class Node:
    __slots__ = ("key", "value", "prev_node", "next_node", "children", "is_end")

    def __init__(self, key: Any = None, value: Any = None) -> None:
        self.key: Any = key
        self.value: Any = value
        self.prev_node: Node | None = None
        self.next_node: Node | None = None
        self.children: MutableMapping[str, Node] = {}
        self.is_end: bool = False


class LRU[K, V]:
    __slots__ = ("cache", "maxsize", "head", "tail")

    def __init__(self, maxsize: int | None, /) -> None:
        self.cache: MutableMapping[K, Node] = {}
        self.maxsize = maxsize
        self.head: Node | None = None
        self.tail: Node | None = None

    def get[T](self, key: K, default: T = MISSING, /) -> V | T:
        """Retrieve item from cache and move it to the front. Return default if not found."""
        node = self.cache.get(key)
        if node is None:
            return default
        self._move_to_front(node)
        return node.value

    def __getitem__(self, key: K) -> V:
        """Retrieve item from cache and move it to the front. Raises KeyError if not found."""
        result = self.get(key, MISSING)
        if result is MISSING:
            raise KeyError(key)
        return result

    def __setitem__(self, key: K, value: V) -> None:
        """Add or update item in cache and move it to the front."""
        if key in self.cache:
            node = self.cache[key]
            node.value = value
            self._move_to_front(node)
        else:
            node = Node(key, value)
            self.cache[key] = node
            self._add_to_front(node)
            if self.maxsize is not None and len(self.cache) > self.maxsize:
                self._remove_tail()

    def remove(self, key: K) -> None:
        """Remove item from cache."""
        node = self.cache.pop(key, None)
        if node:
            self._remove_node(node)

    def _add_to_front(self, node: Node) -> None:
        """Add node to the front of the linked list."""
        node.next_node = self.head
        node.prev_node = None
        if self.head:
            self.head.prev_node = node
        self.head = node
        if self.tail is None:
            self.tail = node

    def _remove_node(self, node: Node) -> None:
        """Remove node from the linked list."""
        if node.prev_node:
            node.prev_node.next_node = node.next_node
        else:
            self.head = node.next_node
        if node.next_node:
            node.next_node.prev_node = node.prev_node
        else:
            self.tail = node.prev_node

    def _move_to_front(self, node: Node) -> None:
        """Move node to the front of the linked list."""
        if self.head != node:
            self._remove_node(node)
            self._add_to_front(node)

    def _remove_tail(self) -> None:
        """Remove the tail node from the linked list."""
        if self.tail:
            self._remove_node(self.tail)
            del self.cache[self.tail.key]


class Trie:
    """Trie data structure for prefix-based searches."""

    __slots__ = ("root",)

    def __init__(self) -> None:
        self.root: Node = Node()

    def insert(self, word: str) -> None:
        node = self.root
        for char in word:
            if char not in node.children:
                node.children[char] = Node()
            node = node.children[char]
        node.is_end = True

    def search(self, prefix: str) -> list[str]:
        node = self.root
        results: list[str] = []

        for char in prefix:
            if char not in node.children:
                return results
            node = node.children[char]

        self._dfs(node, prefix, results)
        return results

    def _dfs(self, node: Node, current: str, results: list[str]) -> None:
        if node.is_end:
            results.append(current)
        for char, child in node.children.items():
            self._dfs(child, current + char, results)


def _finalize_key(
    key: tuple[Any, ...], fast_types: set[type], _type: type[type] = type, _len: Callable[[Sized], int] = len
) -> Hashable:
    return key[0] if _len(key) == 1 and _type(key[0]) in fast_types else HashedSeq(key)


def _make_key(
    args: tuple[Any, ...],
    kwargs: dict[Any, Any],
    kwargs_mark: tuple[object] = (object(),),
    fast_types: set[type] = FAST_TYPES,
) -> Hashable:
    """
    Make cache key from optionally typed positional and keyword arguments. Structure is flat and hashable.
    Treats `f(x=1, y=2)` and `f(y=2, x=1)` as the same call for caching purposes.
    """
    key = args
    if kwargs:
        sorted_items = tuple(sorted(kwargs.items()))
        key += kwargs_mark + sorted_items
    return _finalize_key(key, fast_types)


def _cache_wrapper[**P, T](coro: CoroFunction[P, T], maxsize: int | None, ttl: float | None) -> CachedTask[P, T]:
    sentinel = MISSING
    make_key = _make_key

    internal_cache: LRU[Hashable, asyncio.Future[T]] = LRU(maxsize)
    lock = asyncio.Lock()
    _cache_info = CacheInfo()

    @wraps(coro)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        key: Hashable = make_key(args, kwargs)

        async with lock:
            maybe_future = internal_cache.get(key, sentinel)
            if maybe_future is not sentinel:
                _cache_info.hits += 1
                return await maybe_future

            _cache_info.misses += 1
            future: asyncio.Future[T] = asyncio.get_running_loop().create_future()
            internal_cache[key] = future
            _cache_info.currsize = len(internal_cache.cache)
            _cache_info.full = maxsize is not None and _cache_info.currsize >= (internal_cache.maxsize or 0)

        if ttl is not None:

            def evict(k: Hashable, default: Any = MISSING) -> None:
                async def remove_key() -> None:
                    async with lock:
                        internal_cache.remove(k)

                _ = asyncio.create_task(remove_key())  # noqa: RUF006

            call_after_ttl = partial(asyncio.get_running_loop().call_later, ttl, evict, key)
            future.add_done_callback(call_after_ttl)

        try:
            result = await coro(*args, **kwargs)
            future.set_result(result)
        except Exception as e:
            log.exception("Error in coroutine %s with args %s and kwargs %s", coro, args, kwargs)
            future.set_exception(e)
            raise e from None
        return result

    def cache_info() -> CacheInfo:
        return _cache_info

    async def cache_clear() -> None:
        async with lock:
            internal_cache.cache.clear()
        _cache_info.clear()

    async def invalidate(*args: P.args, **kwargs: P.kwargs) -> bool:
        key = make_key(args, kwargs)
        log.debug("Invalidating cache for %s", key)
        async with lock:
            if removed := (key in internal_cache.cache):
                internal_cache.remove(key)
        return removed

    async def get_containing(*args: P.args, **kwargs: P.kwargs) -> T | None:
        key = make_key(args, kwargs)
        async with lock:
            future = internal_cache.get(key, sentinel)
        return await future if future is not sentinel else None

    _wrapper = cast(CachedTask[P, T], wrapper)
    _wrapper.cache_info = cache_info
    _wrapper.cache_clear = cache_clear
    _wrapper.invalidate = invalidate
    _wrapper.get_containing = get_containing
    return _wrapper


type DecoratedCoro[**P, T] = Callable[[CoroFunction[P, T]], CachedTask[P, T]]


@overload
def async_cache[**P, T](*, maxsize: int | None = 128, ttl: float | None = None) -> DecoratedCoro[P, T]: ...
@overload
def async_cache[**P, T](coro: CoroFunction[P, T], /) -> CachedTask[P, T]: ...
def async_cache[**P, T](
    maxsize: int | CoroFunction[P, T] | None = 128, ttl: float | None = None
) -> DecoratedCoro[P, T] | CachedTask[P, T]:
    """Decorator to cache the result of a coroutine.

    This decorator caches the result of a coroutine to improve performance
    by avoiding redundant computations. It is functionally similar to :func:`functools.cache`
    and :func:`functools.lru_cache` but designed for coroutines.

    Parameters
    ----------
    maxsize : int | CoroFunction[P, T] | None, optional
        The maximum number of items to cache. If a coroutine function is provided directly,
        it is assumed to be the function to be decorated, and `maxsize` defaults to 128.
        If `None`, the cache can grow without bound. Default is 128.
    ttl : float | None, optional
        The time-to-live for cached items in seconds. If `None`, items do not expire.
        Default is None.

    Returns
    -------
    DecoratedCoro[P, T] | CachedTask[P, T]
        If a coroutine is provided directly, returns the cached task.
        Otherwise, returns a decorator that can be applied to a coroutine.

    Examples
    --------
    Using the decorator with default parameters:

    >>> @async_cache
    ... async def fetch_data(url: str) -> str:
    ...     # Simulate a network request
    ...     await asyncio.sleep(1)
    ...     return f"Data from {url}"

    Using the decorator with custom parameters:

    >>> @async_cache(maxsize=256, ttl=60.0)
    ... async def fetch_data(url: str) -> str:
    ...     # Simulate a network request
    ...     await asyncio.sleep(1)
    ...     return f"Data from {url}"

    """
    if callable(maxsize):
        coro, maxsize = maxsize, 128
        wrapper = _cache_wrapper(coro, maxsize, ttl)
        wrapper.cache_parameters = lambda: {"maxsize": maxsize, "ttl": ttl}
        return wrapper

    maxsize = max(maxsize, 0) if isinstance(maxsize, int) else None

    def decorator(coro: CoroFunction[P, T]) -> CachedTask[P, T]:
        wrapper = _cache_wrapper(coro, maxsize, ttl)
        wrapper.cache_parameters = lambda: {"maxsize": maxsize, "ttl": ttl}
        return wrapper

    return decorator
