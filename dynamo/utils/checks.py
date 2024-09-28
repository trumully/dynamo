from collections.abc import Callable, Coroutine
from typing import Any, Protocol

from discord.ext import commands

from dynamo.utils.context import Context


class Check[T](Protocol):
    predicate: Callable[..., Coroutine[Any, Any, bool]]

    def __call__(self, coro_or_commands: T) -> T: ...


def is_owner() -> Check[Context]:
    """Check if the user is the owner of the bot."""

    def predicate(ctx: Context) -> bool:
        return ctx.author.id == ctx.bot.owner.id

    return commands.check(predicate)
