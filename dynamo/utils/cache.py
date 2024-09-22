from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Callable, Coroutine, Hashable, Sized
from dataclasses import dataclass
from functools import partial
from typing import Any, Protocol, TypedDict

from dynamo._typing import AC, P, T

log = logging.getLogger(__name__)


@dataclass(slots=True)
class CacheInfo:
    """Cache info for the async_lru_cache decorator."""

    hits: int = 0
    misses: int = 0
    currsize: int = 0

    def clear(self) -> None:
        """Reset all counters to zero."""
        self.hits = self.misses = self.currsize = 0


class HashedSeq(list[Any]):
    __slots__ = ("hash_value",)

    def __init__(self, *args: Any, hash: Callable[[object], int] = hash) -> None:  # noqa: A002
        self[:] = args
        self.hash_value: int = hash(args)

    def __hash__(self) -> int:
        return self.hash_value


def make_key(
    args: tuple[Any, ...],
    kwargs: dict[Any, Any],
    kwargs_mark: tuple[object] = (object(),),
    fast_types: set[type] = {int, str},  # noqa: B006
    type: type[type] = type,  # noqa: A002
    len: Callable[[Sized], int] = len,  # noqa: A002
) -> Hashable:
    key: tuple[Any, ...] = args
    if kwargs:
        key += kwargs_mark
        for item in kwargs.items():
            key += item
    return key[0] if len(key) == 1 and type(key[0]) in fast_types else HashedSeq(key)


class CacheParameters(TypedDict):
    maxsize: int | None
    ttl: float | None


class LRUAsyncCallable(Protocol[AC]):
    __slots__: tuple[str, ...] = ()

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, T]: ...
    def cache_info(self) -> CacheInfo: ...
    def cache_clear(self) -> None: ...
    def cache_parameters(self) -> CacheParameters: ...


def async_cache(
    f: AC | None = None,
    /,
    *,
    maxsize: int | None = None,
    ttl: float | None = None,
) -> Callable[[LRUAsyncCallable[AC]], Callable[P, asyncio.Task[T]]]:
    """Decorator to cache the result of an asynchronous function.

    Functionally similar to `functools.cache` & `functools.lru_cache` but non-blocking and thread-safe.

    Parameters
    ----------
    maxsize : int | None, optional
        Set the maximum number of items to cache.
    ttl : int | None, optional
        Set the time to live for cached items in seconds.

    See
    ---
    - https://github.com/mikeshardmind/async-utils/blob/main/async_utils/task_cache.py
    - https://asyncstdlib.readthedocs.io/en/stable
    """

    def wrapper(coro: AC) -> LRUAsyncCallable[AC]:
        internal_cache: OrderedDict[Hashable, asyncio.Task[T]] = OrderedDict()
        cache_info: CacheInfo = CacheInfo()

        def wrapped(*args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]:
            key = make_key(args, kwargs)
            try:
                task = internal_cache[key]
                internal_cache.move_to_end(key)
                cache_info.hits += 1
                log.debug("Hit on key: %s", key)
                return internal_cache[key]
            except KeyError:
                log.debug("Miss on key: %s", key)
                if maxsize is not None and len(internal_cache) >= maxsize:
                    internal_cache.popitem(last=False)
                internal_cache[key] = task = asyncio.create_task(coro(*args, **kwargs))
                cache_info.misses += 1
                cache_info.currsize = len(internal_cache)
                if ttl is not None:
                    call_after_ttl = partial(
                        asyncio.get_running_loop().call_later,
                        ttl,
                        internal_cache.pop,
                        key,
                    )
                    task.add_done_callback(call_after_ttl)
                return task

        def cache_clear() -> None:
            internal_cache.clear()
            cache_info.clear()

        wrapped.cache_info = lambda: cache_info
        wrapped.cache_clear = cache_clear
        wrapped.cache_parameters = CacheParameters(maxsize=maxsize, ttl=ttl)

        return wrapped

    return wrapper if f is None else wrapper(f)
