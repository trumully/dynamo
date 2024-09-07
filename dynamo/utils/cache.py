import asyncio
import threading
from collections import OrderedDict
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Coroutine, TypeVar

R = TypeVar("R")


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


def async_lru_cache(maxsize: int = 128) -> Callable[[Callable[..., Coroutine[Any, Any, R]]], asyncio.Task[R]]:
    def decorator(func: Callable[..., Coroutine[Any, Any, R]]) -> Callable[..., Coroutine[Any, Any, R]]:
        cache: OrderedDict[CacheKey, asyncio.Task[R]] = OrderedDict()
        lock = threading.Lock()

        @wraps(func)
        def wrapper(*args: tuple[Any, ...], **kwargs: dict[str, Any]) -> asyncio.Task[R]:
            key = CacheKey(func, args, kwargs)
            with lock:
                if key in cache:
                    cache.move_to_end(key)
                    return cache[key]

                cache[key] = task = asyncio.create_task(func(*args, **kwargs))

                if len(cache) > maxsize:
                    cache.popitem(last=False)
            return task

        return wrapper

    return decorator
