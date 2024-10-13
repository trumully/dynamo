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


class GuildConverter[GuildLike: discord.Guild | str](ConverterMixin[GuildLike]):
    """Convert an argument to a guild. If not found, return the current guild. If there's no guild at all,
    return the argument."""

    async def convert(self, ctx: commands.Context[BotT], argument: str) -> GuildLike:
        try:
            result = await commands.GuildConverter().convert(ctx, argument)
        except commands.GuildNotFound:
            result = argument if ctx.guild is None else ctx.guild
        return cast(GuildLike, result)

    @property
    def type(self) -> discord.AppCommandOptionType:
        return discord.AppCommandOptionType.number


class MemberLikeConverter[MemberLike: discord.Member | str](ConverterMixin[MemberLike]):
    """Convert a given string to a member type if it is valid."""

    async def convert(self, ctx: commands.Context[BotT], argument: str | discord.Member) -> MemberLike:
        try:
            result = await commands.MemberConverter().convert(ctx, str(argument))
        except commands.MemberNotFound:
            result = argument
        return cast(MemberLike, result)

    @property
    def type(self) -> discord.AppCommandOptionType:
        return discord.AppCommandOptionType.string
