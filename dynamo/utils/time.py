import datetime

from dateutil.relativedelta import relativedelta

from dynamo.utils.format import human_join, plural


def human_timedelta(
    dt: datetime.datetime,
    source: datetime.datetime | None = None,
    accuracy: int | None = 3,
    brief: bool = False,
    suffix: bool = True,
) -> str:
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
