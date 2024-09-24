from typing import Any, Callable, Coroutine, Protocol

from discord.ext import commands

from dynamo._typing import ContextT, T
from dynamo.utils.context import Context


class Check(Protocol[ContextT]):
    predicate: Callable[..., Coroutine[Any, Any, bool]]

    def __call__(self, coro_or_commands: T) -> T: ...


def is_owner() -> Check[Context]:
    """Check if the user is the owner of the bot."""

    def predicate(ctx: Context) -> bool:
        return ctx.author.id == ctx.bot.owner.id

    return commands.check(predicate)
