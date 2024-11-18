import asyncio
import logging
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from functools import wraps

from dynamo.types import CoroFunction

log = logging.getLogger(__name__)


@contextmanager
def time_it(func_name: str) -> Generator[None]:
    start = time.perf_counter()
    yield
    end = time.perf_counter()
    log.debug("%s took %s seconds", func_name, f"{end - start:.2f}")


def executor_function[**P, T](func: Callable[P, T]) -> CoroFunction[P, T]:
    """Send sync function to thread."""

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        return await asyncio.to_thread(func, *args, **kwargs)

    return wrapper
