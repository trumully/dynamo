import asyncio
import logging
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from functools import wraps
from typing import cast, overload

from dynamo.typedefs import CoroFunction

log = logging.getLogger(__name__)


@contextmanager
def time_it(func_name: str) -> Generator[None]:
    start = time.perf_counter()
    yield
    end = time.perf_counter()
    log.debug("%s took %s seconds", func_name, f"{end - start:.2f}")


@overload
def timer[**P, T](func: CoroFunction[P, T]) -> CoroFunction[P, T]: ...


@overload
def timer[**P, T](func: Callable[P, T]) -> Callable[P, T]: ...


def timer[**P, T](func: Callable[P, T] | CoroFunction[P, T]) -> Callable[P, T] | CoroFunction[P, T]:
    """Time execution of a function or coroutine"""

    async def async_wrap(*args: P.args, **kwargs: P.kwargs) -> T:
        with time_it(func.__name__):
            return await func(*args, **kwargs)

    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        with time_it(func.__name__):
            return cast(T, func(*args, **kwargs))

    return async_wrap if asyncio.iscoroutinefunction(func) else wrapper


def executor_function[**P, T](func: Callable[P, T]) -> CoroFunction[P, T]:
    """Send sync function to thread"""

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        return await asyncio.to_thread(func, *args, **kwargs)

    return wrapper
