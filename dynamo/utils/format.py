from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import TYPE_CHECKING, NamedTuple

from dynamo.utils.helper import ROOT

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


class Codeblock(NamedTuple):
    language: str | None
    content: str

    @classmethod
    def as_raw(cls, content: str) -> Codeblock:
        if not content.startswith("`"):
            return cls(None, content)

        buffer: deque[str] = deque(maxlen=3)
        backticks = 0
        in_language = False
        in_code = False
        language: list[str] = []
        code: list[str] = []

        for char in content:
            if char == "`" and not in_code and not in_language:
                backticks += 1
            if buffer and buffer[-1] == "`" and char != "`" or in_code and "".join(buffer) != "`" * backticks:
                in_code = True
                code.append(char)
            if char == "\n":
                in_language = False
                in_code = True
            elif "".join(buffer) == "`" * 3 and char != "`":
                in_language = True
                language.append(char)
            elif in_language:
                if char != "\n":
                    language.append(char)

            buffer.append(char)

        if not code and not language:
            code[:] = buffer

        return Codeblock("".join(language), "".join(code[len(language) : -backticks]))

    def __str__(self) -> str:
        return f"```{self.language}\n{self.content}\n```"


def human_join(seq: Sequence[str], sep: str = ", ", conjunction: str = "or", *, oxford_comma: bool = True) -> str:
    """Join a sequence of strings into a human-readable format."""
    # hack: str is a Sequence[str], no point in joining it
    if isinstance(seq, str):
        return seq

    if (size := len(seq)) == 0:
        return ""

    if size == 1:
        return seq[0]

    if size == 2:  # noqa: PLR2004
        return f"{seq[0]} {conjunction} {seq[1]}"

    return f"{sep.join(seq[:-1])}{sep if oxford_comma else " "}{conjunction} {seq[-1]}"


class CJK(StrEnum):
    CHINESE = auto()
    JAPANESE = auto()
    KOREAN = auto()
    NONE = auto()


def is_cjk(text: str) -> CJK:
    """Check if a string contains any CJK characters."""
    if re.search(r"[\u4e00-\u9fff\u3400-\u4dbf]", text):
        return CJK.CHINESE

    if re.search(r"[\u3040-\u309f\u30a0-\u30ff]", text):
        return CJK.JAPANESE

    if re.search(r"[\uac00-\ud7af\u1100-\u11ff]", text):
        return CJK.KOREAN

    return CJK.NONE


@dataclass(slots=True, frozen=True)
class FontFamily:
    regular: Path
    bold: Path


def _font_path(font: str) -> Path:
    return ROOT / "dynamo" / "assets" / "fonts" / "static" / font


def _get_fonts(font_name: str) -> FontFamily:
    return FontFamily(regular=_font_path(f"{font_name}-Regular.ttf"), bold=_font_path(f"{font_name}-Bold.ttf"))


FONTS: dict[CJK, FontFamily] = {
    CJK.NONE: _get_fonts("NotoSans"),
    CJK.CHINESE: _get_fonts("NotoSansTC"),
    CJK.JAPANESE: _get_fonts("NotoSansJP"),
    CJK.KOREAN: _get_fonts("NotoSansKR"),
}
