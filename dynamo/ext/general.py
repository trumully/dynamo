import discord
from discord.ext import commands

from dynamo.bot import Dynamo


class General(commands.GroupCog, group_name="general"):
    """General commands"""

    def __init__(self, bot: Dynamo) -> None:
        self.bot: Dynamo = bot

    @commands.hybrid_command(name="invite")
    async def invite(self, interaction: discord.Interaction) -> None:
        """Get the invite link for the bot"""
        if (user := self.bot.user) is None:
            return

        embed = discord.Embed(
            description=f"[Invite me here!]({discord.utils.oauth_url(user.id)})"
        )
        try:
            await interaction.author.send(embed=embed)
            await interaction.response.send_message(
                "Check your DMs!", delete_after=10.0
            )
        except discord.Forbidden:
            await interaction.response.send_message(embed=embed)


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(General(bot))
