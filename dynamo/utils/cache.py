from __future__ import annotations

import asyncio
from functools import partial, update_wrapper
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol, overload

from dynamo.utils.hashable import HashedSeq

if TYPE_CHECKING:
    from collections.abc import Callable, MutableMapping, Sized

    from dynamo.types import CoroFunction


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

    def __get__[S: object](
        self, instance: S, owner: type[S] | None = None
    ) -> CacheableTask[P, T] | BoundCacheableTask[S, P, T]:
        return self if instance is None else BoundCacheableTask[S, P, T](self, instance)

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
        "__sentinel",
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
        self.__wrapped__ = call
        self.__hits = 0
        self.__misses = 0
        self.__maxsize = maxsize
        self.__ttl = ttl
        self.__cache = LRU[HashedSeq | int | str, asyncio.Task[T]](maxsize)
        self.__sentinel = object()

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]:  # type: ignore[override]
        key = HashedSeq.from_call(args, kwargs)
        try:
            task = self.__cache[key]
        except KeyError:
            self.__misses += 1
            task = asyncio.create_task(self.__wrapped__(*args, **kwargs))
            if self.__cache.get(key, self.__sentinel) is self.__sentinel:
                self.__cache[key] = task
            if self.__ttl is not None:
                task.add_done_callback(partial(_lru_evict, self.__ttl, self.__cache, key))
        else:
            self.__hits += 1
        return task

    def cache_parameters(self) -> CacheParameters:
        return CacheParameters(self.__maxsize, self.__ttl)

    def cache_info(self, len: Callable[[Sized], int] = len) -> CacheInfo:  # noqa: A002
        return CacheInfo(self.__hits, self.__misses, self.__maxsize, len(self.__cache))

    def cache_clear(self) -> None:
        self.__hits = 0
        self.__misses = 0
        self.__cache.clear()

    def cache_discard(self, *args: P.args, **kwargs: P.kwargs) -> None:
        self.__cache.remove(HashedSeq.from_call(args, kwargs))


class BoundCacheableTask[S, **P, T]:
    __slots__ = ("__self__", "__weakref__", "_task")

    def __init__(self, task: CacheableTask[P, T], __self__: S) -> None:
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

    def __get__[S2: object](self, instance: S2, owner: type[S2] | None = None) -> BoundCacheableTask[S2, P, T]:
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
        return f"<bound cached task {getattr(self.__wrapped__, "__qualname__", "?")} of {self.__self__!r}>"


class Node:
    __slots__ = ("children", "is_end")

    def __init__(self) -> None:
        self.children: MutableMapping[str, Node] = {}
        self.is_end: bool = False


class _Sentinel(type):
    def __new__(cls, name: str) -> _Sentinel:
        return super().__new__(cls, name, (), {})

    def __repr__(cls) -> str:
        return "..."

    def __hash__(cls) -> int:
        return 0

    def __eq__(cls, other: object) -> bool:
        return other is cls


type Sentinel = _Sentinel
MISSING: Sentinel = _Sentinel("MISSING")


class LRU[K, V]:
    def __init__(self, maxsize: int, /) -> None:
        self._cache: dict[K, V] = {}
        self.maxsize = maxsize

    def get[T](self, key: K, default: T | Any = MISSING, /) -> V | T:
        try:
            self._cache[key] = self._cache.pop(key)
            return self._cache[key]
        except KeyError as exc:
            if default is MISSING:
                raise exc from None
            return default

    def __getitem__(self, key: K, /) -> V:
        self._cache[key] = self._cache.pop(key)
        return self._cache[key]

    def __setitem__(self, key: K, value: V, /) -> None:
        self._cache[key] = value
        if len(self._cache) > self.maxsize:
            self._cache.pop(next(iter(self._cache)))

    def __contains__(self, key: K, /) -> bool:
        return key in self._cache

    def remove(self, key: K) -> None:
        self._cache.pop(key, None)

    def __len__(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        self._cache.clear()


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
    if ttl is not None and ttl <= 0:
        msg = "ttl must be greater than 0"
        raise ValueError(msg) from None

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
