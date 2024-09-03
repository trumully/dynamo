import discord
from discord.ext import commands

from dynamo.bot import Dynamo
from dynamo.utils.time import human_timedelta


class General(commands.GroupCog, group_name="general"):
    """General commands"""

    def __init__(self, bot: Dynamo) -> None:
        self.bot: Dynamo = bot

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx: commands.Context) -> None:
        """Get the bot's latency"""
        await ctx.send(f"Pong! {round(self.bot.latency * 1000)}ms")

    @commands.hybrid_command(name="invite")
    async def invite(self, ctx: commands.Context) -> None:
        """Get the invite link for the bot"""
        if (user := self.bot.user) is None:
            return

        inv = f"[Invite me here!]({discord.utils.oauth_url(user.id)})"
        try:
            await ctx.author.send(inv)
            await ctx.send("Check your DMs!", delete_after=10.0)
        except discord.Forbidden:
            await ctx.send(inv)

    @commands.hybrid_command(name="about")
    async def about(self, ctx: commands.Context) -> None:
        """Get information about the bot"""
        embed = discord.Embed(
            title="About Dynamo",
            description="Dynamo is a bot that does stuff.",
        )
        uptime = f"`{human_timedelta(dt=self.bot.uptime, suffix=False)}`"
        embed.add_field(name="Uptime", value=uptime)
        embed.set_image(url=self.bot.user.avatar.url)
        embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.avatar.url)
        await ctx.send(embed=embed)


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(General(bot))
