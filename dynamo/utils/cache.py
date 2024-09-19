from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from functools import wraps
from typing import Any, Awaitable, Callable, ParamSpec, Protocol, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

log = logging.getLogger(__name__)


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
    currsize : int
        Current size of the cache.

    Methods
    -------
    clear()
        Reset all counters to zero.
    """

    hits: int = 0
    misses: int = 0
    currsize: int = 0

    def clear(self) -> None:
        """Reset all counters to zero."""
        self.hits = self.misses = self.currsize = 0

    def __repr__(self) -> str:
        """Return a string representation of the cache info."""
        return f"hits={self.hits}, misses={self.misses}, currsize={self.currsize}"


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
    """

    func: Awaitable
    args: tuple
    kwargs: frozenset

    def __hash__(self) -> int:
        """Compute a hash value for the cache key."""
        return hash((self.func, self.args, self.kwargs))

    def __repr__(self) -> str:
        """Return a string representation of the cache key."""
        return f"func={self.func.__name__}, args={self.args}, kwargs={self.kwargs}"


@dataclass(frozen=True, slots=True)
class CacheEntry:
    value: asyncio.Future[R] | asyncio.Task[R]
    expiry: float | None


class Cacheable(Protocol[R]):
    cache: OrderedDict[CacheKey, asyncio.Future[R] | asyncio.Task[R]]

    def __call__(self, *args: Any, **kwargs: Any) -> Awaitable[R]: ...
    def cache_info(self) -> CacheInfo: ...
    def cache_clear_all(self) -> None: ...
    def evict_containing(self, func_name: str) -> None: ...


def _make_key(func: Awaitable[R], *args: Any, **kwargs: Any) -> CacheKey:
    return CacheKey(func, args, frozenset(kwargs.items()))


def future_lru_cache(
    f: Callable[P, Awaitable[R]] | None = None, /, *, maxsize: int | None = None, ttl: int | None = None
) -> Cacheable[R] | Callable[[Callable[P, Awaitable[R]]], Cacheable[R]]:
    """Decorator to cache the result of an asynchronous function.

    Functionally similar to `functools.lru_cache`, but non-blocking and thread-safe.
    Eviction is carried out with an LRU algorithm and/or time-to-live (TTL).

    Parameters
    ----------
    `f : Callable[P, Awaitable[R]] | None, optional
        The function to cache.
    maxsize : int | None, optional
        The maximum number of items to cache.
    ttl : int | None, optional
        The time to live for cached items in seconds.
    """

    def decorator(func: Awaitable[Any]) -> Awaitable[R]:
        _cache: OrderedDict[CacheKey, CacheEntry] = OrderedDict()
        _info = CacheInfo()

        async def run_and_cache(func: Awaitable[R], *args: Any, **kwargs: Any) -> R:
            key: CacheKey = _make_key(func, *args, **kwargs)
            result = await func(*args, **kwargs)
            expiry = time.monotonic() + ttl if ttl else None
            _cache[key] = CacheEntry(asyncio.Future(), expiry)
            _cache[key].value.set_result(result)
            _evict()
            return result

        def _evict() -> None:
            now = time.monotonic()
            expired_keys = [k for k, v in _cache.items() if v.expiry is not None and now >= v.expiry]

            for key in expired_keys:
                _cache.pop(key)
                _info.currsize -= 1
                log.debug("Cache eviction (expired): %s\n%s\nMaxsize: %s TTL: %s", key, _info, maxsize, ttl)

            if maxsize is not None:
                while _cache and _info.currsize > maxsize:
                    key, _ = _cache.popitem(last=False)
                    _info.currsize -= 1
                    log.debug("Cache eviction (maxsize): %s\n%s\nMaxsize: %s TTL: %s", key, _info, maxsize, ttl)

        def evict_containing(func_name: str) -> None:
            to_evict = [k for k in _cache if k.func.__name__ == func_name]
            for key in to_evict:
                try:
                    del _cache[key]
                    _info.currsize -= 1
                    log.debug("Cache eviction (explicit): %s\n%s\nMaxsize: %s TTL: %s", key, _info, maxsize, ttl)
                except KeyError:
                    pass

        def cache_info() -> CacheInfo:
            return _info

        def cache_clear_all() -> None:
            _cache.clear()
            _info.clear()

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> asyncio.Future[R] | asyncio.Task[R]:
            _evict()
            now = time.monotonic()
            key = _make_key(func, *args, **kwargs)
            if key in _cache:
                _info.hits += 1
                log.debug("Cache hit: %s\n%s\nMaxsize: %s TTL: %s", key, _info, maxsize, ttl)
                if isinstance(_cache[key].value, asyncio.Future):
                    return _cache[key].value
                f = asyncio.Future()
                f.set_result(_cache[key].value)
                return f
            _info.misses += 1
            _info.currsize += 1
            log.debug("Cache miss: %s\n%s\nMaxsize: %s TTL: %s", key, _info, maxsize, ttl)
            task: asyncio.Task[R] = asyncio.create_task(run_and_cache(func, *args, **kwargs))
            _cache[key] = CacheEntry(task, now + ttl if ttl else None)
            return task

        wrapper.cache_info = cache_info
        wrapper.cache_clear_all = cache_clear_all
        wrapper.evict_containing = evict_containing
        return wrapper

    return decorator if f is None else decorator(f)
