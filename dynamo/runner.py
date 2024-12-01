from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os
import socket
import ssl
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp
import apsw
import apsw.bestpractice
import apsw.ext
import discord
import truststore
from dynaconf.validator import ValidationError  # type: ignore[reportMissingTypeStubs]
from dynamo_utils.lifecycle import AsyncLifecycle, LifecycleHooks, SignalService

from dynamo.config import get_token
from dynamo.logger import with_logging
from dynamo.typedefs import DynamoContext
from dynamo.utils.helper import platformdir

if TYPE_CHECKING:
    import signal
    from collections.abc import Callable

    from dynamo.typedefs import HasExports

log = logging.getLogger(__name__)


class DynamoHooks(
    LifecycleHooks[DynamoContext],
):
    def sync_setup(self, context: DynamoContext) -> None:
        pass

    async def async_main(self, context: DynamoContext) -> None:
        try:
            async with context.bot:
                await context.bot.start(get_token())
        except ValidationError:
            log.critical("Invalid token in config.toml")

    async def async_cleanup(self, context: DynamoContext) -> None:
        if not context.bot.is_closed():
            await context.bot.close()

        if not context.session.closed:
            await context.session.close()

    def sync_cleanup(self, context: DynamoContext) -> None:
        context.db.pragma("analysis_limit", 400)
        context.db.pragma("optimize")
        context.db.close()


def _run_bot(loop: asyncio.AbstractEventLoop) -> None:
    # Setup resources
    db_path = platformdir.user_data_path / "dynamo.db"
    conn = apsw.Connection(str(db_path))

    connector = aiohttp.TCPConnector(
        family=socket.AddressFamily.AF_INET,
        ttl_dns_cache=60,
        loop=loop,
        ssl=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
    )
    session = aiohttp.ClientSession(connector=connector)

    from .extensions import code_exec, events, identicon, info, pinned, tags

    initial_exts: list[HasExports] = [events, code_exec, tags, identicon, info, pinned]

    from dynamo.bot import Dynamo

    bot = Dynamo(
        intents=discord.Intents(
            guilds=True,
            members=True,
            messages=True,
            message_content=True,
            presences=True,
        ),
        conn=conn,
        session=session,
        initial_exts=initial_exts,
    )

    # Setup lifecycle management
    signal_queue: asyncio.Queue[signal.Signals] = asyncio.Queue()
    lifecycle = AsyncLifecycle(
        context=DynamoContext(bot, conn, session),
        loop=loop,
        signal_queue=signal_queue,
        hooks=DynamoHooks(),
    )

    # Setup signal service
    service = SignalService(
        startup=[],
        signal_handlers=[],
        joins=[],
    )
    service.add_async_lifecycle(lifecycle)

    # Run the service
    service.run()


def ensure_schema() -> None:
    """Initialize the database schema from schema.sql file."""
    db_path = platformdir.user_data_path / "dynamo.db"
    schema_location = Path(__file__).with_name("schema.sql")

    # Read and filter out comments line by line
    with schema_location.open(mode="r", encoding="utf-8") as f:
        schema = "\n".join(
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("--")
        )

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
