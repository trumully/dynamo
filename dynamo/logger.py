import logging
import logging.handlers
import os
import queue
import sys
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Final, Protocol, TypeVar, runtime_checkable

import apsw
import apsw.ext

from dynamo.utils.helper import platformdir, resolve_folder_with_links

_T_contra = TypeVar("_T_contra", contravariant=True)


class SupportsWrite(Protocol[_T_contra]):
    def write(self, s: _T_contra, /) -> object: ...


@runtime_checkable
class TTYSupportsWrite(SupportsWrite[_T_contra], Protocol):
    def isatty(self) -> bool: ...


type Stream[T] = SupportsWrite[T] | TTYSupportsWrite[T]


class KnownWarningFilter(logging.Filter):
    known_messages: tuple[str, ...] = (
        "referencing an unknown",
        "PyNaCl is not installed, voice will NOT be supported",
    )

    def filter(self, record: logging.LogRecord) -> bool | logging.LogRecord:
        return record.msg not in self.known_messages


DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
FORMAT = logging.Formatter(
    "[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s", DATE_FORMAT
)

_MSG_PREFIX = "\x1b[30;1m%(asctime)s\x1b[0m "
_MSG_POSTFIX = "%(levelname)-8s\x1b[0m \x1b[35m%(name)s\x1b[0m: %(message)s"


class AnsiFormatter(logging.Formatter):
    LEVEL_TO_COLOR = (
        (logging.DEBUG, "\x1b[40;1m"),
        (logging.INFO, "\x1b[34;1m"),
        (logging.WARNING, "\x1b[33;1m"),
        (logging.ERROR, "\x1b[31m"),
        (logging.CRITICAL, "\x1b[41m"),
    )

    FORMATS: Final = {
        level: logging.Formatter(_MSG_PREFIX + color + _MSG_POSTFIX, DATE_FORMAT)
        for level, color in LEVEL_TO_COLOR
    }

    def format(self, record: logging.LogRecord) -> str:
        if (formatter := self.FORMATS.get(record.levelno)) is None:
            formatter = self.FORMATS[logging.DEBUG]
        if record.exc_info:
            text = formatter.formatException(record.exc_info)
            record.exc_text = f"\x1b[31m{text}\x1b[0m"
        output = formatter.format(record)
        record.exc_text = None
        return output


def use_color_formatting(stream: Stream[str]) -> bool:
    is_a_tty = isinstance(stream, TTYSupportsWrite) and stream.isatty()

    if os.environ.get("TERM_PROGRAM") == "vscode":
        return is_a_tty

    if sys.platform == "win32":
        if "WT_SESSION" not in os.environ:
            return False

    return is_a_tty


@contextmanager
def with_logging(log_level: int = logging.INFO) -> Generator[None]:
    q: queue.SimpleQueue[Any] = queue.SimpleQueue()
    q_handler = logging.handlers.QueueHandler(q)
    q_handler.addFilter(KnownWarningFilter())
    stream_handler = logging.StreamHandler()

    log_location = resolve_folder_with_links(platformdir.user_log_path) / "dynamo.log"
    rotating_file_handler = logging.handlers.RotatingFileHandler(
        log_location,
        maxBytes=2_000_000,
        backupCount=5,
    )

    if use_color_formatting(sys.stderr):
        stream_handler.setFormatter(AnsiFormatter())
    else:
        stream_handler.setFormatter(FORMAT)

    rotating_file_handler.setFormatter(FORMAT)

    q_listener = logging.handlers.QueueListener(q, stream_handler, rotating_file_handler)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(q_handler)

    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.client").setLevel(logging.INFO)

    apsw_log = logging.getLogger("apsw_forwarded")
    apsw.ext.log_sqlite(logger=apsw_log)

    try:
        q_listener.start()
        yield
    finally:
        q_listener.stop()
