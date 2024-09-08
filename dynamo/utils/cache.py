import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Coroutine, TypeVar

R = TypeVar("R")


@dataclass(slots=True)
class CacheInfo:
    """Cache info for the async_lru_cache decorator."""

    hits: int = 0
    misses: int = 0
    maxsize: int = 128
    currsize: int = 0

    def clear(self) -> None:
        self.hits = 0
        self.misses = 0
        self.currsize = 0


@dataclass(frozen=True, slots=True)
class CacheKey:
    """Hashable cache key for functions. Requires args and kwargs to be hashable."""

    func: Callable
    args: tuple
    kwargs: frozenset

    def __post_init__(self) -> None:
        object.__setattr__(self, "kwargs", frozenset(self.kwargs.items()))

    def __hash__(self) -> int:
        return hash((self.func, self.args, self.kwargs))

    def __repr__(self) -> str:
        return f"CacheKey(func={self.func.__name__}, args={self.args}, kwargs={self.kwargs})"


_cached: dict[asyncio.Task[R], CacheInfo] = {}


def async_lru_cache(maxsize: int = 128) -> Callable[[Callable[..., Coroutine[Any, Any, R]]], asyncio.Task[R]]:
    def decorator(func: Callable[..., Coroutine[Any, Any, R]]) -> Callable[..., Coroutine[Any, Any, R]]:
        cache: OrderedDict[CacheKey, asyncio.Task[R]] = OrderedDict()
        info: CacheInfo = CacheInfo(0, 0, maxsize, 0)

        @wraps(func)
        def wrapper(*args: tuple[Any, ...], **kwargs: dict[str, Any]) -> asyncio.Task[R]:
            if (key := CacheKey(func, args, kwargs)) in cache:
                info.hits += 1
                cache.move_to_end(key)
                return cache[key]

            info.misses += 1
            info.currsize += 1
            cache[key] = task = asyncio.create_task(func(*args, **kwargs))

            if len(cache) > maxsize:
                cache.popitem(last=False)

            return task

        def cache_info() -> CacheInfo:
            return info

        def cache_clear(
            func: Callable[..., Coroutine[Any, Any, R]], *args: tuple[Any, ...], **kwargs: dict[str, Any]
        ) -> bool:
            try:
                cache.pop(CacheKey(func, args, kwargs))
            except KeyError:
                return False
            info.currsize -= 1
            return True

        wrapper.cache_info = cache_info
        wrapper.cache_clear = cache_clear

        _cached[wrapper] = info

        return wrapper

    return decorator


def cached_functions() -> str:
    return "\n".join([f"{func.__name__}: {info}" for func, info in _cached.items()])
