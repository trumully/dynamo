from __future__ import annotations

import asyncio
from collections.abc import Callable, Hashable
from functools import partial
from typing import Any, overload

from dynamo.types import CoroFunction
from dynamo.utils.hashable import make_key

type CachedTask[**P, T] = Callable[P, asyncio.Task[T]]
type DecoratedCachedTask[**P, T] = Callable[[CoroFunction[P, T]], CachedTask[P, T]]


class LRU[K, V]:
    """A Least Recently Used (LRU) cache implementation."""

    def __init__(self, maxsize: int | None, /):
        self.cache: dict[K, V] = {}
        self.maxsize = maxsize

    def get[T](self, key: K, default: T, /) -> V | T:
        if key not in self.cache:
            return default
        self.cache[key] = self.cache.pop(key)
        return self.cache[key]

    def __getitem__(self, key: K, /) -> V:
        self.cache[key] = self.cache.pop(key)
        return self.cache[key]

    def __setitem__(self, key: K, value: V, /):
        self.cache[key] = value
        if self.maxsize is not None and len(self.cache) > self.maxsize:
            self.cache.pop(next(iter(self.cache)))

    def remove(self, key: K) -> None:
        self.cache.pop(key, None)


def _lru_evict(ttl: float, cache: LRU[Hashable, Any], key: Hashable, _ignored_task: object) -> None:
    asyncio.get_running_loop().call_later(ttl, cache.remove, key)


@overload
def task_cache[**P, T](maxsize: int | None = 128, ttl: float | None = None) -> DecoratedCachedTask[P, T]: ...
@overload
def task_cache[**P, T](coro: CoroFunction[P, T], /) -> CachedTask[P, T]: ...
def task_cache[**P, T](
    maxsize: int | CoroFunction[P, T] | None = 128, ttl: float | None = None, /
) -> DecoratedCachedTask[P, T] | CachedTask[P, T]:
    """Decorator to change behavior of coroutine function to act as functions returning cached tasks"""
    if callable(maxsize):
        _coro, maxsize = maxsize, 128
    else:
        maxsize = max(maxsize, 0) if isinstance(maxsize, int) else None

    def wrapper(coro: CoroFunction[P, T]) -> CachedTask[P, T]:
        internal_cache: LRU[Hashable, asyncio.Task[T]] = LRU(maxsize)

        def wrapped(*args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]:
            key = make_key(args, kwargs)
            try:
                return internal_cache[key]
            except KeyError:
                internal_cache[key] = task = asyncio.create_task(coro(*args, **kwargs))
                if ttl is not None:
                    task.add_done_callback(partial(_lru_evict, ttl, internal_cache, key))
                return task

        return wrapped

    return wrapper if not callable(maxsize) else wrapper(maxsize)
