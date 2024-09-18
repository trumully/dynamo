from __future__ import annotations

import asyncio
import logging
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

    func: Awaitable
    args: tuple
    kwargs: frozenset

    def __hash__(self) -> int:
        """Compute a hash value for the cache key."""
        return hash((self.func, self.args, self.kwargs))

    def __repr__(self) -> str:
        """Return a string representation of the cache key."""
        return f"func={self.func.__name__}, args={self.args}, kwargs={self.kwargs}"


class Cacheable(Protocol[R]):
    cache: OrderedDict[CacheKey, asyncio.Future[R] | asyncio.Task[R]]

    def __call__(self, *args: Any, **kwargs: Any) -> Awaitable[R]: ...
    def cache_info(self) -> CacheInfo: ...
    def cache_clear_all(self) -> None: ...


def future_lru_cache(maxsize: int | None = None) -> Callable[[Awaitable[R]], Cacheable[R]]:
    INITIAL_MAXSIZE = 128
    maxsize = INITIAL_MAXSIZE if callable(maxsize) else maxsize

    def decorator(func: Awaitable[Any]) -> Awaitable[R]:
        _cache: OrderedDict[CacheKey, asyncio.Future[R] | asyncio.Task[R]] = OrderedDict()
        _info = CacheInfo()

        def _make_key(func: Awaitable[R], *args: Any, **kwargs: Any) -> CacheKey:
            return CacheKey(func, args, frozenset(kwargs.items()))

        async def run_and_cache(func: Awaitable[R], *args: Any, **kwargs: Any) -> R:
            key: CacheKey = _make_key(func, *args, **kwargs)
            _cache[key] = result = await func(*args, **kwargs)
            if isinstance(maxsize, int) and len(_cache) > maxsize:
                _cache.popitem(last=False)
            return result

        def cache_info() -> CacheInfo:
            return _info

        def cache_clear_all() -> None:
            _cache.clear()
            _info.clear()

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> asyncio.Future[R] | asyncio.Task[R]:
            key = _make_key(func, *args, **kwargs)
            if key in _cache:
                _info.hits += 1
                if isinstance(_cache[key], asyncio.Future):
                    return _cache[key]
                f = asyncio.Future()
                f.set_result(_cache[key])
                log.debug("Cache hit: %s\n%s", key, _info)
                return f
            task: asyncio.Task[R] = asyncio.create_task(run_and_cache(func, *args, **kwargs))
            _cache[key] = task
            _info.currsize += 1
            _info.misses += 1
            log.debug("Cache miss: %s\n%s", key, _info)
            return task

        wrapper.cache_info = cache_info
        wrapper.cache_clear_all = cache_clear_all
        return wrapper

    return decorator(maxsize) if callable(maxsize) else decorator
