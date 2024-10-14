from typing import Protocol

from discord.ext import commands

from dynamo import Context
from dynamo.typedefs import CoroFunction


class Check(Protocol):
    predicate: CoroFunction[[Context], bool]

    def __call__[T](self, coro_or_commands: T) -> T: ...


def is_owner() -> Check:
    """Check if the user is the owner of the bot."""

    async def predicate(ctx: Context) -> bool:
        return ctx.author.id == ctx.bot.owner.id

    return commands.check(predicate)


def is_dev_guild() -> Check:
    async def predicate(ctx: Context) -> bool:
        return ctx.guild is not None and ctx.guild.id == ctx.bot.dev_guild.id

    return commands.check(predicate)
