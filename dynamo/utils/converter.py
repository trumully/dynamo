from __future__ import annotations

from typing import Any, cast

import discord
from discord import app_commands
from discord.ext import commands

from dynamo.core.bot import Interaction
from dynamo.core.context import Context

type BotT = commands.Bot | commands.AutoShardedBot


class ConverterMixin[T: Any](commands.Converter[T], app_commands.Transformer):
    """A mixin of a converter and a transformer."""

    async def transform(self, interaction: discord.Interaction, value: Any, /) -> T:
        ctx = await Context.from_interaction(cast(Interaction, interaction))
        return await self.convert(ctx, value)

    @property
    def type(self) -> discord.AppCommandOptionType:
        return NotImplemented


class GuildConverter(ConverterMixin[discord.Guild | str]):
    """Convert an argument to a guild. If not found, return the current guild. If there's no guild at all,
    return the argument."""

    async def convert(self, ctx: commands.Context[BotT], argument: str) -> discord.Guild | str:
        try:
            result = await commands.GuildConverter().convert(ctx, argument)
        except commands.GuildNotFound:
            return argument if ctx.guild is None else ctx.guild
        return result

    @property
    def type(self) -> discord.AppCommandOptionType:
        return discord.AppCommandOptionType.number


class MemberLikeConverter(ConverterMixin[discord.Member | str]):
    """Convert a given string to a member type if it is valid."""

    async def convert(self, ctx: commands.Context[BotT], argument: str) -> discord.Member | str:
        try:
            result = await commands.MemberConverter().convert(ctx, argument)
        except commands.MemberNotFound:
            return argument
        return result

    @property
    def type(self) -> discord.AppCommandOptionType:
        return discord.AppCommandOptionType.string
