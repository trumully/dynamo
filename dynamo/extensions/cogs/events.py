from __future__ import annotations

from typing import Any, NoReturn, cast

import discord
from discord.ext import commands
from discord.ui import View

from dynamo import Cog, Context, Dynamo
from dynamo.utils.cache import async_cache
from dynamo.utils.format import shorten_string
from dynamo.utils.helper import process_async_iterable


def event_to_option(event: discord.ScheduledEvent) -> discord.SelectOption:
    """Convert a ScheduledEvent to a SelectOption to be used in a dropdown menu"""
    description = shorten_string(event.description or "")
    return discord.SelectOption(label=event.name, value=str(event.id), description=description)


class EventsDropdown[V: View](discord.ui.Select[V]):
    """Base dropdown for selecting an event. Functionality can be defined with callback."""

    def __init__(self, events: list[discord.ScheduledEvent], *args: Any, **kwargs: Any) -> None:
        self.events: list[discord.ScheduledEvent] = events

        options = [event_to_option(e) for e in events]

        super().__init__(*args, placeholder="Select an event", min_values=1, max_values=1, options=options, **kwargs)


class EventsView(View):
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
        await self.message.edit(content="Expired!", view=self, delete_after=10)


class InterestedDropdown(EventsDropdown[EventsView]):
    async def callback(self, interaction: discord.Interaction) -> None:
        event: discord.ScheduledEvent | None = next((e for e in self.events if e.id == int(self.values[0])), None)
        response = "No users found" if event is None else await get_interested(event)
        await interaction.response.send_message(response, ephemeral=True)


@async_cache(ttl=900)
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


async def fetch_events(guild: discord.Guild) -> list[discord.ScheduledEvent]:
    events: list[discord.ScheduledEvent] = []
    try:
        events = await guild.fetch_scheduled_events(with_counts=False)
    except discord.HTTPException:
        return []
    return sorted(events, key=lambda e: e.start_time)


@async_cache(ttl=900)
async def event_check(guild: discord.Guild, event_id: int | None = None) -> str | list[discord.ScheduledEvent]:
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
        A string if an event is not found, otherwise a list of events
    """
    if event_id is None:
        return await fetch_events(guild) or f"{Context.Status.FAILURE} No events found!"
    try:
        event = await guild.fetch_scheduled_event(event_id, with_counts=False)
    except (discord.NotFound, discord.HTTPException):
        return f"No event with id: {event_id}"
    return await get_interested(event)


class Events(Cog, name="events"):
    """Scheduled event related commands"""

    def __init__(self, bot: Dynamo) -> None:
        super().__init__(bot)
        self.active_users: set[int] = set()

    @commands.hybrid_command(name="event")
    @commands.guild_only()
    async def event(self, ctx: Context, event_id: int | None = None) -> None:
        """Get attendees of an event

        A dropdown of guild events is shown by default.

        Parameters
        ----------
        event_id: int | None, optional
            The ID of the event.
        """
        if ctx.guild is None or ctx.author.id in self.active_users:
            return

        # Prevent invokation when a view is already active by invoking user
        self.active_users.add(ctx.author.id)

        # Message for when the events are cached or not
        is_guild_cached = event_check.get_containing(ctx.guild, event_id) is not None
        fetch_message = "Fetching events..." if is_guild_cached else "Events not cached, fetching..."
        message = await ctx.send(f"{self.bot.app_emojis.get("loading2", "⏳")}\t{fetch_message}")

        event_exists: str | list[discord.ScheduledEvent] = await event_check(ctx.guild, event_id)
        if isinstance(event_exists, str):
            self.active_users.remove(ctx.author.id)
            await message.edit(content=event_exists, delete_after=10)
            return

        view = EventsView(ctx.author.id, event_exists, InterestedDropdown, timeout=25)
        view.message = message
        await message.edit(content=f"Events in {ctx.guild.name}:", view=view)

        await view.wait()

        self.active_users.remove(ctx.author.id)

    @event.error
    async def event_error(self, ctx: Context, error: Exception) -> NoReturn:
        """If an unhandled exception ever occurs, remove the user from the active users, send an error message,
        and raise the error
        """
        if ctx.author.id in self.active_users:
            self.active_users.remove(ctx.author.id)
        await ctx.send(f"Something went wrong: {error!s}")
        raise error from None


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Events(bot))


async def teardown(bot: Dynamo) -> None:
    await bot.remove_cog(Events.__name__)
