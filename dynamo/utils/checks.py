from typing import Any, Callable, Coroutine, Protocol, TypeVar

from discord.ext import commands

from dynamo.utils.context import Context

ContextT = TypeVar("ContextT", bound=commands.Context[Any], covariant=True)
T = TypeVar("T")


class Check(Protocol[ContextT]):
    predicate: Callable[..., Coroutine[Any, Any, bool]]

    def __call__(self, coro_or_commands: T) -> T: ...


def is_owner() -> Check[Context]:
    """Check if the user is the owner of the bot."""

    def predicate(ctx: Context) -> bool:
        return ctx.author.id == ctx.bot.owner_id

    return commands.check(predicate)


def guild_only() -> Check[Context]:
    """Only run this command in a guild context"""

    def predicate(ctx: Context) -> bool:
        return ctx.guild is not None

    return commands.check(predicate)
