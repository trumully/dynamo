from __future__ import annotations

import asyncio
from collections.abc import Callable, MutableMapping
from functools import partial, update_wrapper
from typing import Any, NamedTuple, Protocol, overload

from dynamo.types import CoroFunction
from dynamo.utils.hashable import HashedSeq


class CacheInfo(NamedTuple):
    hits: int
    misses: int
    maxsize: int
    currsize: int


class CacheParameters(NamedTuple):
    maxsize: int | None
    ttl: float | None


class CacheableTask[**P, T](Protocol):
    __slots__: tuple[str, ...] = ()

    @property
    def __wrapped__(self) -> CoroFunction[P, T]: ...

    def __get__(self: CacheableTask[P, T], instance: Any, owner: type | None = None) -> Any:
        return self if instance is None else BoundCacheableTask[instance, P, T](self, instance)

    __call__: CoroFunction[P, T]

    def cache_parameters(self) -> CacheParameters: ...
    def cache_info(self) -> CacheInfo: ...
    def cache_clear(self) -> None: ...
    def cache_discard(self, *args: P.args, **kwargs: P.kwargs) -> None: ...


def _lru_evict[Key: HashedSeq | int | str](ttl: float, cache: LRU[Key, Any], key: Key, _ignored_task: object) -> None:
    asyncio.get_running_loop().call_later(ttl, cache.remove, key)


class CachedTask[**P, T](CacheableTask[P, T]):
    __slots__ = (
        "__cache",
        "__dict__",
        "__hits",
        "__maxsize",
        "__misses",
        "__ttl",
        "__weakref__",
        "__wrapped__",
    )

    __wrapped__: CoroFunction[P, T]

    def __init__(self, call: CoroFunction[P, T], maxsize: int, ttl: float | None) -> None:
        self.__wrapped__ = call  # type: ignore
        self.__hits = 0
        self.__misses = 0
        self.__maxsize = maxsize
        self.__ttl = ttl
        self.__cache = LRU[HashedSeq | int | str, asyncio.Task[T]](maxsize)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]:  # type: ignore
        key = HashedSeq.from_call(args, kwargs)
        try:
            task = self.__cache[key]
        except KeyError:
            self.__misses += 1
            task = asyncio.create_task(self.__wrapped__(*args, **kwargs))
            if key not in self.__cache:
                self.__cache[key] = task
            if self.__ttl is not None:
                task.add_done_callback(partial(_lru_evict, self.__ttl, self.__cache, key))
        else:
            self.__hits += 1
        return task

    def cache_parameters(self) -> CacheParameters:
        return CacheParameters(self.__maxsize, self.__ttl)

    def cache_info(self) -> CacheInfo:
        return CacheInfo(self.__hits, self.__misses, self.__maxsize, len(self.__cache))

    def cache_clear(self) -> None:
        self.__hits = 0
        self.__misses = 0
        self.__cache.clear()

    def cache_discard(self, *args: P.args, **kwargs: P.kwargs) -> None:
        self.__cache.remove(HashedSeq.from_call(args, kwargs))


class BoundCacheableTask[S, **P, T]:
    __slots__ = ("__self__", "__weakref__", "_task")

    def __init__(self, task: CacheableTask[P, T], __self__: object):
        self._task = task
        self.__self__ = __self__
        self.__setattr__("__annotations__", task.__annotations__)
        self.__setattr__("__doc__", task.__doc__)

    @property
    def __wrapped__(self) -> CoroFunction[P, T]:
        return self._task.__wrapped__

    @property
    def __func__(self) -> CacheableTask[P, T]:
        return self._task

    def __get__[S2](
        self: BoundCacheableTask[S, P, T], instance: S2, owner: type | None = None
    ) -> BoundCacheableTask[S2, P, T]:
        return BoundCacheableTask(self._task, instance)

    def cache_parameters(self) -> CacheParameters:
        return self._task.cache_parameters()

    def cache_info(self) -> CacheInfo:
        return self._task.cache_info()

    def cache_clear(self) -> None:
        return self._task.cache_clear()

    def cache_discard(self, *args: P.args, **kwargs: P.kwargs) -> None:
        args_with_self: tuple[Any, ...] = (self.__self__, *args)
        return self._task.cache_discard(*args_with_self, **kwargs)

    def __repr__(self) -> str:
        name = getattr(self.__wrapped__, "__qualname__", "?")
        return f"<bound cached task {name} of {self.__self__!r}>"


class Node:
    __slots__ = ("children", "is_end")

    def __init__(self) -> None:
        self.children: MutableMapping[str, Node] = {}
        self.is_end: bool = False


class LRU[K, V]:
    def __init__(self, maxsize: int, /):
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
        if len(self.cache) > self.maxsize:
            self.cache.pop(next(iter(self.cache)))

    def __contains__(self, key: K, /) -> bool:
        return key in self.cache

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


@overload
def task_cache[**P, T](
    *, maxsize: int = 128, ttl: float | None = None
) -> Callable[[CoroFunction[P, T]], CacheableTask[P, T]]: ...
@overload
def task_cache[**P, T](coro: CoroFunction[P, T], /) -> CacheableTask[P, T]: ...
def task_cache[**P, T](
    maxsize: int | CoroFunction[P, T] = 128, ttl: float | None = None
) -> Callable[[CoroFunction[P, T]], CacheableTask[P, T]] | CacheableTask[P, T]:
    """Decorator that modifies coroutine functions to act as functions returning cached tasks."""
    if isinstance(maxsize, int):
        maxsize = 0 if maxsize < 0 else maxsize
    elif callable(maxsize):
        fast_wrapper = CachedTask(maxsize, 128, ttl)
        update_wrapper(fast_wrapper, maxsize)
        return fast_wrapper

    def decorator(coro: CoroFunction[P, T]) -> CacheableTask[P, T]:
        wrapper = CachedTask(coro, maxsize, ttl)
        update_wrapper(wrapper, coro)
        return wrapper

    return decorator
