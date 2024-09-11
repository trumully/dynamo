import asyncio
import logging
import time
from functools import wraps
from typing import Awaitable, Callable, ParamSpec, TypeVar, overload

log = logging.getLogger(__name__)

R = TypeVar("R")
P = ParamSpec("P")
F = TypeVar("F", bound=Callable[P, R])
A = TypeVar("A", bound=Callable[P, Awaitable[R]])


@overload
def timer(func: F) -> F: ...
@overload
def timer(func: A) -> A: ...
def timer(func: F | A) -> F | A:
    """Timer wrapper for functions"""

    @wraps(func)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        end = time.perf_counter()
        log.debug("Function %s took %f seconds", func.__name__, end - start)
        return result

    @wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        log.debug("Function %s took %f seconds", func.__name__, end - start)
        return result

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
