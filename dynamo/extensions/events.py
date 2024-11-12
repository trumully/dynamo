from __future__ import annotations

import discord
from discord import app_commands
from discord.app_commands import Group, Transform

from dynamo.bot import Interaction
from dynamo.types import BotExports
from dynamo.utils.helper import process_async_iterable
from dynamo.utils.transformer import ScheduledEventTransformer


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


@app_commands.describe(event="The event to get attendees for. Either the event name or ID.")
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
@events_group.command(name="interested")
async def event_interested(
    itx: Interaction, event: Transform[discord.ScheduledEvent, ScheduledEventTransformer]
) -> None:
    """Get attendees of an event"""
    await itx.response.send_message(content=await get_interested(event), ephemeral=True)


exports = BotExports([events_group])
