from dataclasses import dataclass
from typing import Sequence


def shorten_string(string: str, max_len: int = 50, placeholder: str = "Nothing provided") -> str:
    """Truncate a string to a maximum length of `max_len`

    Example:
        Very very very long text way over the max yada yada yada
        -> Very very very long text way over the max...

    Args:
        description (str): The string to truncate
        max_len (int, optional): Maximum length. Defaults to 50.

    Returns:
        str: The truncated string
    """
    if not string:
        return placeholder
    if len(string) <= max_len:
        return string
    return string[:max_len] + "..."


@dataclass(frozen=True)
class plural:
    value: int

    def __format__(self, format_spec: str) -> str:
        v = self.value
        skip_value = format_spec.endswith("!")
        if skip_value:
            format_spec = format_spec[:-1]

        singular, _, plural = format_spec.partition("|")
        plural = plural or f"{singular}s"
        if skip_value:
            return plural if abs(v) != 1 else singular

        return f"{v} {plural}" if abs(v) != 1 else f"{v} {singular}"


def human_join(seq: Sequence[str], sep: str = ", ", conjunction: str = "or", *, oxford_comma: bool = True) -> str:
    """Join a sequence of strings into a human-readable format.

    Args:
        seq (Sequence[str]): The sequence of strings to join.
        sep (str, optional): The separator to use between the strings. Defaults to ", ".
        conjunction (str, optional): The word to use before the last string. Defaults to "or".
        oxford_comma (bool, optional): Whether to use an oxford comma. Defaults to True.

    Returns:
        str: A human-readable string.
    """
    if (size := len(seq)) == 0:
        return ""

    if size == 1:
        return seq[0]

    if size == 2:
        return f"{seq[0]} {conjunction} {seq[1]}"

    return f"{sep.join(seq[:-1])}{sep if oxford_comma else " "}{conjunction} {seq[-1]}"
