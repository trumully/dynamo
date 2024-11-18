from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol

import discord.abc
from discord import Interaction as InteractionD
from discord import app_commands

if TYPE_CHECKING:
    import datetime

type Coro[T] = Coroutine[Any, Any, T]
type CoroFunction[**P, T] = Callable[P, Coro[T]]


class RawSubmittableCls(Protocol):
    @classmethod
    async def raw_submit(cls: type[RawSubmittableCls], interaction: InteractionD, data: str) -> Any: ...


class RawSubmittableStatic(Protocol):
    @staticmethod
    async def raw_submit(interaction: InteractionD, data: str) -> Any: ...


type RawSubmittable = RawSubmittableCls | RawSubmittableStatic
type AppCommandA = app_commands.Command[Any, Any, Any]
type AppCommandT = app_commands.Group | AppCommandA | app_commands.ContextMenu


class DynamoLike(Protocol):
    bot_app_info: discord.AppInfo
    owner_id: int
    uptime: datetime.datetime


class BotExports(NamedTuple):
    commands: list[AppCommandT] | None = None
    raw_modal_submits: dict[str, type[RawSubmittable]] | None = None
    raw_button_submits: dict[str, type[RawSubmittable]] | None = None


class HasExports(Protocol):
    exports: BotExports
