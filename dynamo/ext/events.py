import logging

import discord
from discord.ext import commands

from dynamo.bot import Dynamo
from dynamo.utils.cache import async_lru_cache

log = logging.getLogger(__name__)


class Dropdown(discord.ui.Select):
    def __init__(self, events: list[discord.ScheduledEvent]) -> None:
        self.events: list[discord.ScheduledEvent] = events

        options = [discord.SelectOption(label=e.name, value=str(e.id), description="An event") for e in events]

        super().__init__(placeholder="Select an event", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if (event := next((e for e in self.events if str(e.id) == self.values[0]), None)) is None:
            await interaction.response.send_message("Something went wrong, please try again.", ephemeral=True)
            return
        interested = await get_interested(event)
        await interaction.response.send_message(interested, ephemeral=True)


class DropdownView(discord.ui.View):
    def __init__(self, events: list[discord.ScheduledEvent]) -> None:
        super().__init__()
        self.add_item(Dropdown(events))


@async_lru_cache()
async def fetch_events(guild: discord.Guild) -> list[discord.ScheduledEvent]:
    try:
        events = await guild.fetch_scheduled_events()
    except discord.HTTPException:
        log.exception("Failed to fetch events for guild %s", guild.id)
    return sorted(events, key=lambda e: e.start_time)


@async_lru_cache()
async def get_interested(event: discord.ScheduledEvent) -> str:
    users: list[discord.User] = [user async for user in event.users()]
    return f"`[{event.name}]({event.url}) {' '.join(f'<@{u.id}>' for u in users) or "No users found"}`"


class Events(commands.Cog, name="Events"):
    """Scheduled event related commands"""

    def __init__(self, bot: Dynamo) -> None:
        self.bot: Dynamo = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return ctx.guild is not None

    @commands.hybrid_command(name="event")
    async def event(self, ctx: commands.Context, event: int | None) -> None:
        """Get a list of members subscribed to an event

        Parameters
        ----------
        event: int | None
            The event ID to get attendees of (optional)
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

        if not (events := await fetch_events(ctx.guild)):
            await ctx.send("No events found!", ephemeral=True)
            return
        view = DropdownView(events)
        view.message = await ctx.send("Select an event", ephemeral=True, view=view)
        await view.wait()


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Events(bot))
