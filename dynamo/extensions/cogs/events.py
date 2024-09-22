import contextlib
from typing import Any

import discord
from discord.ext import commands

from dynamo.bot import Dynamo
from dynamo.utils.base_cog import DynamoCog
from dynamo.utils.cache import future_lru_cache
from dynamo.utils.checks import guild_only
from dynamo.utils.context import Context
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
    # https://peps.python.org/pep-0533/
    async with contextlib.aclosing(event.users()) as gen:
        users = [u async for u in gen]
    return f"`[{event.name}]({event.url}) {' '.join(f'<@{u.id}>' for u in users) or "No users found"}`"


class Events(DynamoCog):
    """Scheduled event related commands"""

    def __init__(self, bot: Dynamo) -> None:
        super().__init__(bot)

    @future_lru_cache(maxsize=10, ttl=1800)
    async def fetch_events(self, guild: discord.Guild) -> list[discord.ScheduledEvent]:
        try:
            events = await guild.fetch_scheduled_events()
        except discord.HTTPException:
            self.log.exception("Failed to fetch events for guild %s", guild.id)
        return sorted(events, key=lambda e: e.start_time)

    @commands.hybrid_command(name="event")
    @commands.cooldown(1, 35, commands.BucketType.guild)
    @guild_only()
    async def event(self, ctx: Context, event: int | None = None) -> None:
        """Get a list of members subscribed to an event

        Parameters
        ----------
        event: int | None, optional
            The event ID to get attendees of
        """
        if event is not None:
            try:
                ev = await ctx.guild.fetch_scheduled_event(event)
            except discord.NotFound:
                await ctx.send(f"No event with id: {event}", ephemeral=True)
                return
            interested = await get_interested(ev)
            await ctx.send(interested, ephemeral=True)
            return

        loading_emoji = self.bot.app_emojis.get("loading2", "⏳")
        message = await ctx.send(f"{loading_emoji} Fetching events...")

        events = await self.fetch_events(ctx.guild)

        if not events:
            await message.edit(content=f"{ctx.Status.FAILURE} No events found!")
            return

        view = EventsDropdownView(events, timeout=25)
        await message.edit(content="Select an event", view=view)

        await view.wait()

        await message.edit(content="Expired!", view=None)
        await message.delete(delay=10)


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Events(bot))


async def teardown(bot: Dynamo) -> None:
    await bot.remove_cog(Events.__name__)
