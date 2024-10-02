from collections.abc import Callable
from typing import Protocol

from discord.ext import commands

from dynamo._types import Coro
from dynamo.utils.context import Context


class Check(Protocol):
    predicate: Callable[..., Coro[bool]]

    def __call__[T](self, coro_or_commands: T) -> T: ...


def is_owner() -> Check:
    """Check if the user is the owner of the bot."""

    async def predicate(ctx: Context) -> bool:
        return ctx.author.id == ctx.bot.owner.id

    return commands.check(predicate)
