import discord
from discord import app_commands
from discord.ext import commands

from dynamo.bot import Dynamo
from dynamo.ext.utils.cache import async_cache
from dynamo.ext.utils.helpers import truncate_string


class Dropdown(discord.ui.Select):
    def __init__(self, events: list[discord.ScheduledEvent]) -> None:
        self.events = events

        options = [
            discord.SelectOption(
                label=e.name,
                description=truncate_string(
                    e.description, placeholder="No description given"
                ),
            )
            for e in events
        ]

        super().__init__(
            placeholder="Select an event", min_values=1, max_values=1, options=options
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        event = next(e for e in self.events if e.name == self.values[0])
        pings = " ".join([f"<@{user.id}>" async for user in event.users()])
        await interaction.response.send_message(
            f"{event.name}: `{pings}`", ephemeral=True
        )


class DropdownView(discord.ui.View):
    def __init__(self, events: list[discord.ScheduledEvent]) -> None:
        super().__init__()

        self.add_item(Dropdown(events))


@app_commands.guild_only()
class Events(commands.GroupCog, group_name="events"):
    """Scheduled event related commands"""

    def __init__(self, bot: Dynamo) -> None:
        self.bot: Dynamo = bot

    @async_cache
    async def fetch_events(self, guild: discord.Guild) -> list[discord.ScheduledEvent]:
        events = await guild.fetch_scheduled_events()
        return sorted(events, key=lambda e: e.start_time)

    @commands.hybrid_command(
        name="event",
        description="Get a list of members subscribed to an event",
    )
    async def event(self, ctx: commands.Context) -> None:
        """Get a list of members subscribed to an event"""
        if ctx.guild is None:
            return

        events: list[discord.ScheduledEvent] = await self.fetch_events(ctx.guild)
        if not events:
            return await ctx.send("No events found!")
        view = DropdownView(events)
        await ctx.send("Select an event", view=view, ephemeral=True)

    @commands.hybrid_command(
        name="refresh",
        description="Refresh the event cache for current guild",
    )
    @commands.is_owner()
    async def refresh(self, ctx: commands.Context) -> None:
        """Refresh the event cache for current guild."""
        if ctx.guild is None:
            return

        async_cache.invalidate(self.fetch_events, ctx.guild)

        await self.fetch_events(ctx.guild)
        await ctx.send(f"Refreshed event cache for {ctx.guild.name}")


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Events(bot))
