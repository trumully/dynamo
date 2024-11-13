from __future__ import annotations

import asyncio
from collections.abc import Callable, Hashable, MutableMapping
from functools import partial
from typing import Any, NamedTuple, overload

from dynamo.types import CoroFunction
from dynamo.utils.hashable import make_key

type CachedTaskDecorator[**P, T] = Callable[[CoroFunction[P, T]], CachedTask[P, T]]


class CacheInfo:
    def __init__(self) -> None:
        self.hits = 0
        self.misses = 0
        self.currsize = 0

    def clear(self) -> None:
        self.hits = self.misses = self.currsize = 0


class CacheParameters(NamedTuple):
    maxsize: int | None
    ttl: float | None


class CachedTask[**P, T]:
    def __init__(
        self,
        callback: Callable[P, asyncio.Task[T]],
        info: CacheInfo,
        parameters: CacheParameters,
        cache_clear: Callable[[], None],
        invalidate: Callable[P, bool],
    ) -> None:
        self.callback = callback
        self.info = info
        self.parameters = parameters
        self.cache_clear = cache_clear
        self.invalidate = invalidate

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]:
        return self.callback(*args, **kwargs)


class Node:
    __slots__ = ("children", "is_end")

    def __init__(self) -> None:
        self.children: MutableMapping[str, Node] = {}
        self.is_end: bool = False


class LRU[K, V]:
    def __init__(self, maxsize: int | None = None, /):
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

    def clear(self) -> None:
        self.cache.clear()

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


def _lru_evict(ttl: float, cache: LRU[Hashable, Any], key: Hashable, _ignored_task: object) -> None:
    asyncio.get_running_loop().call_later(ttl, cache.remove, key)


@overload
def task_cache[**P, T](*, maxsize: int | None = 128, ttl: float | None = None) -> CachedTaskDecorator[P, T]: ...
@overload
def task_cache[**P, T](coro: CoroFunction[P, T], /) -> CachedTask[P, T]: ...
def task_cache[**P, T](
    maxsize: int | CoroFunction[P, T] | None = 128, ttl: float | None = None
) -> CachedTaskDecorator[P, T] | CachedTask[P, T]:
    """Decorator that modifies coroutine functions to act as functions returning cached tasks"""
    coro = None
    if callable(maxsize):
        coro, maxsize = maxsize, 128

    maxsize = max(maxsize, 0) if isinstance(maxsize, int) else None

    def wrapper(coro: CoroFunction[P, T]) -> CachedTask[P, T]:
        cache: LRU[Hashable, asyncio.Task[T]] = LRU(maxsize)
        info: CacheInfo = CacheInfo()

        def wrapped(*args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]:
            key: Hashable = make_key(args, kwargs)

            try:
                task = cache[key]
            except KeyError:
                cache[key] = task = asyncio.create_task(coro(*args, **kwargs))
                if ttl is not None:
                    task.add_done_callback(partial(_lru_evict, ttl, cache, key))
                info.misses += 1
            else:
                info.hits += 1

            info.currsize = len(cache)

            return task

        def cache_clear() -> None:
            cache.clear()
            info.clear()

        def invalidate(*args: P.args, **kwargs: P.kwargs) -> bool:
            return bool(cache.remove(make_key(args, kwargs)))

        return CachedTask(wrapped, info, CacheParameters(maxsize, ttl), cache_clear, invalidate)

    return wrapper(coro) if coro is not None else wrapper
