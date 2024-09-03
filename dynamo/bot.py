from __future__ import annotations

import logging
from typing import Any

import aiohttp
import discord
import msgspec
import xxhash
from discord.ext import commands

from dynamo.utils.context import Context
from dynamo.utils.helper import platformdir, resolve_path_with_links

log = logging.getLogger(__name__)

initial_extensions = (
    "dynamo.ext.events",
    "dynamo.ext.general",
    "dynamo.ext.debug",
)

description = """
Quantum entanglement.
"""


class VersionableTree(discord.app_commands.CommandTree["Dynamo"]):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.client.is_blocked(interaction.user.id):
            await interaction.response.send_message("You are blocked.", ephemeral=True)
            return False
        return True

    async def get_hash(self, tree: discord.app_commands.CommandTree) -> bytes:
        commands = sorted(self._get_all_commands(guild=None), key=lambda c: c.qualified_name)

        translator = self.translator
        if translator:
            payload = [await command.get_translated_payload(tree, translator) for command in commands]
        else:
            payload = [command.to_dict(tree) for command in commands]

        return xxhash.xxh64_digest(msgspec.msgpack.encode(payload), seed=0)


def _prefix_callable(bot: Dynamo, msg: discord.Message) -> list[str]:
    user_id = bot.user.id
    base = [f"<@{user_id}> ", f"<@!{user_id}> "]
    if msg.guild is None:
        base.extend(["d!", "d?"])
    else:
        base.extend(bot.prefixes.get(msg.guild.id, ["d!", "d?"]))
    return base


class Dynamo(commands.AutoShardedBot):
    user: discord.ClientUser
    logging_handler: Any
    bot_app_info: discord.AppInfo

    def __init__(self) -> None:
        allowed_mentions = discord.AllowedMentions(roles=False, everyone=False, users=True)
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
            help_attrs={"hidden": True},
            chunk_guilds_at_startup=False,
            heartbeat_timeout=150.0,
            allowed_mentions=allowed_mentions,
            intents=intents,
            enable_debug_events=True,
            tree_cls=VersionableTree,
        )

    async def setup_hook(self) -> None:
        self.session: aiohttp.ClientSession = aiohttp.ClientSession()
        self.prefixes: dict[int, list[str]] = {}

        self.bot_app_info = await self.application_info()
        self.owner_id = self.bot_app_info.owner.id

        tree_path = platformdir.user_cache_path / "tree.hash"
        tree_path = resolve_path_with_links(tree_path)
        tree_hash = await self.tree.get_hash(self.tree)
        with tree_path.open("r+b") as fp:
            data = fp.read()
            if data != tree_hash:
                await self.tree.sync(guild=None)
                fp.seek(0)
                fp.write(tree_hash)

        for ext in initial_extensions:
            try:
                await self.load_extension(ext)
                log.debug("Loaded ext %s", ext)
            except commands.ExtensionError:
                log.exception("Failed to load extension %s", ext)

    @property
    def owner(self) -> discord.User:
        return self.bot_app_info.owner

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        return await super().start(token, reconnect=reconnect)

    async def close(self) -> None:
        await self.session.close()
        await super().close()

    async def on_ready(self) -> None:
        if not hasattr(self, "uptime"):
            self.uptime = discord.utils.utcnow()

        log.info("Ready: %s (ID: %s)", self.user, self.user.id)

    async def get_context(
        self, origin: discord.Interaction | discord.Message, /, *, cls: type[Context] = Context
    ) -> Context:
        return await super().get_context(origin, cls=cls)
