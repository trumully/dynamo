import asyncio
import logging
import logging.handlers
import os
import socket
import ssl
from collections.abc import Callable
from importlib import metadata
from pathlib import Path
from typing import Any

import aiohttp
import apsw
import apsw.bestpractice
import apsw.ext
import base2048
import click
import discord
import truststore

from dynamo.logger import with_logging
from dynamo.types import HasExports
from dynamo.utils.helper import platformdir, resolve_path_with_links, valid_token

log = logging.getLogger(__name__)


def run_bot(loop: asyncio.AbstractEventLoop) -> None:
    db_path = platformdir.user_data_path / "dynamo.db"
    conn = apsw.Connection(str(db_path))

    loop.set_task_factory(asyncio.eager_task_factory)
    asyncio.set_event_loop(loop)

    # https://github.com/aio-libs/aiohttp/issues/8599
    # https://github.com/mikeshardmind/salamander-reloaded
    connector = aiohttp.TCPConnector(
        happy_eyeballs_delay=None,
        family=socket.AddressFamily.AF_INET,
        ttl_dns_cache=60,
        loop=loop,
        ssl=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
    )
    session = aiohttp.ClientSession(connector=connector)

    from .extensions import events, identicon, info, settings, tags

    initial_exts: list[HasExports] = [events, tags, identicon, info, settings]

    from dynamo.bot import Dynamo

    bot = Dynamo(
        intents=discord.Intents(guilds=True, members=True, messages=True, message_content=True, presences=True),
        conn=conn,
        session=session,
        initial_exts=initial_exts,
    )

    async def entrypoint() -> None:
        try:
            async with bot:
                await bot.start(_get_token())
        finally:
            if not bot.is_closed():
                await bot.close()

    def stop_when_done(fut: asyncio.Future[None]) -> None:
        loop.stop()

    fut = asyncio.ensure_future(entrypoint(), loop=loop)
    try:
        fut.add_done_callback(stop_when_done)
        loop.run_forever()
    finally:
        fut.remove_done_callback(stop_when_done)
        if not bot.is_closed():
            _close_task = loop.create_task(bot.close())
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
                    loop.call_exception_handler({
                        "message": "Unhandled exception in task during shutdown.",
                        "exception": exc,
                        "task": task,
                    })
            except (asyncio.InvalidStateError, asyncio.CancelledError):
                pass

        asyncio.set_event_loop(None)
        loop.close()

        if not fut.cancelled():
            fut.result()

    conn.pragma("analysis_limit", 400)
    conn.pragma("optimize")
    conn.close()


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
        raise RuntimeError(msg) from None
    return token


def ensure_schema() -> None:
    db_path = platformdir.user_data_path / "dynamo.db"
    conn = apsw.Connection(str(db_path))

    schema_location = (Path(__file__)).with_name("schema.sql")
    to_execute: list[str] = []
    with schema_location.open(mode="r", encoding="utf-8") as fp:
        for line in fp.readlines():
            if (text := line.strip()).startswith("--"):
                continue
            to_execute.append(text)

    for line in (iterator := iter(to_execute)):
        s = [line]
        while n := next(iterator, None):
            s.append(n)
        statement = "\n".join(s)
        list(conn.execute(statement))


@click.group(invoke_without_command=True, options_metavar="[options]")
@click.version_option(
    metadata.version("dynamo"),
    "-v",
    "--version",
    package_name="Dynamo",
    prog_name="dynamo",
    message=click.style("%(prog)s", fg="yellow") + click.style(" %(version)s", fg="bright_cyan"),
)
@click.option("--debug", "-d", is_flag=True, help="Set log level to debug")
@click.pass_context
def main(ctx: click.Context, debug: bool) -> None:
    """Launch the bot"""
    ensure_schema()
    os.umask(0o077)
    to_apply: tuple[Callable[[apsw.Connection], None], ...] = (
        apsw.bestpractice.connection_wal,
        apsw.bestpractice.connection_busy_timeout,
        apsw.bestpractice.connection_enable_foreign_keys,
        apsw.bestpractice.connection_dqs,
    )
    apsw.bestpractice.apply(to_apply)  # pyright: ignore[reportUnknownMemberType]
    if ctx.invoked_subcommand is None:
        if (log_level := logging.DEBUG if debug else logging.INFO) == logging.DEBUG:
            click.echo("Running in DEBUG mode", err=True)
        loop = asyncio.new_event_loop()
        with with_logging(log_level=log_level):
            run_bot(loop)


@main.command(name="help")
@click.pass_context
def dynamo_help(ctx: click.Context) -> None:
    """Show this message and exit."""
    if ctx.parent is not None:
        click.echo(ctx.parent.get_help())


@main.command()
def setup() -> None:
    """Set the bot's token"""
    if not valid_token(token := click.prompt("Enter your bot token", hide_input=True, type=str)):
        text = "\N{WARNING SIGN} WARNING: That token doesn't look right. Double check before starting the bot."
        msg = click.style(text, bold=True, fg="yellow")
        click.echo(msg, err=True)
    _store_token(token)


@main.command()
def config() -> None:
    """Get the path to the bot's config directory"""
    click.echo(platformdir.user_config_path)


if __name__ == "__main__":
    main()
