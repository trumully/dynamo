import datetime

import hypothesis.strategies as st
from dateutil.relativedelta import relativedelta
from hypothesis import given

from dynamo.utils import time_utils


def aware_datetime(*args: int) -> datetime.datetime:
    """Create an aware datetime with UTC timezone.

    Parameters
    ----------
    *args: int
        Time data to create the datetime. Assumed to be in the order of year, month, day, hour, minute, second.

    Returns
    -------
    datetime.datetime
        An aware datetime with UTC timezone.
    """
    return datetime.datetime(*args, tzinfo=datetime.UTC)


def test_human_timedelta_basic() -> None:
    """Tests that the basic functionality of human_timedelta works as expected."""
    # year, month, day, hour, minute, second
    some_datetime = (2023, 1, 1, 12, 0, 0)
    now = aware_datetime(*some_datetime)

    assert time_utils.human_timedelta(now, now) == "now"
    assert time_utils.human_timedelta(now + datetime.timedelta(seconds=5), now) == "5 seconds"
    assert time_utils.human_timedelta(now - datetime.timedelta(minutes=5), now) == "5 minutes ago"
    assert time_utils.human_timedelta(now + relativedelta(years=1, months=2), now) == "1 year and 2 months"


@given(
    dt=st.datetimes(timezones=st.just(datetime.UTC)),
    source=st.datetimes(timezones=st.just(datetime.UTC)),
    accuracy=st.integers() | st.none(),
    brief=st.booleans(),
    suffix=st.booleans(),
)
def test_human_timedelta_properties(
    dt: datetime.datetime, source: datetime.datetime, accuracy: int | None, brief: bool, suffix: bool
) -> None:
    """Tests that all the properties of human_timedelta work as expected."""
    result = time_utils.human_timedelta(dt, source, accuracy, brief, suffix)

    # Validate output
    assert isinstance(result, str)
    assert result != ""

    # In case of same datetime, other cases are irrelevant
    if dt == source:
        assert result == "now"
        return

    # Check accuracy
    if accuracy is not None:
        parts = result.split()
        time_parts = [p for p in parts if any(c.isdigit() for c in p)]
        # Accuracy gets converted within the function
        if accuracy < 1:
            accuracy = 3
        assert len(time_parts) <= accuracy

    # Check if brief is correctly applied
    attrs: list[tuple[str, str]] = [
        ("year", "y"),
        ("month", "mo"),
        ("day", "d"),
        ("hour", "h"),
        ("minute", "m"),
        ("second", "s"),
    ]
    split_result = result.split()
    for long, short in attrs:
        if long in split_result:
            assert not brief
        elif short in split_result:
            assert brief

        assert not (long in split_result and short in split_result)
