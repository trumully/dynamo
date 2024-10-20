import asyncio
from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from dynamo.utils.cache import FAST_TYPES, CachedTask, _make_key, async_cache  # type: ignore

fast_type_values = st.one_of(
    st.integers(), st.text(), st.floats(allow_nan=False, allow_infinity=False), st.binary(), st.none()
)
args_strategy = st.lists(fast_type_values, max_size=5).map(tuple)
kwargs_strategy = st.dictionaries(st.text(min_size=1), fast_type_values, max_size=5)


def create_async_cacheable(maxsize: int | None = 128, sleep_time: float = 1e-3) -> CachedTask[[int], int]:
    @async_cache(maxsize=maxsize)
    async def async_cacheable(x: int) -> int:
        await asyncio.sleep(sleep_time)
        return x * 2

    return async_cacheable


@pytest.mark.asyncio
@settings(deadline=None)
@given(first=st.integers(min_value=0, max_value=10), second=st.integers(min_value=0, max_value=10))
async def test_async_cache_basic(first: int, second: int) -> None:
    """Tests that functions are cached and hits/misses are counted correctly."""
    assume(first != second)

    async_cacheable = create_async_cacheable()

    # Test cache hit
    result_a = await async_cacheable(first)
    assert async_cacheable.cache_info().misses == 1
    result_b = await async_cacheable(first)
    assert result_a == result_b == first * 2
    assert async_cacheable.cache_info().hits == 1

    # Test cache miss
    result_c = await async_cacheable(second)
    assert result_c == second * 2
    assert async_cacheable.cache_info().hits == 1
    assert async_cacheable.cache_info().misses == 2


@pytest.mark.asyncio
@settings(deadline=None, max_examples=10)
@given(st.sets(st.integers(), min_size=1, max_size=10))
async def test_async_cache_property(inputs: set[int]) -> None:
    """Tests that the cache properties are correctly updated."""

    async_cacheable_sized = create_async_cacheable(maxsize=5)

    call_count: int = 0

    results: list[int] = []
    for i in inputs:
        result: int = await async_cacheable_sized(i)
        results.append(result)
        call_count += 1

    assert results == [x * 2 for x in inputs]

    cache_info = async_cacheable_sized.cache_info()
    assert call_count == cache_info.hits + cache_info.misses


@pytest.mark.asyncio
@settings(deadline=None, max_examples=10)
@given(inputs=st.sets(st.integers(min_value=0, max_value=5), min_size=1, max_size=5))
async def test_async_cache_maxsize_enforcement(inputs: set[int]) -> None:
    """Test that the cache enforces the maxsize."""

    async_cacheable_sized = create_async_cacheable(maxsize=5)

    for i in inputs:
        await async_cacheable_sized(i)

    cache_info = async_cacheable_sized.cache_info()
    assert cache_info.currsize <= 5
    assert cache_info.currsize == min(len(set(inputs)), 5)


@pytest.mark.asyncio
@settings(deadline=None, max_examples=10)
@given(inputs=st.sets(st.integers(min_value=0, max_value=5), min_size=1, max_size=5))
async def test_async_cache_unbounded(inputs: set[int]) -> None:
    async_cacheable_unbounded = create_async_cacheable(maxsize=None)

    for i in inputs:
        await async_cacheable_unbounded(i)

    cache_info = async_cacheable_unbounded.cache_info()
    assert not cache_info.full
    assert cache_info.currsize == len(inputs)


@pytest.mark.asyncio
@settings(deadline=None, max_examples=10)
@given(st.sets(st.integers(), min_size=1, max_size=5))
async def test_async_cache_clear(inputs: set[int]) -> None:
    """Tests that the cache can be cleared."""

    async_cacheable_sized = create_async_cacheable(maxsize=5)

    results: list[int] = []
    for i in inputs:
        result: int = await async_cacheable_sized(i)
        results.append(result)

    assert async_cacheable_sized.cache_info().currsize > 0
    await async_cacheable_sized.cache_clear()
    assert async_cacheable_sized.cache_info().currsize == 0


@pytest.mark.asyncio
@settings(deadline=None, max_examples=10)
@given(inputs=st.sets(st.integers(min_value=1, max_value=10), min_size=5, max_size=10))
async def test_async_cache_stampede_resistance(inputs: set[int]) -> None:
    """Test that the cache is resistant to cache stampede."""

    call_count = 0

    @async_cache
    async def slow_function(x: int) -> int:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.001)
        return x * 2

    async def make_request(x: int):
        return await slow_function(x)

    tasks = [make_request(x) for x in inputs for _ in range(3)]  # 3 concurrent requests per input
    results = await asyncio.gather(*tasks)

    # Check results
    assert results == [x * 2 for x in inputs for _ in range(3)]

    # Check that the function was called only once per unique input
    assert call_count == len(inputs)

    # Check cache info
    cache_info = slow_function.cache_info()
    assert cache_info.hits == len(inputs) * 3 - len(inputs)
    assert cache_info.misses == len(inputs)


@given(args=args_strategy)
def test_make_key_with_only_args(args: tuple[Any, ...]) -> None:
    """Test with only positional arguments"""
    key1 = _make_key(args, {}, fast_types=FAST_TYPES)
    key2 = _make_key(args, {}, fast_types=FAST_TYPES)
    assert key1 == key2


@given(kwargs=kwargs_strategy)
def test_make_key_order_independence(kwargs: dict[Any, Any]) -> None:
    """Test that keyword argument order doesn't affect the key"""
    key1 = _make_key((), kwargs, fast_types=FAST_TYPES)
    key2 = _make_key((), dict(reversed(list(kwargs.items()))), fast_types=FAST_TYPES)
    assert key1 == key2


@given(args=args_strategy, kwargs=kwargs_strategy)
def test_make_key_with_args_and_kwargs(args: tuple[Any, ...], kwargs: dict[Any, Any]) -> None:
    """Test with both positional and keyword arguments"""
    key1 = _make_key(args, kwargs, fast_types=FAST_TYPES)
    key2 = _make_key(args, dict(reversed(list(kwargs.items()))), fast_types=FAST_TYPES)
    assert key1 == key2


@given(kwargs=kwargs_strategy, extra_key=st.text(min_size=1), extra_value=fast_type_values)
def test_make_key_different_values(kwargs: dict[Any, Any], extra_key: str, extra_value: Any) -> None:
    """Test that different values produce different keys"""
    key1 = _make_key((), kwargs, fast_types=FAST_TYPES)

    extra_key = "unique_key_for_test"

    kwargs[extra_key] = extra_value
    key2 = _make_key((), kwargs, fast_types=FAST_TYPES)
    assert key1 != key2
