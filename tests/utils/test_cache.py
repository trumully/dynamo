import asyncio

import pytest
from hypothesis import given
from hypothesis import strategies as st

import dynamo.utils.cache


@pytest.mark.asyncio
async def test_async_lru_cache_basic() -> None:
    """Tests that functions are cached and hits/misses are counted correctly."""

    @dynamo.utils.cache.async_lru_cache()
    async def example_func(x: int):
        await asyncio.sleep(0.1)
        return x * 2

    # Test cache hit
    result_a = await example_func(5)
    result_b = await example_func(5)
    assert result_a == result_b == 10
    assert example_func.cache_info().hits == 1
    assert example_func.cache_info().misses == 1

    # Test cache miss
    result_c = await example_func(6)
    assert result_c == 12
    assert example_func.cache_info().hits == 1
    assert example_func.cache_info().misses == 2


@pytest.mark.asyncio
@given(st.lists(st.integers(), min_size=1, max_size=10))
async def test_async_lru_cache_property(inputs: list[int]) -> None:
    """Tests that the cache properties are correctly updated."""
    call_count: int = 0

    @dynamo.utils.cache.async_lru_cache(maxsize=5)
    async def cached_func(x: int):
        await asyncio.sleep(0.01)
        return x * 2

    results: list[int] = []
    for i in inputs:
        result: int = await cached_func(i)
        results.append(result)
        call_count += 1

    assert results == [x * 2 for x in inputs]

    cache_info = cached_func.cache_info()
    assert call_count == cache_info.hits + cache_info.misses


@pytest.mark.asyncio
@given(st.lists(st.integers(), min_size=1, max_size=10))
async def test_async_lru_cache_clear(inputs: list[int]) -> None:
    """Tests that the cache can be cleared."""

    @dynamo.utils.cache.async_lru_cache(maxsize=5)
    async def cached_func(x: int):
        await asyncio.sleep(0.01)
        return x * 2

    results: list[int] = []
    for i in inputs:
        result: int = await cached_func(i)
        results.append(result)

    assert cached_func.cache_info().currsize > 0
    cached_func.cache_clear_all()
    assert cached_func.cache_info().currsize == 0
