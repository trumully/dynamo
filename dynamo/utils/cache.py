from __future__ import annotations

import asyncio
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable, Sized
from dataclasses import dataclass, field
from functools import partial, wraps
from typing import Any, ParamSpec, Protocol, TypeVar, cast, overload

from dynamo.typedefs import MISSING, CoroFunction
from dynamo.utils.format import shorten_string

P = ParamSpec("P")
T = TypeVar("T")

log = logging.getLogger(__name__)

WRAPPER_ASSIGNMENTS = ("__module__", "__name__", "__qualname__", "__doc__", "__annotations__", "__type_params__")
WRAPPER_UPDATES = ("__dict__",)
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


class CachedTask[**P, T](Protocol):
    __wrapped__: WrappedCoro[P, T]

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]: ...
    def cache_info(self) -> CacheInfo: ...
    def cache_clear(self) -> None: ...
    def cache_parameters(self) -> dict[str, int | float | None]: ...
    def invalidate(self, *args: P.args, **kwargs: P.kwargs) -> bool: ...
    def get_containing(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T] | None: ...


type DecoratedCoro[**P, T] = Callable[[CoroFunction[P, T]], CachedTask[P, T]]


class HashedSeq(list[Any]):
    __slots__: tuple[str, ...] = ("hash_value",)

    def __init__(self, /, *args: Any, _hash: Callable[[object], int] = hash) -> None:
        self[:] = args
        self.hash_value: int = _hash(args)

    def __hash__(self) -> int:  # type: ignore
        return self.hash_value


class LRU[K, V]:
    def __init__(self, maxsize: int, /) -> None:
        self.cache: OrderedDict[K, V] = OrderedDict()
        self.maxsize = maxsize

    def get[T](self, key: K, default: T, /) -> V | T:
        if key not in self.cache:
            return default
        self.cache.move_to_end(key)
        return self.cache[key]

    def __getitem__(self, key: K, /) -> V:
        value = self.cache[key]
        self.cache.move_to_end(key)
        return value

    def __setitem__(self, key: K, value: V, /) -> None:
        if key in self.cache:
            del self.cache[key]
        elif len(self.cache) >= self.maxsize:
            self.cache.popitem(last=False)
        self.cache[key] = value

    def remove(self, key: K, /) -> None:
        self.cache.pop(key, None)


@dataclass(slots=True)
class Node:
    children: dict[str, Node] = field(default_factory=dict)
    is_end: bool = False


@dataclass(slots=True)
class Trie:
    root: Node = field(default_factory=Node)

    def insert(self, word: str) -> None:
        node = self.root
        for char in word:
            if char not in node.children:
                node.children[char] = Node()
            node = node.children[char]
        node.is_end = True

    def search(self, prefix: str) -> list[str]:
        node = self.root
        for char in prefix:
            if char not in node.children:
                return []
            node = node.children[char]

        results: list[str] = []
        self._dfs(node, prefix, results)
        return results

    def _dfs(self, node: Node, current: str, results: list[str]) -> None:
        if node.is_end:
            results.append(current)
        for char, child in node.children.items():
            self._dfs(child, current + char, results)


def _create_key(args: tuple[Any, ...], kwargs: dict[Any, Any], kwargs_mark: tuple[object]) -> tuple[Any, ...]:
    key = args
    if kwargs:
        key += kwargs_mark + tuple(kwargs.items())
    return key


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
    Although efficient, it will treat `f(x=1, y=2)` and `f(y=2, x=1)` as distinct calls and will be cached
    separately.
    """
    key = _create_key(args, kwargs, kwargs_mark)
    return _finalize_key(key, fast_types)


async def wrap_future[T](future: asyncio.Future[T]) -> T:
    return await future


def task_from_future[T](future: asyncio.Future[T]) -> asyncio.Task[T]:
    return asyncio.create_task(wrap_future(future))


def _cache_wrapper[**P, T](coro: CoroFunction[P, T], maxsize: int | None, ttl: float | None) -> CachedTask[P, T]:
    sentinel = MISSING
    make_key = _make_key

    internal_cache: OrderedDict[Hashable, asyncio.Future[T]] = OrderedDict()
    cache_get = internal_cache.get
    cache_len = internal_cache.__len__
    lock = threading.Lock()
    _cache_info = CacheInfo()

    @wraps(coro)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]:
        key: Hashable = make_key(args, kwargs)
        to_log = shorten_string(
            f"{coro.__name__}("
            f"{', '.join(map(str, args))}"
            f"{', ' if kwargs else ''}"
            f"{', '.join(f'{k}={v!r}' for k, v in kwargs.items())}"
            f")"
        )

        with lock:
            future = cache_get(key, sentinel)
            if future is not sentinel:
                log.debug("Cache hit for %s", to_log)
                _cache_info.hits += 1
                return task_from_future(future)
        log.debug("Cache miss for %s", to_log)
        _cache_info.misses += 1
        future: asyncio.Future[T] = asyncio.get_running_loop().create_future()

        with lock:
            if maxsize is not None:
                if key not in internal_cache and _cache_info.full:
                    log.debug("Eviction: LRU cache is full")
                    internal_cache.popitem(last=False)
                internal_cache[key] = future
                internal_cache.move_to_end(key)
                _cache_info.full = cache_len() >= maxsize
                _cache_info.currsize = cache_len()
            else:
                internal_cache[key] = future

        if ttl is not None:

            def evict(k: Hashable, default: Any = MISSING) -> None:
                log.debug("Eviction: TTL expired for %s", k)
                with lock:
                    internal_cache.pop(k, default)

            call_after_ttl = partial(asyncio.get_running_loop().call_later, ttl, evict, key)
            future.add_done_callback(call_after_ttl)

        async def run_coro() -> T:
            try:
                result = await coro(*args, **kwargs)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
                log.exception("Error in cached coroutine %s", to_log)
                raise
            return result

        return asyncio.create_task(run_coro())

    def cache_info() -> CacheInfo:
        return _cache_info

    def cache_clear() -> None:
        with lock:
            internal_cache.clear()
            _cache_info.clear()

    def invalidate(*args: P.args, **kwargs: P.kwargs) -> bool:
        key = make_key(args, kwargs)
        log.debug("Invalidating cache for %s", key)
        with lock:
            return internal_cache.pop(key, sentinel) is not sentinel

    def get_containing(*args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T] | None:
        key = make_key(args, kwargs)
        with lock:
            future = cache_get(key, sentinel)
            return task_from_future(future) if future is not sentinel else None

    _wrapper = cast(CachedTask[P, T], wrapper)
    _wrapper.cache_info = cache_info
    _wrapper.cache_clear = cache_clear
    _wrapper.invalidate = invalidate
    _wrapper.get_containing = get_containing
    return _wrapper


@overload
def async_cache[**P, T](*, maxsize: int | None = 128, ttl: float | None = None) -> DecoratedCoro[P, T]: ...


@overload
def async_cache[**P, T](coro: CoroFunction[P, T], /) -> CachedTask[P, T]: ...


def async_cache[**P, T](
    maxsize: int | CoroFunction[P, T] | None = 128, ttl: float | None = None
) -> CachedTask[P, T] | DecoratedCoro[P, T]:
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
    CachedTask[P, T] | DecoratedCoro[P, T]
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
    if isinstance(maxsize, int):
        maxsize = max(maxsize, 0)
    elif callable(maxsize):
        coro, maxsize = maxsize, 128
        wrapper = _cache_wrapper(coro, maxsize, ttl)
        wrapper.cache_parameters = lambda: {"maxsize": maxsize, "ttl": ttl}
        return wrapper
    else:
        error = "Expected first argument to be an integer, a coroutine, or None"
        raise TypeError(error) from None

    def decorator(coro: CoroFunction[P, T]) -> CachedTask[P, T]:
        wrapper = _cache_wrapper(coro, maxsize, ttl)
        wrapper.cache_parameters = lambda: {"maxsize": maxsize, "ttl": ttl}
        return wrapper

    return decorator
