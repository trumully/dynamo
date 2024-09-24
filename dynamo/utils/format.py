import datetime
import re
from dataclasses import dataclass
from enum import StrEnum, auto
from pathlib import Path
from typing import Sequence

from dynamo.utils.helper import ROOT, resolve_path_with_links


def shorten_string(string: str, max_len: int = 50, placeholder: str = "Nothing provided") -> str:
    """
    Truncate a string to a maximum length.

    Parameters
    ----------
    string : str
        The string to truncate.
    max_len : int, optional
        Maximum length of the truncated string, by default 50.
    placeholder : str, optional
        String to return if input is empty, by default "Nothing provided".

    Returns
    -------
    str
        The truncated string.

    Examples
    --------
    >>> shorten_string("Very very very long text way over the max yada yada yada")
    'Very very very long text way over the max...'
    """
    if not string:
        return placeholder

    return string if len(string) <= max_len else string[:max_len] + "..."


@dataclass(frozen=True)
class plural:
    """
    A class to handle plural formatting of values.

    Parameters
    ----------
    value : int
        The numeric value to format.

    Methods
    -------
    __format__(format_spec: str) -> str
        Format the value with singular or plural form based on the format specification.
    """

    value: int

    def __format__(self, format_spec: str) -> str:
        """
        Format the value with singular or plural form.

        Parameters
        ----------
        format_spec : str
            The format specification string.

        Returns
        -------
        str
            Formatted string with appropriate singular or plural form.
        """
        v = self.value
        skip_value = format_spec.endswith("!")
        if skip_value:
            format_spec = format_spec[:-1]

        singular, _, plural = format_spec.partition("|")
        plural = plural or f"{singular}s"
        if skip_value:
            return plural if abs(v) != 1 else singular

        return f"{v} {plural}" if abs(v) != 1 else f"{v} {singular}"


def format_dt(dt: datetime.datetime, style: str | None = None) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    return f"<t:{int(dt.timestamp())}>" if style is None else f"<t:{int(dt.timestamp())}:{style}>"


def human_join(seq: Sequence[str], sep: str = ", ", conjunction: str = "or", *, oxford_comma: bool = True) -> str:
    """
    Join a sequence of strings into a human-readable format.

    Parameters
    ----------
    seq : Sequence[str]
        The sequence of strings to join.
    sep : str, optional
        The separator to use between the strings, by default ", ".
    conjunction : str, optional
        The word to use before the last string, by default "or".
    oxford_comma : bool, optional
        Whether to use an oxford comma, by default True.

    Returns
    -------
    str
        A human-readable string.

    Examples
    --------
    >>> human_join(["apple", "banana", "cherry"])
    'apple, banana, or cherry'
    >>> human_join(["dog", "cat"], conjunction="and")
    'dog and cat'
    """
    if (size := len(seq)) == 0:
        return ""

    if size == 1:
        return seq[0]

    if size == 2:
        return f"{seq[0]} {conjunction} {seq[1]}"

    return f"{sep.join(seq[:-1])}{sep if oxford_comma else " "}{conjunction} {seq[-1]}"


def code_block(content: str, language: str = "") -> str:
    return f"```{language}\n{content}\n```"


class CJK(StrEnum):
    CHINESE = auto()
    JAPANESE = auto()
    KOREAN = auto()
    NONE = auto()


def is_cjk(text: str) -> CJK:
    """
    Check if a string contains any CJK characters.

    Parameters
    ----------
    text : str
        The string to check.

    Returns
    -------
    CJK
        The CJK language of the string.
    """
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


STATIC_FONT_PATH = Path(ROOT / "assets" / "fonts" / "static")


latin: FontFamily = FontFamily(
    regular=resolve_path_with_links(STATIC_FONT_PATH / "NotoSans-Regular.ttf"),
    bold=resolve_path_with_links(STATIC_FONT_PATH / "NotoSans-Bold.ttf"),
)

chinese: FontFamily = FontFamily(
    regular=resolve_path_with_links(STATIC_FONT_PATH / "NotoSansTC-Regular.ttf"),
    bold=resolve_path_with_links(STATIC_FONT_PATH / "NotoSansTC-Bold.ttf"),
)

japanese: FontFamily = FontFamily(
    regular=resolve_path_with_links(STATIC_FONT_PATH / "NotoSansJP-Regular.ttf"),
    bold=resolve_path_with_links(STATIC_FONT_PATH / "NotoSansJP-Bold.ttf"),
)

korean: FontFamily = FontFamily(
    regular=resolve_path_with_links(STATIC_FONT_PATH / "NotoSansKR-Regular.ttf"),
    bold=resolve_path_with_links(STATIC_FONT_PATH / "NotoSansKR-Bold.ttf"),
)

FONTS: dict[CJK, FontFamily] = {
    CJK.NONE: latin,
    CJK.CHINESE: chinese,
    CJK.JAPANESE: japanese,
    CJK.KOREAN: korean,
}
