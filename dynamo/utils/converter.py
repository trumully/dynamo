from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from dynamo.utils.context import Context

if TYPE_CHECKING:
    from dynamo.core import Dynamo


class GuildConverter(commands.GuildConverter):
    """Convert an argument to a guild. If not found, return the current guild. If there's no guild at all,
    return the argument."""

    async def convert(self, ctx: Context, argument: str) -> discord.Guild | str:  # type: ignore
        try:
            result: discord.Guild = await commands.GuildConverter().convert(ctx, argument)
        except commands.GuildNotFound:
            return argument if ctx.guild is None else ctx.guild
        return result


class SeedConverter(commands.Converter[discord.Member | str], app_commands.Transformer):
    """Convert a given string to a member type if it is valid.

    See
    ---
    :func:`discord.ext.commands.MemberConverter.convert`
    """

    async def convert(self, ctx: Context, argument: str) -> discord.Member | str:  # type: ignore
        try:
            return await commands.MemberConverter().convert(ctx, argument)
        except commands.MemberNotFound:
            return argument

    async def transform(self, interaction: discord.Interaction[Dynamo], value: str) -> discord.Member | str:  # type: ignore
        # No need to reinvent the wheel, just run it through the commands.MemberConverter method.
        ctx = await Context.from_interaction(interaction)
        return await self.convert(ctx, value)

    @property
    def type(self) -> discord.AppCommandOptionType:
        return discord.AppCommandOptionType.string
