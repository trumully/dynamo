import discord
from discord import app_commands
from discord.ext import commands

from dynamo.bot import Dynamo
from dynamo.ext.utils.cache import cache
from dynamo.ext.utils.helpers import truncate_string


class Dropdown(discord.ui.Select):
    def __init__(self, events: list[discord.ScheduledEvent], author_id: int) -> None:
        self.events: list[discord.ScheduledEvent] = events
        self.author_id: int = author_id

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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user and interaction.user.id == self.author_id

    async def callback(self, interaction: discord.Interaction) -> None:
        event = next(e for e in self.events if e.name == self.values[0])
        users: list[discord.User] = [user async for user in event.users()]
        pings = f"`{' '.join(f'<@{u.id}>' for u in users)}`" or "No users found"

        await interaction.response.send_message(
            f"{event.name}: {pings}", ephemeral=True
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

    @cache()
    async def fetch_events(self, guild: discord.Guild) -> list[discord.ScheduledEvent]:
        events = await guild.fetch_scheduled_events()
        return sorted(events, key=lambda e: e.start_time)

    @commands.hybrid_command(name="event")
    async def event(self, ctx: commands.Context) -> None:
        """Get a list of members subscribed to an event"""
        if not (guild := ctx.guild):
            return

        events: list[discord.ScheduledEvent] = await self.fetch_events(guild)
        if not events:
            return await ctx.send("No events found!")
        view = DropdownView(events)
        view.message = await ctx.send("Select an event", ephemeral=True, view=view)
        await view.wait()


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Events(bot))
