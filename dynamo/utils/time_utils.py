import datetime

from dateutil.relativedelta import relativedelta

from dynamo.utils.format import format_datetime, human_join, plural


def parse_hour(hour: str) -> int | None:
    hour = hour.replace(" ", "")

    hour_as_int = -1

    # am/pm
    if hour.endswith("m"):
        hour, suffix = hour[:-2], hour[-2:]
        if suffix.casefold() not in {"am", "pm"} or len(hour) > 2:
            return None
        try:
            hour_as_int = int(hour)
        except ValueError:
            return None
        if suffix == "am" and hour_as_int == 12:
            hour_as_int = 0
        elif suffix == "pm" and hour_as_int != 12:
            hour_as_int += 12

    else:
        try:
            hour_as_int = int(hour)
        except ValueError:
            return None

    return hour_as_int if 0 <= hour_as_int <= 23 else None


def human_timedelta(
    dt: datetime.datetime,
    source: datetime.datetime | None = None,
    accuracy: int | None = 3,
    brief: bool = False,
    suffix: bool = True,
) -> str:
    """Format a datetime.datetime object into a human-readable string."""
    if accuracy is not None and accuracy < 1:
        accuracy = 1

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)

    if (now := source or datetime.datetime.now(datetime.UTC)).tzinfo is None:
        now = now.replace(tzinfo=datetime.UTC)

    now = now.replace(microsecond=0).astimezone(datetime.UTC)
    dt = dt.replace(microsecond=0).astimezone(datetime.UTC)

    if dt > now:
        delta = relativedelta(dt, now)
        output_suffix = ""
    else:
        delta = relativedelta(now, dt)
        output_suffix = " ago" if suffix else ""

    attrs = [("year", "y"), ("month", "mo"), ("day", "d"), ("hour", "h"), ("minute", "m"), ("second", "s")]

    output: list[str] = []
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
    return format_datetime(dt, "R")
