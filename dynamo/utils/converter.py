import discord
from discord.ext import commands


class MemberConverter(commands.MemberConverter):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.Member | str:
        converter = commands.MemberConverter()

        try:
            return await converter.convert(ctx, argument)
        except commands.MemberNotFound:
            return argument
