import asyncio
import logging
import time
from collections.abc import Callable
from functools import wraps

from dynamo._typing import AC, P, T

log = logging.getLogger(__name__)


def timer(func: Callable[P, T] | AC[T]) -> Callable[P, T] | AC[T]:
    """Timer wrapper for functions"""

    @wraps(func)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        end = time.perf_counter()
        log.debug("%s: %s", func.__name__, f"{(end - start) * 1000:.2f}ms")
        return result

    @wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        log.debug("%s: %s", func.__name__, f"{(end - start) * 1000:.2f}ms")
        return result

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
