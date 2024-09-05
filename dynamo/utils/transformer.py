import discord
from discord import app_commands
from discord.ext import commands


class MemberTransformer(commands.MemberConverter, app_commands.Transformer):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.Member | str:
        try:
            return await super().convert(ctx, argument)
        except (commands.BadArgument, commands.CommandError):
            return argument

    async def transform(self, interaction: discord.Interaction, value: str) -> discord.Member | str:
        return value

    @property
    def type(self) -> discord.AppCommandOptionType:
        return discord.AppCommandOptionType.user
