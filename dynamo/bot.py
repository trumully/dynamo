from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import aiohttp
import discord
import discord.ext.commands as commands

import dynamo.config as config

log = logging.getLogger(__name__)

initial_extensions = (
    "dynamo.ext.events",
    "dynamo.ext.general",
    "dynamo.ext.debug",
)

description = """
Quantum entanglement.
"""


def _prefix_callable(bot: Dynamo, msg: discord.Message) -> list[str]:
    user_id = bot.user.id
    base = [f"<@{user_id}> ", f"<@!{user_id}> "]
    if msg.guild is None:
        base.append("d!")
        base.append("d?")
    else:
        base.extend(bot.prefixes.get(msg.guild.id, ["d!", "d?"]))
    return base


class Dynamo(commands.AutoShardedBot):
    user: discord.ClientUser
    logging_handler: Any
    bot_app_info: discord.AppInfo

    def __init__(self) -> None:
        self.root_path: Path = Path(__file__).parent

        allowed_mentions = discord.AllowedMentions(
            roles=False, everyone=False, users=True
        )
        intents = discord.Intents(
            guilds=True,
            members=True,
            messages=True,
            message_content=True,
        )
        super().__init__(
            command_prefix=_prefix_callable,
            description=description,
            pm_help=None,
            help_attrs=dict(hidden=True),
            chunk_guilds_at_startup=False,
            heartbeat_timeout=150.0,
            allowed_mentions=allowed_mentions,
            intents=intents,
            enable_debug_events=True,
        )

        self.client_id: str = config.client_id

    async def setup_hook(self) -> None:
        self.session = aiohttp.ClientSession()

        self.prefixes: dict[int, list[str]] = {}

        self.bot_app_info = await self.application_info()
        self.owner_id = self.bot_app_info.owner.id

        for ext in initial_extensions:
            try:
                await self.load_extension(ext)
            except Exception as exc:
                log.error(f"Failed to load extension {ext}: {exc}")

    @property
    def owner(self) -> discord.User:
        return self.bot_app_info.owner

    async def start(self) -> None:
        await super().start(config.token, reconnect=True)

    async def close(self) -> None:
        await super().close()
        await self.session.close()

    @property
    def config(self) -> None:
        return __import__("config")

    async def on_ready(self) -> None:
        if not hasattr(self, "uptime"):
            self.uptime = discord.utils.utcnow()

        log.info("Ready: %s (ID: %s)", self.user, self.user.id)
