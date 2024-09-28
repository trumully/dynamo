import asyncio
import logging
import time
from collections.abc import Callable, Coroutine, Generator
from contextlib import contextmanager
from typing import Any, Protocol, cast, overload

log = logging.getLogger(__name__)


@contextmanager
def time_it(func_name: str) -> Generator[None, None, None]:
    start = time.perf_counter()
    yield
    end = time.perf_counter()
    log.debug("%s took %s seconds", func_name, f"{end - start:.2f}")


class WrappedCoroutine[**P, T](Protocol):
    __name__: str

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Coroutine[Any, Any, T]: ...


@overload
def timer[**P, T](func: WrappedCoroutine[P, T]) -> WrappedCoroutine[P, T]: ...


@overload
def timer[**P, T](func: Callable[P, T]) -> Callable[P, T]: ...


def timer[**P, T](func: Callable[P, T] | WrappedCoroutine[P, T]) -> Callable[P, T] | WrappedCoroutine[P, T]:
    if asyncio.iscoroutinefunction(func):

        async def async_wrap(*args: P.args, **kwargs: P.kwargs) -> T:
            with time_it(func.__name__):
                return await func(*args, **kwargs)

        return async_wrap

    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        with time_it(func.__name__):
            return cast(T, func(*args, **kwargs))

    return wrapper
