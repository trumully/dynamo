from __future__ import annotations

from collections import deque
from datetime import timedelta
from functools import lru_cache
from typing import Literal

import arrow
import discord
import pytz
from discord import app_commands
from discord.app_commands import Choice, Group, Range, Transform

from dynamo.bot import Interaction
from dynamo.extensions.settings import get_timezone_from_user
from dynamo.types import BotExports
from dynamo.utils import time_utils
from dynamo.utils.cache import task_cache
from dynamo.utils.helper import process_async_iterable
from dynamo.utils.transformer import ScheduledEventTransformer

MIN_YEAR = (arrow.Arrow.now(pytz.UTC) - timedelta(days=2)).datetime.year
MAX_YEAR = MIN_YEAR + 3

DATE_FMT = r"%Y-%m-%d %H:%M"


@task_cache(ttl=900)
async def get_interested(event: discord.ScheduledEvent) -> str:
    """|coro|

    Get a list of users interested in an event

    Returns
    -------
    str
        A formatted string of users interested in the event.
        `[Event Name](Event URL) <@User1> <@User2> ...`
        Designed to be copied and pasted.
    """
    users = await process_async_iterable(event.users())
    return f"`[{event.name}]({event.url}) {" ".join(u.mention for u in users) or "No users found"}`"


events_group = Group(name="event", description="Event related commands")


@app_commands.describe(
    event="The event to get attendees for. Either the event name or ID.",
    ephemeral="Attempt to send output as an ephemeral/temporary response",
)
@app_commands.guild_only()
@events_group.command(name="interested")
async def event_interested(
    itx: Interaction,
    event: Transform[discord.ScheduledEvent, ScheduledEventTransformer],
    ephemeral: Literal["True", "False"] = "True",
) -> None:
    """Get attendees of an event"""
    interested: str = await get_interested(event)
    await itx.response.send_message(content=interested, ephemeral=ephemeral == "True")


time_group = Group(name="time", description="Time related commands")


@lru_cache(64)
def en_hour_to_str(hour: int) -> str:
    if hour == 0:
        return "12am"
    if hour == 12:
        return "12pm"

    return f"{hour - 12}pm" if hour > 12 else f"{hour}am"


@time_group.command(name="relative", description="Get the time relative to now")
async def get_time_relative(
    itx: Interaction,
    year: Range[int, MIN_YEAR, MAX_YEAR] = -1,
    month: Range[int, 1, 12] = -1,
    day: Range[int, 1, 31] = -1,
    hour: Range[str, 0, 5] = "",
    minute: Range[int, 0, 59] = -1,
) -> None:
    send = itx.response.send_message

    if (hour_as_int := time_utils.parse_hour(hour)) is None:
        await send("Not a valid hour", ephemeral=True)
        return

    time_mapping = {
        "year": year,
        "month": month,
        "day": day,
        "hour": hour_as_int,
        "minute": minute,
    }
    time_mapping = {k: v for k, v in time_mapping.items() if v >= 0}

    raw_timezone = get_timezone_from_user(itx.client.conn, itx.user.id)
    user_timezone = pytz.timezone(raw_timezone)
    now = arrow.now(user_timezone)

    try:
        when = now.replace(**time_mapping)
    except ValueError:
        await send("Invalid calendar date", ephemeral=True)
        return

    formatted_time = f"`{time_utils.format_relative(when.datetime)}`"
    if raw_timezone == "UTC":
        footer = "-# Used UTC time, consider changing your settings with /settings timezone"
        formatted_time = "\n".join((formatted_time, footer))

    await send(formatted_time, ephemeral=True)


@task_cache(maxsize=60)
async def _autocomplete_minute(current: str, timezone_str: str) -> list[Choice[int]]:
    common_minutes = (0, 15, 20, 30, 40, 45)
    if not current:
        tz = pytz.timezone(timezone_str)
        minute = arrow.Arrow.now(tz).datetime.minute

        if minute not in common_minutes:
            c = Choice(name=str(minute), value=minute)
            return [c, *(Choice(name=str(m), value=m) for m in common_minutes)]

    else:
        minutes_str = list(map(str, range(60)))
        if current in minutes_str:
            return [Choice(name=current, value=int(current))]

    return [Choice(name=str(m), value=m) for m in common_minutes]


@get_time_relative.autocomplete("minute")
async def autocomplete_minute(itx: Interaction, current: str) -> list[Choice[int]]:
    timezone_str = get_timezone_from_user(itx.client.conn, itx.user.id)
    return await _autocomplete_minute(current, timezone_str)


@task_cache(maxsize=60)
async def _autocomplete_hour(current: str, timezone_str: str) -> list[Choice[int]]:
    hours_int = range(24)
    hours = deque(en_hour_to_str(h) for h in range(24))

    if not current:
        tz = pytz.timezone(timezone_str)
        now = arrow.Arrow.now(tz)
        hour = en_hour_to_str(now.datetime.hour)
        while hour != hours[0]:
            hours.rotate()

        return [Choice(name=h, value=h) for h in hours]  # type: ignore

    if current in hours:
        return [Choice(name=current, value=current)]  # type: ignore

    if int(current) in hours_int:
        choices = (current, f"{current}am", f"{current}pm")
        return [Choice(name=c, value=c) for c in choices]  # type: ignore

    if time_utils.parse_hour(current) is not None:
        return [Choice(name=current, value=current)]  # type: ignore

    return []


@get_time_relative.autocomplete("hour")
async def autocomplete_hour(itx: Interaction, current: str) -> list[Choice[int]]:
    timezone_str = get_timezone_from_user(itx.client.conn, itx.user.id)
    return await _autocomplete_hour(current, timezone_str)


@task_cache(maxsize=300)
async def _autocomplete_day(current: str, timezone_str: str, year: int | None, month: int | None) -> list[Choice[int]]:
    # fmt: off
    days_str = (
        "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12",
        "13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23",
        "24", "25", "26", "27", "28", "29", "30", "31"
    )
    # fmt: on
    if current in days_str:
        if not year or month:
            return [Choice(name=current, value=int(current))]

        now = arrow.Arrow.now(pytz.timezone(timezone_str))
        kwargs = {k: v for k, v in (("year", year), ("month", month)) if v}
        when = now.replace(**kwargs) if kwargs else now

        if (when.datetime.year, when.datetime.month) > (now.datetime.year, now.datetime.month):
            start = when.replace(day=1)
            end = start.shift(months=1)
            span = arrow.Arrow.span_range("day", start.datetime, end.datetime, exact=True)
            days = {str(s[0].datetime.day) for s in span}
        else:
            start = now
            end = start.shift(months=1).replace(day=1)
            span = arrow.Arrow.span_range("day", start.datetime, end.datetime, exact=True)
            days = {str(s[0].datetime.day) for s in span}

        if current in days:
            return [Choice(name=current, value=int(current))]

    if not current:
        now = arrow.Arrow.now(pytz.timezone(timezone_str))
        kwargs = {k: v for k, v in (("year", year), ("month", month)) if v}
        when = now.replace(**kwargs) if kwargs else now

        if (when.datetime.year, when.datetime.month) > (now.datetime.year, now.datetime.month):
            start = when.replace(day=1)
            end = start.shift(months=1)
        else:
            start = now
            end = start.shift(months=1).replace(day=1)

        span = arrow.Arrow.span_range("day", start.datetime, end.datetime, exact=True)
        result = [*dict.fromkeys(s[0].datetime.day for s in span)][:10]
        return [Choice(name=str(day), value=day) for day in result]

    return []


@get_time_relative.autocomplete("day")
async def autocomplete_day(itx: Interaction, current: str) -> list[Choice[int]]:
    timezone_str = get_timezone_from_user(itx.client.conn, itx.user.id)
    year = itx.namespace.__dict__.get("year", None)
    month = itx.namespace.__dict__.get("month", None)
    return await _autocomplete_day(current, timezone_str, year, month)


@get_time_relative.autocomplete("month")
async def autocomplete_month(itx: Interaction, current: str) -> list[Choice[int]]:
    months = deque(range(1, 13))
    timezone_str = get_timezone_from_user(itx.client.conn, itx.user.id)
    now = arrow.Arrow.now(pytz.timezone(timezone_str))
    starting_month = now.datetime.month
    try:
        year = itx.namespace["year"]
    except KeyError:
        pass
    else:
        if year > now.datetime.year:
            starting_month = 1

    if not current:
        months.rotate(1 - starting_month)
        return [Choice(name=f"{m}", value=m) for m in months]
    if current in map(str, months):
        return [Choice(name=current, value=int(current))]
    return []


@get_time_relative.autocomplete("year")
async def autocomplete_year(itx: Interaction, current: str) -> list[Choice[int]]:
    if not current:
        return [Choice(name=str(y), value=y) for y in range(MIN_YEAR, MAX_YEAR + 1)]
    if len(current) != 4:
        return []
    str_years = [str(y) for y in range(MIN_YEAR, MAX_YEAR + 1)]
    if current in str_years:
        return [Choice(name=current, value=int(current))]
    return []


exports = BotExports([events_group, time_group])
