import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from functools import wraps
from typing import Awaitable, Callable, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

# Awaitable[R] is essentially Coroutine[..., ..., R]
A = TypeVar("A", bound=Callable[P, Awaitable[R]])


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

    def __post_init__(self) -> None:
        """Convert kwargs to a frozenset for hashing."""
        object.__setattr__(self, "kwargs", frozenset(self.kwargs.items()))

    def __hash__(self) -> int:
        """Compute a hash value for the cache key."""
        return hash((self.func, self.args, self.kwargs))

    def __repr__(self) -> str:
        """Return a string representation of the cache key."""
        return f"{self.__qualname__}(func={self.func.__name__}, args={self.args}, kwargs={self.kwargs})"


_cached: dict[asyncio.Task[R], CacheInfo] = {}


def async_lru_cache(maxsize: int = 128) -> Callable[[A], asyncio.Task[R]]:
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

    def decorator(func: A) -> A:
        cache: OrderedDict[CacheKey, asyncio.Task[R]] = OrderedDict()
        info: CacheInfo = CacheInfo(maxsize=maxsize)

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> asyncio.Task[R]:
            if (key := CacheKey(func, args, kwargs)) in cache:
                info.hits += 1
                cache.move_to_end(key)
                return cache[key]

            info.misses += 1
            cache[key] = task = asyncio.create_task(func(*args, **kwargs))
            info.currsize = len(cache)

            if info.currsize > maxsize:
                cache.popitem(last=False)

            return task

        def cache_info() -> CacheInfo:
            """Return the current cache statistics."""
            return info

        def cache_clear(func: A, *args: P.args, **kwargs: P.kwargs) -> bool:
            """
            Clear a specific cache entry.

            Parameters
            ----------
            func : A
                The function associated with the cache entry.
            *args : P.args
                Positional arguments of the cache entry.
            **kwargs : P.kwargs
                Keyword arguments of the cache entry.

            Returns
            -------
            bool
                True if the entry was found and cleared, False otherwise.
            """
            try:
                cache.pop(CacheKey(func, args, kwargs))
            except KeyError:
                return False
            info.currsize -= 1
            return True

        def cache_clear_all() -> None:
            """Clear all cache entries and reset statistics."""
            cache.clear()
            info.clear()

        wrapper.cache_info = cache_info
        wrapper.cache_clear = cache_clear
        wrapper.cache_clear_all = cache_clear_all

        _cached[wrapper] = info

        return wrapper

    return decorator


def cached_functions() -> str:
    """
    Get a string representation of all cached functions and their info.

    Returns
    -------
    str
        A string containing the names of all cached functions and their cache info.
    """
    return "\n".join([f"{func.__name__}: {info}" for func, info in _cached.items()])
