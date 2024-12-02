from __future__ import annotations

from collections.abc import Callable, Coroutine, Generator, Iterator, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    NamedTuple,
    Protocol,
    SupportsIndex,
    TypeVar,
    overload,
)

from discord import AutoShardedClient, app_commands
from discord import Interaction as InteractionD

if TYPE_CHECKING:
    import aiohttp
    import apsw

_T_co = TypeVar("_T_co", covariant=True)

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


# https://github.com/hauntsaninja/useful_types/blob/main/useful_types/__init__.py#L285
class SequenceNotStr(Protocol[_T_co]):
    @overload
    def __getitem__(self, index: SupportsIndex, /) -> _T_co: ...
    @overload
    def __getitem__(self, index: slice, /) -> Sequence[_T_co]: ...
    def __contains__(self, value: object, /) -> bool: ...
    def __len__(self) -> int: ...
    def __iter__(self) -> Iterator[_T_co]: ...
    def index(self, value: Any, start: int = 0, stop: int = ..., /) -> int: ...
    def count(self, value: Any, /) -> int: ...
    def __reversed__(self) -> Iterator[_T_co]: ...
