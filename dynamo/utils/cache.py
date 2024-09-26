from __future__ import annotations

import asyncio
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Coroutine, Hashable, MutableSequence, Sized
from dataclasses import dataclass
from functools import partial
from typing import Any, Protocol, Self, cast, overload

from dynamo._typing import MISSING, P, T

log = logging.getLogger(__name__)

WRAPPER_ASSIGNMENTS = ("__module__", "__name__", "__qualname__", "__doc__", "__annotations__", "__type_params__")
WRAPPER_UPDATES = ("__dict__",)
FAST_TYPES: set[type] = {int, str}


WrappedCoroutine = Callable[P, Coroutine[Any, Any, T]]


@dataclass(slots=True)
class CacheInfo:
    """Cache info for the async_cache decorator."""

    hits: int = 0
    misses: int = 0
    currsize: int = 0
    full: bool = False

    def clear(self) -> None:
        """Reset all counters to zero."""
        self.hits = self.misses = self.currsize = 0
        self.full = False


class HashedSeq(MutableSequence[Any]):
    __slots__: tuple[str, ...] = ("hash_value",)

    def __init__(self, /, *args: Any, _hash: Callable[[object], int] = hash) -> None:
        self[:] = args
        self.hash_value: int = _hash(args)

    def __hash__(self) -> int:
        return self.hash_value


def _make_key(
    args: tuple[Any, ...],
    kwargs: dict[Any, Any],
    kwargs_mark: tuple[object] = (object(),),
    fast_types: set[type] = FAST_TYPES,
    _type: type[type] = type,
    _len: Callable[[Sized], int] = len,
) -> Hashable:
    """
    Make cache key from optionally typed positional and keyword arguments. Structure is flat and hashable.
    Although efficient, it will treat `f(x=1, y=2)` and `f(y=2, x=1)` as distinct calls and will be cached
    separately.
    """
    key: tuple[Any, ...] = args
    if kwargs:
        key += kwargs_mark
        for item in kwargs.items():
            key += item
    return key[0] if _len(key) == 1 and _type(key[0]) in fast_types else HashedSeq(key)


class CachedTask(Protocol[P, T]):
    @property
    def __wrapped__(self) -> WrappedCoroutine[P, T]: ...

    @__wrapped__.setter
    def __wrapped__(self, value: WrappedCoroutine[P, T]) -> None: ...

    @overload
    def __call__(self: Self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]: ...
    @overload
    def __call__(self: CachedTask[P, T], *args: Any, **kwargs: Any) -> asyncio.Task[T]: ...
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]: ...
    def cache_info(self) -> CacheInfo: ...
    def cache_clear(self) -> None: ...
    def cache_parameters(self) -> dict[str, int | float | None]: ...


def update_wrapper(
    wrapper: CachedTask[P, T],
    wrapped: WrappedCoroutine[P, T],
    assigned: tuple[str, ...] = WRAPPER_ASSIGNMENTS,
    updated: tuple[str, ...] = WRAPPER_UPDATES,
) -> CachedTask[P, T]:
    """
    Update a wrapper function to look more like the wrapped function.

    Parameters
    ----------
    wrapper : CachedTask[P, T]
        The wrapper function to be updated.
    wrapped : WrappedCoroutine[P, T]
        The original function being wrapped.
    assigned : tuple of str, optional
        Attribute names to assign from the wrapped function. Default is WRAPPER_ASSIGNMENTS.
    updated : tuple of str, optional
        Attribute names to update from the wrapped function. Default is WRAPPER_UPDATES.

    Returns
    -------
    CachedTask[P, T]
        The updated wrapper function.

    Notes
    -----
    Typically used in decorators to ensure the wrapper function retains the metadata
    of the wrapped function.

    See Also
    --------
    functools.update_wrapper : Similar function for synchronous functions.
    """
    for attr in assigned:
        if hasattr(wrapped, attr):
            setattr(wrapper, attr, getattr(wrapped, attr))
    for attr in updated:
        if hasattr(wrapper, attr) and hasattr(wrapped, attr):
            getattr(wrapper, attr).update(getattr(wrapped, attr))

    wrapper.__wrapped__ = wrapped
    return wrapper


@overload
def async_cache(
    *, maxsize: int | None = 128, ttl: float | None = None
) -> Callable[[WrappedCoroutine[P, T]], CachedTask[P, T]]: ...


@overload
def async_cache(coro: WrappedCoroutine[P, T], /) -> CachedTask[P, T]: ...


def async_cache(
    maxsize: int | WrappedCoroutine[P, T] | None = 128,
    ttl: float | None = None,
) -> CachedTask[P, T] | Callable[[WrappedCoroutine[P, T]], CachedTask[P, T]]:
    """
    Decorator to cache the result of an asynchronous function.

    This decorator caches the result of an asynchronous function to improve performance
    by avoiding redundant computations. It is functionally similar to :func:`functools.cache`
    and :func:`functools.lru_cache` but designed for asynchronous functions.

    Parameters
    ----------
    maxsize : int | WrappedCoroutine[P, T] | None, optional
        The maximum number of items to cache. If a coroutine function is provided directly,
        it is assumed to be the function to be decorated, and `maxsize` defaults to 128.
        If `None`, the cache can grow without bound. Default is 128.
    ttl : float | None, optional
        The time-to-live for cached items in seconds. If `None`, items do not expire.
        Default is None.

    Returns
    -------
    CachedTask[P, T] | Callable[[WrappedCoroutine[P, T]], CachedTask[P, T]]
        If a coroutine function is provided directly, returns the cached task.
        Otherwise, returns a decorator that can be applied to a coroutine function.

    Examples
    --------
    Using the decorator with default parameters:

    >>> @async_cache
    ... async def fetch_data(url: str) -> str:
    ...     # Simulate a network request
    ...     await asyncio.sleep(1)
    ...     return f"Data from {url}"

    Using the decorator with custom parameters:

    >>> @async_cache(maxsize=256, ttl=60.0)
    ... async def fetch_data(url: str) -> str:
    ...     # Simulate a network request
    ...     await asyncio.sleep(1)
    ...     return f"Data from {url}"

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

    def decorator(coro: WrappedCoroutine[P, T]) -> CachedTask[P, T]:
        wrapper = _async_cache_wrapper(coro, maxsize, ttl)
        wrapper.cache_parameters = lambda: {"maxsize": maxsize, "ttl": ttl}
        return update_wrapper(wrapper, coro)

    return decorator


def _async_cache_wrapper(
    coro: WrappedCoroutine[P, T],
    maxsize: int | None,
    ttl: float | None,
) -> CachedTask[P, T]:
    sentinel = MISSING
    make_key = _make_key

    internal_cache: OrderedDict[Hashable, asyncio.Task[T]] = OrderedDict()
    cache_get = internal_cache.get
    cache_len = internal_cache.__len__
    lock = threading.Lock()
    _cache_info = CacheInfo()

    def wrapper(*args: Any, **kwargs: Any) -> asyncio.Task[T]:
        key: Hashable = make_key(args, kwargs)
        with lock:
            result = cache_get(key, sentinel)
            if result is not sentinel:
                log.debug("Cache hit for %s", args)
                _cache_info.hits += 1
                return result
            log.debug("Cache miss for %s", args)
            _cache_info.misses += 1

        task: asyncio.Task[T] = asyncio.create_task(coro(*args, **kwargs))
        if maxsize is not None:
            with lock:
                if key not in internal_cache and _cache_info.full:
                    log.debug("Eviction: LRU cache is full")
                    internal_cache.popitem(last=False)
                internal_cache[key] = task
                internal_cache.move_to_end(key)
                _cache_info.full = cache_len() >= maxsize
                _cache_info.currsize = cache_len()
        else:
            internal_cache[key] = task

        if ttl is not None:

            def evict(k: Hashable) -> None:
                with lock:
                    log.debug("Eviction: TTL expired for %s", k)
                    internal_cache.pop(k, sentinel)

            call_after_ttl = partial(
                asyncio.get_running_loop().call_later,
                ttl,
                evict,
                key,
            )
            task.add_done_callback(call_after_ttl)
        return task

    def cache_info() -> CacheInfo:
        return _cache_info

    def cache_clear() -> None:
        with lock:
            internal_cache.clear()
            _cache_info.clear()

    _wrapper = cast(CachedTask[P, T], wrapper)
    _wrapper.cache_info = cache_info
    _wrapper.cache_clear = cache_clear
    return _wrapper
