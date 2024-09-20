from typing import Any

import discord
from discord.ext import commands

from dynamo.bot import Dynamo
from dynamo.utils.base_cog import DynamoCog
from dynamo.utils.cache import future_lru_cache
from dynamo.utils.format import shorten_string


class EventsDropdown(discord.ui.Select):
    def __init__(self, events: list[discord.ScheduledEvent], *args: Any, **kwargs: Any) -> None:
        self.events: list[discord.ScheduledEvent] = events

        options = [
            discord.SelectOption(label=e.name, value=str(e.id), description=shorten_string(e.description))
            for e in events
        ]

        super().__init__(*args, placeholder="Select an event", min_values=1, max_values=1, options=options, **kwargs)

    async def callback(self, interaction: discord.Interaction) -> None:
        event = next((e for e in self.events if e.id == int(self.values[0])), None)
        await interaction.response.send_message(await get_interested(event) or "No users found", ephemeral=True)


class EventsDropdownView(discord.ui.View):
    def __init__(self, events: list[discord.ScheduledEvent], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.add_item(EventsDropdown(events))

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)


@future_lru_cache(maxsize=10, ttl=1800)
async def get_interested(event: discord.ScheduledEvent) -> str:
    users: list[discord.User] = [user async for user in event.users()]
    return f"`[{event.name}]({event.url}) {' '.join(f'<@{u.id}>' for u in users) or "No users found"}`"


class Events(DynamoCog):
    """Scheduled event related commands"""

    def __init__(self, bot: Dynamo) -> None:
        super().__init__(bot)

        self.active_users: set[int] = set()

    def cog_check(self, ctx: commands.Context) -> bool:
        return ctx.guild is not None

    @future_lru_cache(maxsize=10, ttl=1800)
    async def fetch_events(self, guild: discord.Guild) -> list[discord.ScheduledEvent]:
        try:
            events = await guild.fetch_scheduled_events()
        except discord.HTTPException:
            self.log.exception("Failed to fetch events for guild %s", guild.id)
            return []
        return sorted(events, key=lambda e: e.start_time)

    @commands.hybrid_command(name="event")
    async def event(self, ctx: commands.Context, event: int | None = None) -> None:
        """Get a list of members subscribed to an event

        Parameters
        ----------
        event: int | None, optional
            The event ID to get attendees of
        """
        if ctx.author.id in self.active_users:
            return

        if event is not None:
            try:
                ev = await ctx.guild.fetch_scheduled_event(event)
            except discord.NotFound:
                await ctx.send(f"No event with id: {event}", ephemeral=True)
                return
            interested = await get_interested(ev)
            await ctx.send(interested, ephemeral=True)
            return

        if not (events := await self.fetch_events(ctx.guild)):
            await ctx.send("No events found!", ephemeral=True)
            return

        self.active_users.add(ctx.author.id)
        view = EventsDropdownView(events, timeout=25)
        view.message = await ctx.send("Select an event", view=view)

        await view.wait()

        self.active_users.remove(ctx.author.id)


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Events(bot))


async def teardown(bot: Dynamo) -> None:
    await bot.remove_cog(Events.__name__)
