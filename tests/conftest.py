import asyncio

import pytest

from dynamo._evt_policy import get_event_loop_policy


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """Set the event loop policy for all async tests."""
    policy = get_event_loop_policy()
    return policy()
