import datetime

from dateutil.relativedelta import relativedelta

from dynamo.ext.utils.format import human_join, plural


def human_timedelta(
    dt: datetime.datetime,
    source: datetime.datetime | None = None,
    accuracy: int | None = 3,
    brief: bool = False,
    suffix: bool = True,
) -> str:
    now = source or datetime.datetime.now(datetime.timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)

    now = now.replace(microsecond=0)
    dt = dt.replace(microsecond=0)

    now = now.astimezone(datetime.timezone.utc)
    dt = dt.astimezone(datetime.timezone.utc)

    if dt > now:
        delta = relativedelta(dt, now)
        output_suffix = ""
    else:
        delta = relativedelta(now, dt)
        output_suffix = " ago" if suffix else ""

    attrs = [
        ("year", "y"),
        ("month", "mo"),
        ("day", "d"),
        ("hour", "h"),
        ("minute", "m"),
        ("second", "s"),
    ]

    output = []
    for attr, brief_attr in attrs:
        elem = getattr(delta, attr + "s")
        if not elem:
            continue

        if attr == "day":
            weeks = delta.weeks
            if weeks:
                elem -= weeks * 7
                output.append(
                    format(plural(weeks), "week") if not brief else f"{weeks}w"
                )

        if elem <= 0:
            continue

        output.append(f"{elem}{brief_attr}" if brief else format(plural(elem), attr))

    if accuracy is not None:
        output = output[:accuracy]

    if len(output) == 0:
        return "now"

    return (
        human_join(output, final="and") if not brief else " ".join(output)
    ) + output_suffix
