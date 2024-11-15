import argparse
import asyncio
import logging
import logging.handlers
import os
import socket
import ssl
from collections.abc import Callable
from pathlib import Path
from typing import Any

import aiohttp
import apsw
import apsw.bestpractice
import apsw.ext
import discord
import truststore

from dynamo.logger import with_logging
from dynamo.types import HasExports
from dynamo.utils.helper import platformdir

log = logging.getLogger(__name__)


def get_token() -> str:
    from dynamo.config import config

    config.validators.validate()
    token: str = config.token
    return token


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
                await bot.start(get_token())
        finally:
            if not bot.is_closed():
                await bot.close()

    def stop_when_done(fut: asyncio.Future[None]) -> None:
        loop.stop()

    fut = asyncio.ensure_future(entrypoint(), loop=loop)
    try:
        fut.add_done_callback(stop_when_done)
        loop.run_forever()
    except KeyboardInterrupt:
        pass
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


def main() -> None:
    """Launch the bot"""
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
    apsw.bestpractice.apply(to_apply)  # pyright: ignore[reportUnknownMemberType]
    loop = asyncio.new_event_loop()
    log_level = logging.DEBUG if args.debug else logging.INFO
    with with_logging(log_level=log_level):
        if args.debug:
            log.debug("****** Running in DEBUG mode ******")
        run_bot(loop)


if __name__ == "__main__":
    main()
