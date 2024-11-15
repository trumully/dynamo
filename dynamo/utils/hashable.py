from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping
from typing import Any


class HashedSeq(list[Any]):
    __slots__ = ("hashvalue",)

    def __init__(self, tup: tuple[Hashable, ...], hash: Callable[[object], int] = hash) -> None:  # noqa: A002
        self[:] = tup
        self.hashvalue = hash(tup)

    def __hash__(self) -> int:  # type: ignore
        return self.hashvalue

    def __eq__(self, other: object) -> bool:
        return type(self) is type(other) and self[:] == other[:]  # type: ignore

    @classmethod
    def from_call(
        cls: type[HashedSeq],
        args: tuple[Hashable, ...],
        kwds: Mapping[str, Hashable],
        fast_types: tuple[type, ...] = (int, str),
        kwarg_sentinel: Hashable = object(),
    ) -> HashedSeq | int | str:
        key = args if not kwds else (*args, kwarg_sentinel, *kwds.items())
        return key[0] if len(key) == 1 and type(key[0]) in fast_types else cls(key)  # type: ignore
