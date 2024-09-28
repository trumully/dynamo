from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator
from typing import Any, cast

import discord
from discord.ext import commands

from dynamo.core import Dynamo, DynamoCog
from dynamo.utils.cache import async_cache
from dynamo.utils.context import Context
from dynamo.utils.format import shorten_string


def event_to_option(event: discord.ScheduledEvent) -> discord.SelectOption:
    """Convert a ScheduledEvent to a SelectOption to be used in a dropdown menu"""
    description = event.description if event.description is not None else ""
    return discord.SelectOption(label=event.name, value=str(event.id), description=shorten_string(description))


class EventsDropdown[V: discord.ui.View](discord.ui.Select[V]):
    """Base dropdown for selecting an event. Functionality can be defined with callback."""

    def __init__(self, events: list[discord.ScheduledEvent], *args: Any, **kwargs: Any) -> None:
        self.events: list[discord.ScheduledEvent] = events

        options = [event_to_option(e) for e in events]

        super().__init__(*args, placeholder="Select an event", min_values=1, max_values=1, options=options, **kwargs)


class EventsView(discord.ui.View):
    """View for selecting an event"""

    message: discord.Message

    def __init__(
        self,
        author_id: int,
        events: list[discord.ScheduledEvent],
        dropdown: type[EventsDropdown[EventsView]],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.author_id: int = author_id
        self.add_item(dropdown(events))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return bool(interaction.user and interaction.user.id == self.author_id)

    async def on_timeout(self) -> None:
        for i in self.children:
            item = cast(EventsDropdown[EventsView], i)
            item.disabled = True
        await self.message.edit(view=self)


class InterestedDropdown(EventsDropdown[EventsView]):
    async def callback(self, interaction: discord.Interaction) -> None:
        event: discord.ScheduledEvent | None = next(filter(lambda e: e.id == int(self.values[0]), self.events), None)
        response = "No users found" if event is None else await get_interested(event)
        await interaction.response.send_message(response, ephemeral=True)


@async_cache(ttl=1800)
async def get_interested(event: discord.ScheduledEvent) -> str:
    """|coro|

    Get a list of users interested in an event

    Parameters
    ----------
    event : discord.ScheduledEvent
        The event to get interested users of

    Returns
    -------
    str
        A formatted string of users interested in the event.
        `[Event Name](Event URL) <@User1> <@User2> ...`
        Designed to be copied and pasted.
    """
    # https://peps.python.org/pep-0533/
    async with contextlib.aclosing(cast(AsyncGenerator[discord.User], event.users())) as gen:
        users: list[discord.User] = [u async for u in gen]
    return f"`[{event.name}]({event.url}) {" ".join(u.mention for u in users) or "No users found"}`"


class Events(DynamoCog):
    """Scheduled event related commands"""

    def __init__(self, bot: Dynamo) -> None:
        super().__init__(bot)

    async def fetch_events(self, guild: discord.Guild) -> list[discord.ScheduledEvent]:
        events: list[discord.ScheduledEvent] = []
        try:
            events = await guild.fetch_scheduled_events(with_counts=False)
        except discord.HTTPException:
            self.log.exception("Failed to fetch events for guild %s", guild.id)
        return sorted(events, key=lambda e: e.start_time)

    @async_cache(ttl=1800)
    async def event_check(
        self, guild: discord.Guild, event_id: int | None = None
    ) -> str | list[discord.ScheduledEvent]:
        """|coro|

        Get a list of members subscribed to an event. If event is provided, get attendees of that event if it exists.
        If no event is provided, get a list of all events in the guild. In both cases if neither events nor attendees
        are found, return a failure message.

        Parameters
        ----------
        guild : discord.Guild
            The guild to fetch events from
        event_id : int | None, optional
            The id of a specific event to fetch, by default None

        Returns
        -------
        str | list[discord.ScheduledEvent]
            _description_
        """
        if event_id is not None:
            try:
                ev = await guild.fetch_scheduled_event(event_id, with_counts=False)
            except discord.NotFound:
                return f"No event with id: {event_id}"
            return await get_interested(ev)

        return await self.fetch_events(guild) or f"{Context.Status.FAILURE} No events found!"

    @commands.hybrid_command(name="event")
    @commands.cooldown(1, 35, commands.BucketType.user)
    @commands.guild_only()
    async def event(self, ctx: Context, event: int | None = None) -> None:
        """Get a list of members subscribed to an event

        Parameters
        ----------
        event: int | None, optional
            The event ID to get attendees of
        """
        if ctx.guild is None:
            return

        message = await ctx.send(f"{self.bot.app_emojis.get("loading2", "⏳")}\tFetching events...")

        event_check: str | list[discord.ScheduledEvent] = await self.event_check(ctx.guild, event)
        if isinstance(event_check, str):
            await message.edit(content=event_check)
            await message.delete(delay=10)
            return

        view = EventsView(ctx.author.id, event_check, InterestedDropdown, timeout=25)
        await message.edit(content=f"Events in {ctx.guild.name}:", view=view)

        await view.wait()

        await message.edit(content="Expired!", view=None)
        await message.delete(delay=10)


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Events(bot))


async def teardown(bot: Dynamo) -> None:
    await bot.remove_cog(Events.__name__)
