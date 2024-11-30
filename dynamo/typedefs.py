from __future__ import annotations

from collections.abc import Callable, Coroutine, Generator
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol

from discord import AutoShardedClient, app_commands
from discord import Interaction as InteractionD

if TYPE_CHECKING:
    import aiohttp
    import apsw


type Coro[T] = Coroutine[Any, Any, T]
type CoroFn[**P, T] = Callable[P, Coro[T]]


type _I[T] = dict[T, Any] | set[T] | frozenset[T] | list[T] | tuple[T, ...]
type IsIterable[T] = _I[T] | Generator[T]


class RawSubmittableCls(Protocol):
    @classmethod
    async def raw_submit(
        cls: type[RawSubmittableCls], interaction: InteractionD, data: str
    ) -> Any: ...


class RawSubmittableStatic(Protocol):
    @staticmethod
    async def raw_submit(interaction: InteractionD, data: str) -> Any: ...


type RawSubmittable = RawSubmittableCls | RawSubmittableStatic
type AppCommandA = app_commands.Command[Any, Any, Any]
type AppCommandT = app_commands.Group | AppCommandA | app_commands.ContextMenu


class BotExports(NamedTuple):
    commands: list[AppCommandT] | None = None
    raw_modal_submits: dict[str, type[RawSubmittable]] | None = None
    raw_button_submits: dict[str, type[RawSubmittable]] | None = None


class HasExports(Protocol):
    exports: BotExports


class DynamoContext(NamedTuple):
    bot: AutoShardedClient
    db: apsw.Connection
    session: aiohttp.ClientSession
