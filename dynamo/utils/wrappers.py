import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Generator
from contextlib import contextmanager
from typing import cast

log = logging.getLogger(__name__)


@contextmanager
def time_it(func_name: str) -> Generator[None, None, None]:
    start = time.perf_counter()
    yield
    end = time.perf_counter()
    log.debug("%s took %s seconds", func_name, f"{end - start:.2f}")


def timer[**P, T](func: Callable[P, T] | Callable[P, Awaitable[T]]) -> Callable[P, T] | Callable[P, Awaitable[T]]:
    if asyncio.iscoroutinefunction(func):

        async def async_wrap(*args: P.args, **kwargs: P.kwargs) -> T:
            with time_it(func.__name__):
                return await func(*args, **kwargs)

        return cast(Callable[P, Awaitable[T]], async_wrap)

    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        with time_it(func.__name__):
            return cast(T, func(*args, **kwargs))

    return cast(Callable[P, T], wrapper)
