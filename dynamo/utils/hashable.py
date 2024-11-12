from collections.abc import Callable, Hashable, Sized
from typing import Any


class HashedSeq(list[Any]):
    __slots__ = ("hashvalue",)

    def __init__(self, tup: tuple[Any, ...], hash: Callable[[object], int] = hash):  # noqa: A002
        self[:] = tup
        self.hashvalue = hash(tuple(self))

    def __hash__(self) -> int:  # type: ignore
        return self.hashvalue


def make_key(
    args: tuple[Any, ...],
    kwargs: dict[Any, Any],
    kwargs_mark: tuple[object] = (object(),),  # type: ignore
    fast_types: set[type] = {int, str},  # noqa: B006
    type: type[type] = type,  # noqa: A002
    len: Callable[[Sized], int] = len,  # noqa: A002
) -> Hashable:
    """
    Make cache key from optionally typed positional and keyword arguments. Structure is flat and hashable.
    Treats `f(x=1, y=2)` and `f(y=2, x=1)` as the same call for caching purposes.
    """
    key = args
    if kwargs:
        sorted_items = tuple(sorted(kwargs.items()))
        key += kwargs_mark + sorted_items
    return key[0] if len(key) == 1 and type(key[0]) in fast_types else HashedSeq(key)
