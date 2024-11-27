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
from dynaconf.validator import ValidationError  # type: ignore[reportMissingTypeStubs]

from dynamo.config import get_token
from dynamo.logger import with_logging
from dynamo.utils.helper import platformdir

if TYPE_CHECKING:
    from collections.abc import Callable

    from dynamo.typedefs import HasExports

log = logging.getLogger(__name__)


def _run_bot(loop: asyncio.AbstractEventLoop) -> None:  # noqa: PLR0915
    db_path = platformdir.user_data_path / "dynamo.db"
    conn = apsw.Connection(str(db_path))

    loop.set_task_factory(asyncio.eager_task_factory)
    asyncio.set_event_loop(loop)

    connector = aiohttp.TCPConnector(
        family=socket.AddressFamily.AF_INET,
        ttl_dns_cache=60,
        loop=loop,
        ssl=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
    )
    session = aiohttp.ClientSession(connector=connector)

    from .extensions import code_exec, events, identicon, info, tags

    initial_exts: list[HasExports] = [events, code_exec, tags, identicon, info]

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
            if not bot.is_closed():
                await bot.close()

    def stop_when_done(_fut: asyncio.Future[None]) -> None:
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
        loop.run_until_complete(asyncio.sleep(1e-3))

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
                        },
                    )
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
    """Initialize the database schema from schema.sql file."""
    db_path = platformdir.user_data_path / "dynamo.db"
    schema_location = Path(__file__).with_name("schema.sql")

    # Read and filter out comments line by line
    with schema_location.open(mode="r", encoding="utf-8") as f:
        schema = "\n".join(line.strip() for line in f if line.strip() and not line.strip().startswith("--"))

    # Execute all statements in a single connection
    with apsw.Connection(str(db_path)) as conn:
        conn.execute(schema)


def run_bot(*, debug: bool = False) -> None:
    to_apply: tuple[Callable[[apsw.Connection], None], ...] = (
        apsw.bestpractice.connection_wal,
        apsw.bestpractice.connection_busy_timeout,
        apsw.bestpractice.connection_enable_foreign_keys,
        apsw.bestpractice.connection_dqs,
        apsw.bestpractice.connection_recursive_triggers,
        apsw.bestpractice.connection_optimize,
    )
    apsw.bestpractice.apply(to_apply)  # type: ignore[reportUnknownMemberType]
    ensure_schema()

    with with_logging(logging.DEBUG if debug else logging.INFO):
        if debug:
            log.debug("****** Running in DEBUG mode ******")

        loop = asyncio.new_event_loop()
        _run_bot(loop)

    os._exit(0)  # type: ignore[reportPrivateUsage]
