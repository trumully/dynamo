from __future__ import annotations

from collections.abc import Callable, Coroutine, Mapping
from typing import Any, NamedTuple, Protocol, TypeVar

import discord.abc
from discord import Interaction as DInter
from discord import app_commands
from discord.ext import commands

type BotT = commands.Bot | commands.AutoShardedBot
BotT_co = TypeVar("BotT_co", bound=BotT, covariant=True)

type CogT = commands.Cog
type CommandT = commands.Command[CogT, ..., Any]

type ContextT = commands.Context[BotT]
type ContextA = commands.Context[Any]
ContextT_co = TypeVar("ContextT_co", bound=ContextT, covariant=True)

type MaybeSnowflake = discord.abc.Snowflake | None


type Coro[T] = Coroutine[Any, Any, T]
type CoroFunction[**P, T] = Callable[P, Coro[T]]
type DecoratedCoro[**P, T] = Callable[[CoroFunction[P, T]], T]


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


class RawSubmittableCls(Protocol):
    @classmethod
    async def raw_submit(cls: type[RawSubmittableCls], interaction: DInter, data: str) -> Any: ...


class RawSubmittableStatic(Protocol):
    @staticmethod
    async def raw_submit(interaction: DInter, data: str) -> Any: ...


type RawSubmittable = RawSubmittableCls | RawSubmittableStatic
type ACommand = app_commands.Command[Any, Any, Any]
type AppCommandT = app_commands.Group | ACommand


class Emojis(dict[str, str]):
    def __init__(self, emojis: list[discord.Emoji], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        for emoji in emojis:
            self[emoji.name] = f"<{"a" if emoji.animated else ""}:{emoji.name}:{emoji.id}>"


class DynamoLike(Protocol):
    bot_app_info: discord.AppInfo
    app_emojis: Emojis


class BotExports(NamedTuple):
    commands: list[AppCommandT] | None = None
    raw_modal_submits: dict[str, type[RawSubmittable]] | None = None
    raw_button_submits: dict[str, type[RawSubmittable]] | None = None


class HasExports(Protocol):
    exports: BotExports
