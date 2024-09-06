import asyncio
import logging
import logging.handlers
import os
import queue
import signal
import socket
import ssl
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import aiohttp
import base2048
import click
import discord
import toml
import truststore

from dynamo._evt_policy import get_event_loop_policy
from dynamo.bot import Dynamo
from dynamo.utils.helper import platformdir, resolve_path_with_links, valid_token

log = logging.getLogger(__name__)


def get_version() -> str:
    parent_dir = resolve_path_with_links(Path(__file__).parent.parent, True)
    with Path.open(parent_dir / "pyproject.toml") as f:
        data = toml.load(f)
    return data["tool"]["poetry"]["version"]


class RemoveNoise(logging.Filter):
    known_messages: tuple[str, ...] = ("referencing an unknown", "PyNaCl is not installed, voice will NOT be supported")

    def filter(self, record: logging.LogRecord) -> bool | logging.LogRecord:
        return not any(message in record.msg for message in self.known_messages)


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


def run_bot() -> None:
    policy_type = get_event_loop_policy()
    asyncio.set_event_loop_policy(policy_type())

    log.debug("Event loop policy: %s", policy_type.__name__)

    loop = asyncio.new_event_loop()
    loop.set_task_factory(asyncio.eager_task_factory)
    asyncio.set_event_loop(loop)

    # https://github.com/aio-libs/aiohttp/issues/8599
    # https://github.com/mikeshardmind/discord.py/tree/salamander-reloaded
    connector = aiohttp.TCPConnector(
        happy_eyeballs_delay=None,
        family=socket.AddressFamily.AF_INET,
        ttl_dns_cache=60,
        loop=loop,
        ssl=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
    )

    bot = Dynamo(connector=connector)

    async def entrypoint() -> None:
        try:
            async with bot:
                await bot.start(_get_token())
        finally:
            if not bot.is_closed():
                await bot.close()

    try:
        loop.add_signal_handler(signal.SIGINT, lambda: loop.stop())
        loop.add_signal_handler(signal.SIGTERM, lambda: loop.stop())
    except NotImplementedError:
        pass

    def stop_when_done(fut: asyncio.Future[None]) -> None:
        loop.stop()

    fut = asyncio.ensure_future(entrypoint(), loop=loop)
    try:
        fut.add_done_callback(stop_when_done)
        loop.run_forever()
    except KeyboardInterrupt:
        log.info("Shutdown via keyboard interrupt")
    finally:
        fut.remove_done_callback(stop_when_done)
        if not bot.is_closed():
            _close_task = loop.create_task(bot.close())  # noqa: RUF006
        loop.run_until_complete(asyncio.sleep(0.001))

        tasks: set[asyncio.Task[Any]] = {t for t in asyncio.all_tasks(loop) if not t.done()}

        async def limited_finalization() -> None:
            _done, pending = await asyncio.wait(tasks, timeout=0.1)
            if not pending:
                log.debug("Clean shutdown accomplished.")
                return

            for task in tasks:
                task.cancel()

            _done, pending = await asyncio.wait(tasks, timeout=0.1)

            for task in pending:
                name = task.get_name()
                coro = task.get_coro()
                log.warning("Task %s wrapping coro %r did not exit properly", name, coro)

        if tasks:
            loop.run_until_complete(limited_finalization())
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(loop.shutdown_default_executor())

        for task in tasks:
            try:
                if (exc := task.exception()) is not None:
                    loop.call_exception_handler(
                        {
                            "message": "Unhandled exception in task during shutdown.",
                            "exception": exc,
                            "task": task,
                        }
                    )
            except (asyncio.InvalidStateError, asyncio.CancelledError):
                pass

        asyncio.set_event_loop(None)
        loop.close()

        if not fut.cancelled():
            try:
                fut.result()
            except KeyboardInterrupt:
                pass


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


@click.group(invoke_without_command=True, options_metavar="[options]")
@click.version_option(
    version=get_version(),
    prog_name="Dynamo",
    message=click.style("%(prog)s - %(version)s", bold=True, fg="bright_cyan"),
)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Launch the bot"""
    os.umask(0o077)
    if ctx.invoked_subcommand is None:
        with setup_logging():
            run_bot()


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
