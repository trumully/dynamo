from collections.abc import Callable
from typing import Protocol

from discord.ext import commands

from dynamo import Context
from dynamo.typedefs import Coro


class Check(Protocol):
    predicate: Callable[[Context], Coro[bool]]

    def __call__[T](self, coro_or_commands: T) -> T: ...


def is_owner() -> Check:
    """Check if the user is the owner of the bot."""

    async def predicate(ctx: Context) -> bool:
        return ctx.author.id == ctx.bot.owner.id

    return commands.check(predicate)
