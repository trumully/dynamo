import asyncio

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from dynamo.utils.cache import async_cache


@pytest.mark.asyncio
@settings(deadline=None)
@given(first=st.integers(min_value=0, max_value=10), second=st.integers(min_value=0, max_value=10))
async def test_future_lru_cache_basic(first: int, second: int) -> None:
    """Tests that functions are cached and hits/misses are counted correctly."""
    assume(first != second)

    @async_cache
    async def async_cacheable(x: int) -> int:
        await asyncio.sleep(0.001)
        return x * 2

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
@given(st.lists(st.integers(), min_size=1, max_size=10))
async def test_future_lru_cache_property(inputs: list[int]) -> None:
    """Tests that the cache properties are correctly updated."""

    @async_cache(maxsize=5)
    async def async_cacheable_sized(x: int) -> int:
        await asyncio.sleep(0.001)
        return x * 2

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
@given(st.lists(st.integers(), min_size=1, max_size=5))
async def test_future_lru_cache_clear(inputs: list[int]) -> None:
    """Tests that the cache can be cleared."""

    @async_cache(maxsize=5)
    async def async_cacheable_sized(x: int) -> int:
        await asyncio.sleep(0.001)
        return x * 2

    results: list[int] = []
    for i in inputs:
        result: int = await async_cacheable_sized(i)
        results.append(result)

    assert async_cacheable_sized.cache_info().currsize > 0
    async_cacheable_sized.cache_clear()
    assert async_cacheable_sized.cache_info().currsize == 0


@pytest.mark.asyncio
@settings(deadline=None, max_examples=10)
@given(inputs=st.lists(st.integers(min_value=0, max_value=5), min_size=1, max_size=5))
async def test_maxsize_enforcement(inputs: list[int]) -> None:
    """Test that the cache enforces the maxsize."""

    @async_cache(maxsize=5)
    async def async_cacheable_sized(x: int) -> int:
        await asyncio.sleep(0.001)
        return x * 2

    for i in inputs:
        await async_cacheable_sized(i)

    cache_info = async_cacheable_sized.cache_info()
    assert cache_info.currsize <= 5
    assert cache_info.currsize == min(len(set(inputs)), 5)


@pytest.mark.asyncio
@settings(deadline=None, max_examples=10)
@given(inputs=st.lists(st.integers(min_value=1, max_value=10), min_size=5, max_size=10))
async def test_future_lru_cache_stampede_resistance(inputs: list[int]) -> None:
    """Test that the cache is resistant to cache stampede."""

    call_count = 0

    @async_cache
    async def slow_function(x: int) -> int:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.001)  # Reduce sleep time
        return x * 2

    # Simulate multiple concurrent requests for the same keys
    async def make_request(x: int):
        return await slow_function(x)

    tasks = [make_request(x) for x in inputs for _ in range(3)]  # 3 concurrent requests per input
    results = await asyncio.gather(*tasks)

    # Check results
    assert results == [x * 2 for x in inputs for _ in range(3)]

    # Check that the function was called only once per unique input
    assert call_count == len(set(inputs))

    # Check cache info
    cache_info = slow_function.cache_info()
    assert cache_info.hits == len(inputs) * 3 - len(set(inputs))
    assert cache_info.misses == len(set(inputs))
