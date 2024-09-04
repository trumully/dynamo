import logging

import discord
from discord.ext import commands

from dynamo.bot import Dynamo
from dynamo.utils.cache import cache

log = logging.getLogger(__name__)


class Dropdown(discord.ui.Select):
    def __init__(self, events: list[discord.ScheduledEvent]) -> None:
        self.events: list[discord.ScheduledEvent] = events

        options = [discord.SelectOption(label=e.name, description="An event") for e in events]

        super().__init__(placeholder="Select an event", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        event = next(e for e in self.events if e.name == self.values[0])
        users: list[discord.User] = [user async for user in event.users()]
        pings = f"`{' '.join(f'<@{u.id}>' for u in users)}`" or "No users found"

        await interaction.response.send_message(f"{event.name}: {pings}", ephemeral=True)


class DropdownView(discord.ui.View):
    def __init__(self, events: list[discord.ScheduledEvent]) -> None:
        super().__init__()
        self.add_item(Dropdown(events))


class Events(commands.Cog, name="events"):
    """Scheduled event related commands"""

    def __init__(self, bot: Dynamo) -> None:
        self.bot: Dynamo = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return ctx.guild is not None

    @cache()
    async def fetch_events(self, guild: discord.Guild) -> list[discord.ScheduledEvent]:
        try:
            events = await guild.fetch_scheduled_events()
        except discord.HTTPException:
            log.exception("Failed to fetch events for guild %s", guild.id)
        return sorted(events, key=lambda e: e.start_time)

    @commands.hybrid_command(name="event")
    async def event(self, ctx: commands.Context) -> None:
        """Get a list of members subscribed to an event"""
        if not (guild := ctx.guild):
            return

        events: list[discord.ScheduledEvent] = await self.fetch_events(guild)
        if not events:
            await ctx.send("No events found!", ephemeral=True)
            return
        view = DropdownView(events)
        view.message = await ctx.send("Select an event", ephemeral=True, view=view)
        await view.wait()


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Events(bot))
