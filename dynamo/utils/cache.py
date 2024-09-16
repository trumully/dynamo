from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Coroutine, Generic, ParamSpec, Protocol, TypeVar, cast

P = ParamSpec("P")
R = TypeVar("R")


@dataclass(slots=True)
class CacheInfo:
    """
    Cache info for the async_lru_cache decorator.

    Attributes
    ----------
    hits : int
        Number of cache hits.
    misses : int
        Number of cache misses.
    maxsize : int
        Maximum size of the cache.
    currsize : int
        Current size of the cache.

    Methods
    -------
    clear()
        Reset all counters to zero.
    """

    hits: int = 0
    misses: int = 0
    maxsize: int = 128
    currsize: int = 0

    def clear(self) -> None:
        """Reset all counters to zero."""
        self.hits = self.misses = self.currsize = 0


@dataclass(frozen=True, slots=True)
class CacheKey:
    """
    Hashable cache key for functions. Requires args and kwargs to be hashable.

    Attributes
    ----------
    func : Callable
        The function being cached.
    args : tuple
        Positional arguments to the function.
    kwargs : frozenset
        Keyword arguments to the function.

    Methods
    -------
    __post_init__()
        Convert kwargs to a frozenset for hashing.
    __hash__()
        Compute a hash value for the cache key.
    __repr__()
        Return a string representation of the cache key.
    """

    func: Callable
    args: tuple
    kwargs: frozenset

    def __hash__(self) -> int:
        """Compute a hash value for the cache key."""
        return hash((self.func, self.args, self.kwargs))

    def __repr__(self) -> str:
        """Return a string representation of the cache key."""
        return f"func={self.func.__name__}, args={self.args}, kwargs={self.kwargs}"


_cached: dict[Callable[..., Awaitable[Any]], AsyncCacheable] = {}


class Cacheable(Protocol[P]):
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[R]: ...
    def cache_info(self) -> CacheInfo: ...
    def cache_clear(self, *args: P.args, **kwargs: P.kwargs) -> bool: ...
    def cache_clear_all(self) -> None: ...


class AsyncCacheable(Generic[P, R]):
    def __init__(self, func: Callable[P, Awaitable[R]], maxsize: int = 128) -> None:
        self.func = func
        self.cache: OrderedDict[CacheKey, asyncio.Task[Any]] = OrderedDict()
        self.info = CacheInfo(maxsize=maxsize)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[R]:
        key = CacheKey(self.func, args, frozenset(kwargs.items()))

        if key in self.cache:
            self.info.hits += 1
            self.cache.move_to_end(key)
            return self.cache[key]

        self.info.misses += 1
        task: asyncio.Task[Any] = asyncio.create_task(cast(Coroutine[Any, Any, Any], self.func(*args, **kwargs)))
        self.cache[key] = task
        self.info.currsize = len(self.cache)

        if self.info.currsize > self.info.maxsize:
            self.cache.popitem(last=False)

        return task

    def cache_info(self) -> CacheInfo:
        return self.info

    def cache_clear(self, *args: P.args, **kwargs: P.kwargs) -> bool:
        key = CacheKey(self.func, args, frozenset(kwargs.items()))
        try:
            self.cache.pop(key)
            self.info.currsize -= 1
        except KeyError:
            return False
        return True

    def cache_clear_all(self) -> None:
        self.cache.clear()
        self.info.clear()


def async_lru_cache(maxsize: int = 128) -> Callable[[Callable[P, Awaitable[R]]], AsyncCacheable[P, R]]:
    """
    Decorator to create an async LRU cache of results.

    Parameters
    ----------
    maxsize : int, optional
        Maximum size of the cache. Default is 128.

    Returns
    -------
    Callable[[A], asyncio.Task[R]]
        A decorator that can be applied to an async function.

    Notes
    -----
    The decorated function will have additional methods:
    - cache_info(): Returns a CacheInfo object with current cache statistics.
    - cache_clear(func, *args, **kwargs): Clears a specific cache entry.
    - cache_clear_all(): Clears all cache entries.

    See
    ---
        :func:`functools.lru_cache`
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> AsyncCacheable[P, R]:
        cached = AsyncCacheable(func, maxsize)
        _cached[func] = cached
        return cached

    return decorator


def cached_functions() -> str:
    """
    Get a string representation of all cached functions and their info.

    Returns
    -------
    str
        A string containing the names of all cached functions and their cache info.
    """
    return "\n".join([f"{func.__name__}: {cacheable.cache_info()}" for func, cacheable in _cached.items()])
