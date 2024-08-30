from enum import StrEnum


class Status(StrEnum):
    SUCCESS = "\N{CHECK MARK}"
    FAILURE = "\N{CROSS MARK}"
    WARNING = "\N{WARNING SIGN}"
    OK = "\N{OK HAND SIGN}"
