import asyncio
import logging
import time
from functools import wraps
from typing import Any, Awaitable, Callable, ParamSpec, TypeVar, overload

from dynamo.utils.time import inferred_conversion

log = logging.getLogger(__name__)

P = ParamSpec("P")
F = TypeVar("F", bound=Callable[P, Any])
A = TypeVar("A", bound=Callable[P, Awaitable[Any]])


@overload
def timer(func: F) -> F: ...  # Sync
@overload
def timer(func: A) -> A: ...  # Async
def timer(func: Callable[P, Any]) -> Callable[P, Any]:
    """Timer wrapper for functions"""

    @wraps(func)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        end = time.perf_counter()
        log.debug("%s: %s", func.__name__, inferred_conversion(end - start, 1000, "ms"))
        return result

    @wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        log.debug("%s: %s", func.__name__, inferred_conversion(end - start, 1000, "ms"))
        return result

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
