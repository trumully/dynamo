import datetime

from dateutil.relativedelta import relativedelta

from dynamo.utils.format import format_dt, human_join, plural


def human_timedelta(
    dt: datetime.datetime,
    source: datetime.datetime | None = None,
    accuracy: int | None = 3,
    brief: bool = False,
    suffix: bool = True,
) -> str:
    """Format a datetime.datetime object into a human-readable string.

    Parameters
    ----------
    dt : datetime.datetime
        The datetime to format.
    source : datetime.datetime | None, optional
        The source datetime to use for the relative time. Defaults to the current datetime.
    accuracy : int | None, optional
        The number of time units to include in the output. Defaults to 3.
    brief : bool, optional
        Whether to use a brief format. Defaults to False.
    suffix : bool, optional
        Whether to include the suffix (e.g. "ago"). Defaults to True.

    Returns
    -------
    str
        A human-readable string representing the time delta.

    Examples
    --------
    >>> human_timedelta(datetime.datetime(2024, 1, 1), accuracy=2)
    '1 year and 2 months ago'
    >>> human_timedelta(datetime.datetime(2024, 1, 1), accuracy=2, brief=True)
    '1y 2mo ago'
    >>> human_timedelta(datetime.datetime(2024, 1, 1), accuracy=2, suffix=False)
    '1 year and 2 months'
    """
    if accuracy is not None and accuracy < 1:
        accuracy = 1

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    if (now := source or datetime.datetime.now(datetime.timezone.utc)).tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)

    now = now.replace(microsecond=0).astimezone(datetime.timezone.utc)
    dt = dt.replace(microsecond=0).astimezone(datetime.timezone.utc)

    if dt > now:
        delta = relativedelta(dt, now)
        output_suffix = ""
    else:
        delta = relativedelta(now, dt)
        output_suffix = " ago" if suffix else ""

    attrs = [("year", "y"), ("month", "mo"), ("day", "d"), ("hour", "h"), ("minute", "m"), ("second", "s")]

    output = []
    for attr, brief_attr in attrs:
        if not (elem := getattr(delta, attr + "s")):
            continue

        if attr == "day" and (weeks := delta.weeks):
            elem -= weeks * 7
            output.append(f"{weeks}w" if brief else f"{plural(weeks):week}")

        if elem > 0:
            output.append(f"{elem}{brief_attr}" if brief else f"{plural(elem):{attr}}")

    if accuracy is not None:
        output = output[:accuracy]

    if len(output) == 0:
        return "now"

    return (human_join(output, conjunction="and") if not brief else " ".join(output)) + output_suffix


def format_relative(dt: datetime.datetime) -> str:
    return format_dt(dt, "R")
