import inspect
import logging
from io import StringIO

import pytest

from dynamo.utils import wrappers


@pytest.mark.asyncio
async def test_executor_function() -> None:
    """Test the executor_function decorator"""

    @wrappers.executor_function
    def test_function() -> str:
        return "test"

    assert inspect.iscoroutinefunction(test_function)
    assert await test_function() == "test"


@pytest.mark.asyncio
async def test_timer(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Test the timer decorator"""

    @wrappers.timer
    def test_function() -> str:
        return "test"

    @wrappers.timer
    async def async_test_function() -> str:
        return "test"

    # Capture log output
    log_capture = StringIO()
    monkeypatch.setattr("sys.stdout", log_capture)
    monkeypatch.setattr("sys.stderr", log_capture)

    # Set log level to capture all logs
    caplog.set_level(logging.DEBUG)

    result = test_function()
    result_async = await async_test_function()

    assert result == result_async == "test"

    assert any("test_function took" in record.message for record in caplog.records)
    assert any("seconds" in record.message for record in caplog.records)
