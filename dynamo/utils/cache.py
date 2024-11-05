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
    hits: int = 0
    misses: int = 0
    currsize: int = 0
    full: bool = False


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
        self._hash_value = hash_function(tuple(self))

    def __hash__(self) -> int:  # type: ignore
        return self._hash_value


class Node:
    __slots__ = ("key", "value", "prev", "next", "children", "is_end")

    def __init__(self, key: Any = None, value: Any = None) -> None:
        self.key: Any = key
        self.value: Any = value
        self.prev: Node | None = None
        self.next: Node | None = None
        self.children: MutableMapping[str, Node] = {}
        self.is_end: bool = False


class LRU[K, V]:
    """A Least Recently Used (LRU) cache implementation."""

    def __init__(self, maxsize: int | None) -> None:
        self.cache: MutableMapping[K, Node] = {}
        self.maxsize = maxsize
        self.head: Node | None = None
        self.tail: Node | None = None

    def get(self, key: K, default: Any = MISSING) -> V | Any:
        if node := self.cache.get(key):
            self._move_to_front(node)
            return node.value
        return default

    def __setitem__(self, key: K, value: V) -> None:
        if key in self.cache:
            node = self.cache[key]
            node.value = value
        else:
            node = Node(key=key, value=value)
            self.cache[key] = node
            if self.maxsize and len(self.cache) > self.maxsize:
                self._evict()
        self._move_to_front(node)

    def remove(self, key: K) -> None:
        if node := self.cache.pop(key, None):
            self._unlink(node)

    def clear(self) -> None:
        """Clear all items from the cache."""
        self.cache.clear()
        self.head = None
        self.tail = None

    def _move_to_front(self, node: Node) -> None:
        if self.head is node:
            return
        self._unlink(node)
        self._link_front(node)

    def _link_front(self, node: Node) -> None:
        if not self.head:
            self.head = self.tail = node
            return
        node.next = self.head
        self.head.prev = node
        self.head = node

    def _unlink(self, node: Node) -> None:
        prev, next_ = node.prev, node.next
        if prev:
            prev.next = next_
        if next_:
            next_.prev = prev
        if self.head is node:
            self.head = next_
        if self.tail is node:
            self.tail = prev
        node.prev = node.next = None

    def _evict(self) -> None:
        if self.tail:
            self.remove(self.tail.key)

    def __len__(self) -> int:
        return len(self.cache)


class Trie:
    def __init__(self) -> None:
        self.root = Node()

    def insert(self, word: str) -> None:
        node = self.root
        for char in word:
            node = node.children.setdefault(char, Node())
        node.is_end = True

    def search(self, prefix: str) -> list[str]:
        node = self.root
        for char in prefix:
            if char not in node.children:
                return []
            node = node.children[char]

        results: list[str] = []
        self._collect_words(node, prefix, results)
        return results

    def _collect_words(self, node: Node, prefix: str, results: list[str]) -> None:
        if node.is_end:
            results.append(prefix)
        for char, child in node.children.items():
            self._collect_words(child, prefix + char, results)


def _make_key(
    args: tuple[Any, ...],
    kwargs: dict[Any, Any],
    kwargs_mark: tuple[object] = (object(),),
    _type: type[type] = type,
    _len: Callable[[Sized], int] = len,
) -> Hashable:
    """
    Make cache key from optionally typed positional and keyword arguments. Structure is flat and hashable.
    Treats `f(x=1, y=2)` and `f(y=2, x=1)` as the same call for caching purposes.
    """
    key = args
    if kwargs:
        sorted_items = tuple(sorted(kwargs.items()))
        key += kwargs_mark + sorted_items
    return key[0] if _len(key) == 1 and _type(key[0]) in FAST_TYPES else HashedSeq(key)


def _cache_wrapper[**P, T](coro: CoroFunction[P, T], maxsize: int | None, ttl: float | None) -> CachedTask[P, T]:
    sentinel = MISSING
    make_key = _make_key

    cache: LRU[Hashable, asyncio.Future[T]] = LRU(maxsize)
    lock = asyncio.Lock()
    info: CacheInfo = CacheInfo()
    len_ = cache.__len__

    @wraps(coro)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        key: Hashable = make_key(args, kwargs)

        async with lock:
            cached_item = cache.get(key, sentinel)
            if cached_item is not sentinel:
                info.hits += 1
                return await cached_item if isinstance(cached_item, asyncio.Future) else cached_item

            future = asyncio.get_running_loop().create_future()
            cache[key] = future
            info.misses += 1
            info.currsize = len_()

        if ttl is not None:
            call_after_ttl = partial(asyncio.get_running_loop().call_later, ttl, cache.remove, key)
            future.add_done_callback(call_after_ttl)

        try:
            result = await coro(*args, **kwargs)
            future.set_result(result)
        except Exception as e:
            log.exception("Error in coroutine %s with args %s and kwargs %s", coro, args, kwargs)
            future.set_exception(e)
            raise e from None
        return result

    async def cache_clear() -> None:
        async with lock:
            cache.clear()
        info.hits = info.misses = info.currsize = 0
        info.full = False

    async def invalidate(*args: P.args, **kwargs: P.kwargs) -> bool:
        async with lock:
            return bool(cache.remove(make_key(args, kwargs)))

    async def get_containing(*args: P.args, **kwargs: P.kwargs) -> T | None:
        async with lock:
            future = cache.get(_make_key(args, kwargs))
            return await future if future else None

    _wrapper = cast(CachedTask[P, T], wrapper)
    _wrapper.cache_info = lambda: info
    _wrapper.cache_clear = cache_clear
    _wrapper.invalidate = invalidate
    _wrapper.get_containing = get_containing
    return _wrapper


type _DecoratedCachedTask[**P, T] = Callable[[CoroFunction[P, T]], CachedTask[P, T]]


@overload
def async_cache[**P, T](*, maxsize: int | None = 128, ttl: float | None = None) -> _DecoratedCachedTask[P, T]: ...
@overload
def async_cache[**P, T](coro: CoroFunction[P, T], /) -> CachedTask[P, T]: ...
def async_cache[**P, T](
    maxsize: int | CoroFunction[P, T] | None = 128, ttl: float | None = None
) -> _DecoratedCachedTask[P, T] | CachedTask[P, T]:
    """Cache results of a coroutine to avoid redundant computations.

    Similar to functools.cache/lru_cache but designed for coroutines.

    Parameters
    ----------
    maxsize : int | CoroFunction[P, T] | None, optional
        Maximum cache size. Defaults to 128. If None, cache is unbounded.
        If coroutine is passed directly, this becomes the decorated function.
    ttl : float | None, optional
        Time-to-live in seconds. If None, items don't expire.

    Returns
    -------
    _DecoratedCachedTask[P, T] | CachedTask[P, T]
        Cached coroutine or decorator function.

    Example
    -------
    >>> @async_cache(maxsize=256, ttl=60.0)
    ... async def fetch_data(url: str) -> str:
    ...     return await some_network_call(url)
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
