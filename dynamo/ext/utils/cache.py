from __future__ import annotations

import asyncio
import time
from enum import Enum, auto
from functools import wraps
from typing import Any, Callable, Coroutine, Iterator, MutableMapping, Protocol, TypeVar

from lru import LRU

T = TypeVar("T")


class CacheProtocol(Protocol[T]):
    cache: MutableMapping[str, asyncio.Task[T]]

    def __call__(self, *args: Any, **kwargs: Any) -> asyncio.Task[T]: ...

    def get_key(self, *args: Any, **kwargs: Any) -> str: ...

    def invalidate(self, *args: Any, **kwargs: Any) -> bool: ...

    def invalidate_containing(self, key: str) -> None: ...

    def get_stats(self) -> tuple[int, int]: ...


def extract_value(item: tuple[Any, Any]) -> Any:
    return item[1]


def extract_key(item: tuple[str, tuple[Any, Any]]) -> tuple[str, Any]:
    return (item[0], item[1][0])


class EphemeralCache(dict):
    def __init__(self, seconds: float) -> None:
        self.ttl = seconds
        super().__init__()

    def __verify_cache_integrity(self) -> None:
        current_time = time.monotonic()
        to_remove = [
            k for (k, (v, t)) in super().items() if current_time > (t + self.ttl)
        ]
        for k in to_remove:
            del self[k]

    def __contains__(self, key: str) -> bool:
        self.__verify_cache_integrity()
        return super().__contains__(key)

    def __getitem__(self, key: str) -> Any:
        self.__verify_cache_integrity()
        v, _ = super().__getitem__(key)
        return v

    def get(self, key: str, default: Any = None) -> Any:
        v = super().get(key, default)
        return default if v is default else v[0]

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, (value, time.monotonic()))

    def values(self) -> Iterator[Any]:
        return map(extract_value, super().values())

    def items(self) -> Iterator[Any]:
        return map(extract_key, super().items())


class Strategy(Enum):
    LRU = auto()
    RAW = auto()
    TIMED = auto()


def _stats() -> tuple[int, int]:
    return (0, 0)


def cache(
    maxsize: int = 128, strategy: Strategy = Strategy.LRU
) -> Callable[[Callable[..., Coroutine[Any, Any, T]]], CacheProtocol[T]]:
    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> CacheProtocol[T]:
        if strategy is Strategy.LRU:
            cache = LRU(maxsize)
            stats = cache.get_stats
        elif strategy is Strategy.RAW:
            cache = {}
            stats = _stats
        elif strategy is Strategy.TIMED:
            cache = EphemeralCache(maxsize)
            stats = _stats

        def make_key(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
            def true_repr(o):
                if o.__class__.__repr__ is object.__repr__:
                    return f"<{o.__class__.__module__}.{o.__class__.__name__}>"
                return repr(o)

            key = [f"{func.__module__}.{func.__name__}"]
            key.extend(true_repr(o) for o in args)

            return ":".join(key)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> asyncio.Task[T]:
            key = make_key(args, kwargs)

            try:
                task = cache[key]
            except KeyError:
                cache[key] = task = asyncio.create_task(func(*args, **kwargs))

            return task

        def invalidate(*args: Any, **kwargs: Any) -> bool:
            try:
                del cache[make_key(args, kwargs)]
            except KeyError:
                return False
            return True

        def invalidate_containing(key: str) -> None:
            to_remove = [k for k in cache if key in k]
            for k in to_remove:
                try:
                    del cache[k]
                except KeyError:
                    continue

        wrapper.cache = cache
        wrapper.get_key = lambda *args, **kwargs: make_key(args, kwargs)
        wrapper.invalidate = invalidate
        wrapper.get_stats = stats
        wrapper.invalidate_containing = invalidate_containing
        return wrapper

    return decorator
