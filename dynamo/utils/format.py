import datetime
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path

from dynamo.utils.helper import ROOT

log = logging.getLogger(__name__)


def shorten_string(string: str, max_len: int = 50, placeholder: str = "Nothing provided") -> str:
    """Truncate a string to a maximum length."""
    if not string:
        return placeholder

    return string if len(string) <= max_len else string[:max_len] + "..."


@dataclass(frozen=True)
class plural:
    """A class to handle plural formatting of values."""

    value: int

    def __format__(self, format_spec: str) -> str:
        """Format the value with singular or plural form."""
        v = self.value
        if skip_value := format_spec.endswith("!"):
            format_spec = format_spec[:-1]

        singular, _, plural = format_spec.partition("|")
        plural = plural or f"{singular}s"
        if skip_value:
            return plural if abs(v) != 1 else singular

        return f"{v} {plural}" if abs(v) != 1 else f"{v} {singular}"


def format_datetime(dt: datetime.datetime, style: str | None = None) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.UTC)

    return f"<t:{int(dt.timestamp())}>" if style is None else f"<t:{int(dt.timestamp())}:{style}>"


def human_join(seq: Sequence[str], sep: str = ", ", conjunction: str = "or", *, oxford_comma: bool = True) -> str:
    """Join a sequence of strings into a human-readable format."""
    if (size := len(seq)) == 0:
        return ""

    if size == 1:
        return seq[0]

    if size == 2:
        return f"{seq[0]} {conjunction} {seq[1]}"

    return f"{sep.join(seq[:-1])}{sep if oxford_comma else " "}{conjunction} {seq[-1]}"


def code_block(content: str, language: str = "", *, line_numbers: bool = False) -> str:
    if line_numbers:
        lines = content.split("\n")
        numbered_lines = [f"{i + 1:2d} {line}" for i, line in enumerate(lines)]
        numbered_content = "\n".join(numbered_lines)
        return f"```{language}\n{numbered_content}\n```"
    return f"```{language}\n{content}\n```"


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
