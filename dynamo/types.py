from __future__ import annotations

from collections.abc import Callable, Coroutine, MutableMapping
from typing import Any, NamedTuple, Protocol

from discord import Interaction as InteractionD
from discord import app_commands

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


class BotExports(NamedTuple):
    commands: list[AppCommandT] | None = None
    raw_modal_submits: dict[str, type[RawSubmittable]] | None = None
    raw_button_submits: dict[str, type[RawSubmittable]] | None = None


class HasExports(Protocol):
    exports: BotExports


class TrieNode:
    __slots__ = ("children", "is_end")

    def __init__(self) -> None:
        self.children: MutableMapping[str, TrieNode] = {}
        self.is_end: bool = False


class Trie:
    __slots__ = ("root",)

    def __init__(self) -> None:
        self.root = TrieNode()

    def insert(self, word: str) -> None:
        node = self.root
        for char in word.casefold():
            node.children.setdefault(char, TrieNode())
            node = node.children[char]
        node.is_end = True

    def search(self, prefix: str) -> set[str]:
        node = self.root
        results: set[str] = set()

        for char in prefix.casefold():
            if char not in node.children:
                return results
            node = node.children[char]

        self._collect_words(node, prefix, results)
        return results

    def _collect_words(self, node: TrieNode, prefix: str, results: set[str]) -> None:
        if node.is_end:
            results.add(prefix)
        for char, child in node.children.items():
            self._collect_words(child, prefix + char, results)
