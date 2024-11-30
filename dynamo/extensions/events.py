from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.app_commands import Group, Transform
from dynamo_utils.iterclose import process_async_iterable

from dynamo.typedefs import BotExports
from dynamo.utils.transformer import (
    ScheduledEventTransformer,  # noqa: TC001  we need this at runtime
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from dynamo.bot import Interaction


def display_interested(name: str, url: str, users: Iterable[discord.User]) -> str:
    """Get a list of users interested in an event.

    Returns:
    -------
    str
        A formatted string of users interested in the event.
        `[Event Name](Event URL) <@User1> <@User2> ...`
        Designed to be copied and pasted.
    """
    result = f"[{name}]({url})\n"
    result += " ".join(u.mention for u in users) or "No users interested yet"
    return f"`{result}`"


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
    ephemeral: bool = False,
) -> None:
    """Get attendees of an event."""
    await itx.response.defer(ephemeral=ephemeral)

    users = await process_async_iterable(event.users())
    interested: str = display_interested(event.name, event.url, users)

    await itx.followup.send(content=interested, ephemeral=ephemeral)


@event_interested.error  # type: ignore[reportUnknownMemberType]
async def event_interested_error(
    itx: Interaction, error: app_commands.AppCommandError
) -> None:
    if isinstance(error, app_commands.TransformerError):
        await itx.response.send_message(
            content=f"Event not found: {error.value}", ephemeral=True
        )
    else:
        raise error from None


exports = BotExports(commands=[events_group])
