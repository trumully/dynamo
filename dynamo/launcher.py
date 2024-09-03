import asyncio
import logging
import queue
from collections.abc import Generator
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import base2048
import click
import discord
import toml

from dynamo.bot import Dynamo
from dynamo.utils.helper import platformdir, resolve_path_with_links, valid_token

try:
    import winloop
except ImportError:
    pass
else:
    asyncio.set_event_loop_policy(winloop.EventLoopPolicy())


log = logging.getLogger("dynamo")


def get_version() -> str:
    with Path.open("pyproject.toml", mode="r") as f:
        data = toml.load(f)
    return data["tool"]["poetry"]["version"]


class RemoveNoise(logging.Filter):
    def __init__(self):
        super().__init__(name="discord.state")

    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.levelname == "WARNING" and "referencing an unknown" in record.msg)


@contextmanager
def setup_logging() -> Generator[None]:
    q: queue.SimpleQueue[Any] = queue.SimpleQueue()
    q_handler = logging.handlers.QueueHandler(q)
    stream_handler = logging.StreamHandler()

    log_path = resolve_path_with_links(platformdir.user_log_path, folder=True)
    log_location = log_path / "dynamo.log"
    rotating_file_handler = RotatingFileHandler(log_location, maxBytes=2_000_000, backupCount=5)

    discord.utils.setup_logging(handler=stream_handler)
    discord.utils.setup_logging(handler=rotating_file_handler)

    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("discord.state").addFilter(RemoveNoise())

    root_logger = logging.getLogger()
    root_logger.removeHandler(stream_handler)
    root_logger.removeHandler(rotating_file_handler)

    q_listener = logging.handlers.QueueListener(q, stream_handler, rotating_file_handler)
    root_logger.addHandler(q_handler)

    try:
        q_listener.start()
        yield
    finally:
        q_listener.stop()


async def run_bot() -> None:
    async with Dynamo() as bot:
        await bot.start(_get_token())


@click.group(invoke_without_command=True, options_metavar="[options]")
@click.version_option(
    version=get_version(),
    prog_name="dynamo",
    message=click.style("%(version)s", bold=True, fg="bright_cyan"),
)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Launch the bot"""
    if ctx.invoked_subcommand is None:
        _get_token()
        with setup_logging():
            asyncio.run(run_bot())


def _load_token() -> str | None:
    token_file_path = resolve_path_with_links(platformdir.user_config_path / "dynamo.token")
    with token_file_path.open(mode="r", encoding="utf-8") as fp:
        data = fp.read()
        return base2048.decode(data).decode("utf-8") if data else None


def _store_token(token: str, /) -> None:
    token_file_path = resolve_path_with_links(platformdir.user_config_path / "dynamo.token")
    with token_file_path.open(mode="w", encoding="utf-8") as fp:
        fp.write(base2048.encode(token.encode()))


def _get_token() -> str:
    if not (token := _load_token()):
        msg = "Token not found. Please run `dynamo setup` before starting the bot."
        raise RuntimeError(msg)
    return token


@main.command()
def setup() -> None:
    """Set the bot's token"""
    if not valid_token(token := click.prompt("Enter your bot token", hide_input=True, type=str)):
        msg = click.style(
            "\N{WARNING SIGN} WARNING: That token doesn't look right. Double check before starting the bot.",
            bold=True,
            fg="yellow",
        )
        click.echo(msg, err=True)
    _store_token(token)


@main.command()
def config() -> None:
    """Get the path to the bot's config directory"""
    click.echo(platformdir.user_config_path)


if __name__ == "__main__":
    main()
