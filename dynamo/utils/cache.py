from __future__ import annotations

import asyncio
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Coroutine, Hashable, Sized
from dataclasses import dataclass
from functools import partial
from typing import Any, Concatenate, Generic, Protocol, Self

from dynamo._typing import MISSING, P, S, S_co, T, T_co

log = logging.getLogger(__name__)

WRAPPER_ASSIGNMENTS = ("__module__", "__name__", "__qualname__", "__doc__", "__annotations__", "__type_params__")
WRAPPER_UPDATES = ("__dict__",)


@dataclass(slots=True)
class CacheInfo:
    """Cache info for the async_lru_cache decorator."""

    hits: int = 0
    misses: int = 0
    currsize: int = 0
    full: bool = False

    def clear(self) -> None:
        """Reset all counters to zero."""
        self.hits = self.misses = self.currsize = 0
        self.full = False


class HashedSeq(list[Any]):
    __slots__ = ("hash_value",)

    def __init__(self, *args: Any, hash: Callable[[object], int] = hash) -> None:  # noqa: A002
        self[:] = args
        self.hash_value: int = hash(args)

    def __hash__(self) -> int:  # type: ignore
        return self.hash_value


def _make_key(
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


class AsyncMethod(Protocol[S_co, P, T_co]):
    def __call__(self, __self: Self, *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, T_co]: ...


class LRUAsyncMethod(Generic[S, P, T]):
    __wrapped__: Callable[Concatenate[S, P], Callable[..., AsyncMethod[S, P, T]]]

    def __call__(self, __self: Self, *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, T]: ...
    def cache_info(self) -> CacheInfo: ...
    def cache_clear(self) -> None: ...
    def cache_parameters(self) -> dict[str, int | float | None]: ...


class LRUAsyncCallable(Generic[P, T]):
    __wrapped__: Callable[P, Callable[Concatenate[Any, P], Coroutine[Any, Any, T]]]

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]: ...
    def cache_info(self) -> CacheInfo: ...
    def cache_clear(self) -> None: ...
    def cache_parameters(self) -> dict[str, int | float | None]: ...


def update_wrapper(
    wrapper: LRUAsyncCallable[P, T] | LRUAsyncMethod[S, P, T],
    wrapped: Callable[Concatenate[S, P], Coroutine[Any, Any, T]],
    assigned: tuple[str, ...] = WRAPPER_ASSIGNMENTS,
    updated: tuple[str, ...] = WRAPPER_UPDATES,
) -> LRUAsyncCallable[P, T] | LRUAsyncMethod[Any, P, T]:
    for attr in assigned:
        try:
            value = getattr(wrapped, attr)
        except AttributeError:
            pass
        else:
            setattr(wrapper, attr, value)
    for attr in updated:
        getattr(wrapper, attr).update(getattr(wrapped, attr, {}))

    wrapper.__wrapped__ = wrapped
    return wrapper


def async_cache(
    maxsize: int
    | Callable[P, Coroutine[Any, Any, T]]
    | Callable[Concatenate[S, P], Coroutine[Any, Any, T]]
    | None = 128,
    ttl: float | None = None,
) -> Any:
    """Decorator to cache the result of an asynchronous function.

    Functionally similar to `functools.cache` & `functools.lru_cache` but non-blocking.

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

    if isinstance(maxsize, int):
        maxsize = max(maxsize, 0)
    elif callable(maxsize):
        coro, maxsize = maxsize, 128
        wrapper = _async_cache_wrapper(coro, maxsize, ttl)
        wrapper.cache_parameters = lambda: {"maxsize": maxsize, "ttl": ttl}
        return update_wrapper(wrapper, coro)
    else:
        error = "Expected first argument to be an integer, a callable, or None"
        raise TypeError(error)

    def decorator(
        coro: Callable[P, Coroutine[Any, Any, T]] | Callable[Concatenate[S, P], Coroutine[Any, Any, T]],
    ) -> LRUAsyncCallable[P, T] | LRUAsyncMethod[S, P, T]:
        wrapper = _async_cache_wrapper(coro, maxsize, ttl)
        wrapper.cache_parameters = lambda: {"maxsize": maxsize, "ttl": ttl}
        return update_wrapper(wrapper, coro)

    return decorator


def _async_cache_wrapper(
    coro: Callable[P, Coroutine[Any, Any, T]] | Callable[Concatenate[S, P], Coroutine[Any, Any, T]],
    maxsize: int | None,
    ttl: float | None,
) -> LRUAsyncCallable[P, T] | LRUAsyncMethod[S, P, T]:
    sentinel = MISSING
    make_key = _make_key

    internal_cache: OrderedDict[Hashable, asyncio.Task[T]] = OrderedDict()
    cache_get = internal_cache.get
    cache_len = internal_cache.__len__
    lock = threading.Lock()
    _cache_info = CacheInfo()

    if maxsize == 0:

        def wrapper(*args: Any, **kwargs: Any) -> asyncio.Task[T]:
            log.debug("Cache miss for %s", args)
            _cache_info.misses += 1
            task: asyncio.Task[T] = asyncio.create_task(coro(*args, **kwargs))
            if ttl is not None:
                call_after_ttl = partial(
                    asyncio.get_running_loop().call_later,
                    ttl,
                    internal_cache.pop,
                    MISSING,
                )
                task.add_done_callback(call_after_ttl)
            return task

    elif maxsize is None:

        def wrapper(*args: Any, **kwargs: Any) -> asyncio.Task[T]:
            key = make_key(args, kwargs)
            result = cache_get(key, sentinel)
            if result is not sentinel:
                log.debug("Cache hit for %s", args)
                _cache_info.hits += 1
                return result
            task: asyncio.Task[T] = asyncio.create_task(coro(*args, **kwargs))
            internal_cache[key] = task
            log.debug("Cache miss for %s", args)
            _cache_info.misses += 1
            if ttl is not None:
                call_after_ttl = partial(
                    asyncio.get_running_loop().call_later,
                    ttl,
                    internal_cache.pop,
                    key,
                )
                task.add_done_callback(call_after_ttl)
            return task

    else:

        def wrapper(*args: Any, **kwargs: Any) -> asyncio.Task[T]:
            key = make_key(args, kwargs)
            with lock:
                link = cache_get(key)
                if link is not None:
                    log.debug("Cache hit for %s", args)
                    _cache_info.hits += 1
                    return link
                log.debug("Cache miss for %s", args)
                _cache_info.misses += 1
            task: asyncio.Task[T] = asyncio.create_task(coro(*args, **kwargs))
            with lock:
                if key in internal_cache:
                    pass
                elif _cache_info.full:
                    internal_cache.popitem(last=False)
                    internal_cache[key] = task
                    internal_cache.move_to_end(key)
                else:
                    internal_cache[key] = task
                    _cache_info.full = cache_len() >= maxsize
                _cache_info.currsize = cache_len()
            return task

    def cache_info() -> CacheInfo:
        return _cache_info

    def cache_clear() -> None:
        internal_cache.clear()
        _cache_info.clear()

    wrapper.cache_info = cache_info
    wrapper.cache_clear = cache_clear
    return wrapper
