from collections.abc import Callable, Coroutine, Mapping
from typing import Any, ParamSpec, Protocol, TypeVar

from discord import Interaction as DInter
from discord import app_commands
from discord.ext import commands

P = ParamSpec("P")

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)
T_contra = TypeVar("T_contra", contravariant=True)

S = TypeVar("S", bound=object)
S_co = TypeVar("S_co", bound=object, covariant=True)

CogT = TypeVar("CogT", bound=commands.Cog)
CommandT = TypeVar("CommandT", bound=commands.Command[Any, ..., Any])
ContextT = TypeVar("ContextT", bound=commands.Context[Any], covariant=True)


type Coro[T] = Coroutine[Any, Any, T]
type WrappedCoro[**P, T] = Callable[P, Coro[T]]
type DecoratedCoro[**P, T] = Callable[[WrappedCoro[P, T]], T]


class NotFoundWithHelp(commands.CommandError): ...


command_error_messages: Mapping[type[commands.CommandError], str] = {
    commands.CommandNotFound: "Command not found: **`{}`**{}",
    NotFoundWithHelp: "Command not found: **`{}`**{}",
    commands.MissingRequiredArgument: "Missing required argument: `{}`.",
    commands.BadArgument: "Bad argument.",
    commands.CommandOnCooldown: "You are on cooldown. Try again in `{:.2f}` seconds.",
    commands.TooManyArguments: "Too many arguments.",
    commands.MissingPermissions: "You are not allowed to use this command.",
    commands.BotMissingPermissions: "I am not allowed to use this command.",
    commands.NoPrivateMessage: "This command can only be used in a server.",
    commands.NotOwner: "You are not the owner of this bot.",
    commands.DisabledCommand: "This command is disabled.",
    commands.CheckFailure: "You do not have permission to use this command.",
}

app_command_error_messages: Mapping[type[app_commands.AppCommandError], str] = {
    app_commands.CommandNotFound: "Command not found: **`{}`**{}",
    app_commands.CommandOnCooldown: "You are on cooldown. Try again in `{:.2f}` seconds.",
    app_commands.MissingPermissions: "You are not allowed to use this command.",
    app_commands.BotMissingPermissions: "I am not allowed to use this command.",
    app_commands.NoPrivateMessage: "This command can only be used in a server.",
    app_commands.CheckFailure: "You do not have permission to use this command.",
}


class _MissingSentinel:
    """
    Represents a sentinel value to indicate that something is missing or not provided.

    This class is not meant to be instantiated. It should be used as a type for
    comparison or as a default value in function signatures.
    """

    __slots__ = ()

    def __eq__(self, other: Any) -> bool:
        return False

    def __bool__(self) -> bool:
        return False

    def __hash__(self) -> int:
        return 0

    def __repr__(self):
        return "..."


MISSING: Any = _MissingSentinel()


class RawSubmittableCls(Protocol):
    @classmethod
    async def raw_submit(cls, interaction: DInter, data: str) -> Any: ...


class RawSubmittableStatic(Protocol):
    @staticmethod
    async def raw_submit(interaction: DInter, data: str) -> Any: ...


type RawSubmittable = RawSubmittableCls | RawSubmittableStatic
