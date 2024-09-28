from collections.abc import Callable, Coroutine
from typing import Any, Protocol

from discord.ext import commands

from dynamo.utils.context import Context


class Check(Protocol):
    predicate: Callable[..., Coroutine[Any, Any, bool]]

    def __call__[T](self, coro_or_commands: T) -> T: ...


def is_owner() -> Check:
    """Check if the user is the owner of the bot."""

    async def predicate(ctx: Context) -> bool:
        return ctx.author.id == ctx.bot.owner.id

    return commands.check(predicate)
