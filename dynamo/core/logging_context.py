import logging
import logging.handlers
import queue
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import discord

from dynamo.utils.helper import platformdir, resolve_path_with_links

known_messages: tuple[str, ...] = ("referencing an unknown", "PyNaCl is not installed, voice will NOT be supported")


class RemoveNoise(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool | logging.LogRecord:
        return not any(message in record.msg for message in known_messages)


@contextmanager
def setup_logging(log_level: int = logging.INFO) -> Generator[None, Any, None]:
    q: queue.SimpleQueue[Any] = queue.SimpleQueue()
    q_handler = logging.handlers.QueueHandler(q)
    q_handler.addFilter(RemoveNoise())
    stream_handler = logging.StreamHandler()

    log_path = resolve_path_with_links(platformdir.user_log_path, folder=True)
    log_location = log_path / "dynamo.log"
    rotating_file_handler = logging.handlers.RotatingFileHandler(log_location, maxBytes=2_000_000, backupCount=5)

    discord.utils.setup_logging(handler=stream_handler)
    discord.utils.setup_logging(handler=rotating_file_handler)

    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("discord.state")

    root_logger = logging.getLogger()
    root_logger.removeHandler(stream_handler)
    root_logger.removeHandler(rotating_file_handler)

    root_logger.setLevel(log_level)

    q_listener = logging.handlers.QueueListener(q, stream_handler, rotating_file_handler)
    root_logger.addHandler(q_handler)

    try:
        q_listener.start()
        yield
    finally:
        q_listener.stop()
