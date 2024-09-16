from typing import Any

import discord
from discord import app_commands
from discord.ext import commands


class MemberTransformer(commands.MemberConverter, app_commands.Transformer):
    async def convert(self, ctx: commands.Context, argument: Any) -> discord.Member | Any:
        try:
            return await super().convert(ctx, argument)
        except commands.MemberNotFound:
            return argument

    async def transform(self, interaction: discord.Interaction, value: Any) -> discord.Member | Any:
        return value

    @property
    def type(self) -> discord.AppCommandOptionType:
        return discord.AppCommandOptionType.user


class GuildConverter(commands.GuildConverter):
    """Convert an argument to a guild. If not found, return the current guild. If there's no guild at all,
    return the argument."""

    async def convert(self, ctx: commands.Context, argument: Any) -> discord.Guild | Any:
        try:
            return await super().convert(ctx, argument)
        except commands.GuildNotFound:
            return ctx.guild or argument
