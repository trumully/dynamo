from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar, cast, override

import discord
from discord import app_commands
from discord.ext import commands

from dynamo.utils.context import Context

if TYPE_CHECKING:
    from dynamo.core import Dynamo


BotT = TypeVar("BotT", bound=commands.Bot | commands.AutoShardedBot, covariant=True)
GuildLike = TypeVar("GuildLike", bound=discord.Guild | str, covariant=True)
SeedLike = TypeVar("SeedLike", bound=discord.Member | str, covariant=True)


class GuildConverter(commands.Converter[GuildLike]):
    """Convert an argument to a guild. If not found, return the current guild. If there's no guild at all,
    return the argument."""

    @override
    async def convert(self, ctx: commands.Context[BotT], argument: str) -> GuildLike:
        try:
            result = await commands.GuildConverter().convert(ctx, argument)
        except commands.GuildNotFound:
            result = argument if ctx.guild is None else ctx.guild
        return cast(GuildLike, result)


class SeedConverter(commands.Converter[SeedLike], app_commands.Transformer):
    """Convert a given string to a member type if it is valid.

    See
    ---
    :func:`discord.ext.commands.MemberConverter.convert`
    """

    @override
    async def convert(self, ctx: commands.Context[BotT], argument: str) -> SeedLike:
        try:
            result = await commands.MemberConverter().convert(ctx, argument)
        except commands.MemberNotFound:
            result = argument
        return cast(SeedLike, result)

    @override
    async def transform(self, interaction: discord.Interaction, value: str) -> discord.Member | str:
        # No need to reinvent the wheel, just run it through the commands.MemberConverter method.
        ctx = await Context.from_interaction(cast(discord.Interaction[Dynamo], interaction))
        return await self.convert(ctx, value)

    @property
    def type(self) -> discord.AppCommandOptionType:
        return discord.AppCommandOptionType.string
