from functools import wraps
from typing import Any, Callable, Coroutine, TypeVar

T = TypeVar("T")


def async_cache(
    func: Callable[..., Coroutine[Any, Any, T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
    cache: dict[str, T] = {}

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        # Generate a unique key based on function arguments
        key = f"{func.__module__}.{func.__name__}:{args}:{kwargs}"

        # Check if the result is in the cache
        if key in cache:
            return cache[key]

        # Call the function and store the result in the cache
        result = await func(*args, **kwargs)
        cache[key] = result
        return result

    def invalidate(*args: Any, **kwargs: Any) -> None:
        """Invalidate a specific cache entry."""
        key = f"{func.__module__}.{func.__name__}:{args}:{kwargs}"
        if key in cache:
            del cache[key]

    def invalidate_all() -> None:
        """Clear the entire cache."""
        cache.clear()

    # Attach the invalidate methods to the wrapper function
    wrapper.invalidate = invalidate
    wrapper.invalidate_all = invalidate_all

    return wrapper
