import discord
from discord.ext import commands

from dynamo.bot import Dynamo


class General(commands.GroupCog, name="general"):
    """General commands"""

    def __init__(self, bot: Dynamo) -> None:
        self.bot: Dynamo = bot

    @commands.hybrid_command(
        name="invite",
        description="Get the invite link for the bot",
    )
    async def invite(self, ctx: commands.Context) -> None:
        """Get the invite link for the bot"""
        if (user := self.bot.user) is None:
            return

        embed = discord.Embed(
            description=f"[Invite me here!]({discord.utils.oauth_url(user.id)})"
        )
        try:
            await ctx.author.send(embed=embed)
            await ctx.send("Check your DMs!", delete_after=10)
        except discord.Forbidden:
            await ctx.send(embed=embed)


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(General(bot))
