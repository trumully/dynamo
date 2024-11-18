import argparse
import asyncio
import logging
import logging.handlers
import os
import socket
import ssl
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiohttp
import apsw
import apsw.bestpractice
import apsw.ext
import discord
import truststore
from dynaconf.validator import ValidationError

from dynamo.logger import with_logging
from dynamo.utils.helper import platformdir

if TYPE_CHECKING:
    from collections.abc import Callable

    from dynamo.bot import Dynamo  # noqa: TCH004
    from dynamo.types import HasExports


log = logging.getLogger(__name__)


def get_token() -> str:
    from dynamo.config import config

    return str(config.token)


async def shutdown_tasks(tasks: set[asyncio.Task[Any]]) -> None:
    """Handle graceful shutdown of remaining tasks."""
    _done, pending = await asyncio.wait(tasks, timeout=0.1)
    if not pending:
        log.debug("Clean shutdown accomplished.")
        return

    for task in tasks:
        task.cancel()

    _done, pending = await asyncio.wait(tasks, timeout=0.1)

    for task in pending:
        log.warning("Task %s wrapping coro %r did not exit properly", task.get_name(), task.get_coro())


async def cleanup_bot(bot: Dynamo, loop: asyncio.AbstractEventLoop) -> None:
    """Perform cleanup operations for the bot."""
    if not bot.is_closed():
        await bot.close()

    await asyncio.sleep(1e-3)
    tasks = {t for t in asyncio.all_tasks(loop) if not t.done()}

    if tasks:
        await shutdown_tasks(tasks)

    await loop.shutdown_asyncgens()
    await loop.shutdown_default_executor()

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


def run_bot(loop: asyncio.AbstractEventLoop) -> None:
    db_path = platformdir.user_data_path / "dynamo.db"
    conn = apsw.Connection(str(db_path))

    loop.set_task_factory(asyncio.eager_task_factory)
    asyncio.set_event_loop(loop)

    connector = aiohttp.TCPConnector(
        happy_eyeballs_delay=None,
        family=socket.AddressFamily.AF_INET,
        ttl_dns_cache=60,
        loop=loop,
        ssl=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
    )
    session = aiohttp.ClientSession(connector=connector)

    from .extensions import events, exec, identicon, info, tags

    initial_exts: list[HasExports] = [events, tags, identicon, info, exec]
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
                await bot.start(get_token())
        except ValidationError:
            log.critical("Invalid token in config.toml")
        finally:
            await cleanup_bot(bot, loop)

    try:
        loop.run_until_complete(entrypoint())
    except KeyboardInterrupt:
        pass
    finally:
        asyncio.set_event_loop(None)
        loop.close()

        conn.pragma("analysis_limit", 400)
        conn.pragma("optimize")
        conn.close()


def ensure_schema() -> None:
    """Initialize the database schema from schema.sql file."""
    db_path = platformdir.user_data_path / "dynamo.db"
    schema_location = Path(__file__).with_name("schema.sql")

    # Read and filter out comments line by line
    with schema_location.open(mode="r", encoding="utf-8") as f:
        schema = "\n".join(line.strip() for line in f if line.strip() and not line.strip().startswith("--"))

    # Execute all statements in a single connection
    with apsw.Connection(str(db_path)) as conn:
        conn.execute(schema)


def main() -> None:
    """Launch the bot."""
    parser = argparse.ArgumentParser(description="Launch Dynamo")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    ensure_schema()
    os.umask(0o077)
    to_apply: tuple[Callable[[apsw.Connection], None], ...] = (
        apsw.bestpractice.connection_wal,
        apsw.bestpractice.connection_busy_timeout,
        apsw.bestpractice.connection_enable_foreign_keys,
        apsw.bestpractice.connection_dqs,
    )
    apsw.bestpractice.apply(to_apply)
    loop = asyncio.new_event_loop()
    with with_logging(logging.DEBUG if args.debug else logging.INFO):
        if args.debug:
            log.debug("****** Running in DEBUG mode ******")
        run_bot(loop)


if __name__ == "__main__":
    main()
