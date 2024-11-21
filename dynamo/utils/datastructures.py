from __future__ import annotations

from typing import TYPE_CHECKING

from dynamo_utils.task_cache import LRU

if TYPE_CHECKING:
    from collections.abc import MutableMapping


__all__ = ("LRU", "Trie")


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
