from __future__ import annotations

from typing import Any, TypeVar, cast

import discord
from discord import app_commands
from discord.ext import commands

from dynamo.core.bot import Interaction
from dynamo.utils.context import Context

BotT_co = TypeVar("BotT_co", bound=commands.Bot | commands.AutoShardedBot, covariant=True)
GuildLike_co = TypeVar("GuildLike_co", bound=discord.Guild | str, covariant=True)
MemberLike_co = TypeVar("MemberLike_co", bound=discord.Member | str, covariant=True)
T_co = TypeVar("T_co", bound=Any, covariant=True)


class ConverterMixin(commands.Converter[T_co], app_commands.Transformer):
    """A mixin for converting values."""

    async def transform(self, interaction: discord.Interaction, value: Any, /) -> T_co:
        ctx = await Context.from_interaction(cast(Interaction, interaction))
        return await self.convert(ctx, value)

    @property
    def type(self) -> discord.AppCommandOptionType:
        return NotImplemented


class GuildConverter(ConverterMixin[GuildLike_co]):
    """Convert an argument to a guild. If not found, return the current guild. If there's no guild at all,
    return the argument."""

    async def convert(self, ctx: commands.Context[BotT_co], argument: str) -> GuildLike_co:
        try:
            result = await commands.GuildConverter().convert(ctx, argument)
        except commands.GuildNotFound:
            result = argument if ctx.guild is None else ctx.guild
        return cast(GuildLike_co, result)

    @property
    def type(self) -> discord.AppCommandOptionType:
        return discord.AppCommandOptionType.number


class MemberLikeConverter(ConverterMixin[MemberLike_co]):
    """Convert a given string to a member type if it is valid."""

    async def convert(self, ctx: commands.Context[BotT_co], argument: str | discord.Member) -> MemberLike_co:
        try:
            result = await commands.MemberConverter().convert(ctx, str(argument))
        except commands.MemberNotFound:
            result = argument
        return cast(MemberLike_co, result)

    @property
    def type(self) -> discord.AppCommandOptionType:
        return discord.AppCommandOptionType.string
