from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Sequence
from typing import Any, Self, cast

import aiohttp
import apsw
import discord
import msgspec
import xxhash
from discord import InteractionType, app_commands

from dynamo.types import DynamoLike, HasExports, RawSubmittable
from dynamo.utils.cache import LRU
from dynamo.utils.helper import platformdir, resolve_path_with_links
from dynamo.utils.waterfall import Waterfall

log = logging.getLogger(__name__)

MODAL_REGEX = re.compile(r"^m:(.{1,10}):(.*)$", flags=re.DOTALL)
BUTTON_REGEX = re.compile(r"^b:(.{1,10}):(.*)$", flags=re.DOTALL)
COG_SPEC = "dynamo.extensions.cogs"

type Interaction = discord.Interaction["Dynamo"]


def _last_seen_update(conn: apsw.Connection, user_ids: Sequence[int]) -> None:
    cursor = conn.cursor()
    with conn:
        cursor.executemany(
            """
            INSERT INTO discord_users (user_id, last_interaction)
            VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id)
            DO UPDATE SET last_interaction=excluded.last_interaction;
            """,
            ((user_id,) for user_id in user_ids),
        )


class DynamoTree(app_commands.CommandTree["Dynamo"]):
    """Versionable and mentionable command tree"""

    @classmethod
    def from_dynamo(cls: type[Self], client: Dynamo) -> Self:
        installs = app_commands.AppInstallationType(user=False, guild=True)
        contexts = app_commands.AppCommandContext(dm_channel=True, guild=True, private_channel=True)
        return cls(
            client,
            fallback_to_global=False,
            allowed_contexts=contexts,
            allowed_installs=installs,
        )

    async def interaction_check(self, interaction: Interaction) -> bool:
        if is_blocked := interaction.client.is_blocked(interaction.user.id):
            response = interaction.response
            if interaction.type is InteractionType.application_command:
                await response.send_message("You are blocked from using this bot.", ephemeral=True)
            else:
                await response.defer(ephemeral=True)
        return not is_blocked

    async def get_hash(self, tree: app_commands.CommandTree) -> bytes:
        """Get the hash of the command tree."""
        commands = sorted(self._get_all_commands(guild=None), key=lambda c: c.qualified_name)

        if translator := self.translator:
            payload = [await command.get_translated_payload(tree, translator) for command in commands]
        else:
            payload = [command.to_dict(tree) for command in commands]

        return xxhash.xxh64_digest(msgspec.msgpack.encode(payload), seed=0)


class Dynamo(discord.AutoShardedClient, DynamoLike):
    """Discord bot with command handling and interaction capabilities."""

    def __init__(
        self,
        *args: Any,
        intents: discord.Intents,
        conn: apsw.Connection,
        session: aiohttp.ClientSession,
        initial_exts: list[HasExports],
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, intents=intents, **kwargs)
        self.raw_modal_submits: dict[str, RawSubmittable] = {}
        self.raw_button_submits: dict[str, RawSubmittable] = {}
        self.tree = DynamoTree.from_dynamo(self)
        self.conn: apsw.Connection = conn
        self.session: aiohttp.ClientSession = session
        self.block_cache: LRU[int, bool] = LRU(512)

        self.prefixes: dict[int, list[str]] = {}
        self.initial_exts: list[HasExports] = initial_exts

        self._last_interaction_waterfall = Waterfall(10, 100, self._update_last_seen)

    @property
    def owner(self) -> discord.User:
        return self.bot_app_info.owner

    @property
    def user(self) -> discord.ClientUser:
        return cast(discord.ClientUser, super().user)

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        self._last_interaction_waterfall.start()
        return await super().start(token, reconnect=reconnect)

    async def close(self) -> None:
        await self.session.close()
        await super().close()
        await self._last_interaction_waterfall.stop(wait=True)

    async def setup_hook(self) -> None:
        """Initialize bot and sync commands."""
        self.bot_app_info = await self.application_info()
        self.owner_id = self.bot_app_info.owner.id

        # Load commands
        for module in self.initial_exts:
            exports = module.exports
            if exports.commands:
                for command_obj in exports.commands:
                    self.tree.add_command(command_obj)
            if exports.raw_modal_submits:
                self.raw_modal_submits.update(exports.raw_modal_submits)
            if exports.raw_button_submits:
                self.raw_button_submits.update(exports.raw_button_submits)

        # Sync command tree if needed
        tree_path = platformdir.user_cache_path / "tree.hash"
        tree_path = resolve_path_with_links(tree_path)
        tree_hash = await self.tree.get_hash(self.tree)
        with tree_path.open("r+b") as fp:
            data = fp.read()
            if data != tree_hash:
                await self.tree.sync()
                fp.seek(0)
                fp.write(tree_hash)

    async def on_ready(self) -> None:
        if not hasattr(self, "uptime"):
            self.uptime = discord.utils.utcnow()
        log.info("Ready: %s (ID: %s)", self.user, self.user.id)

    async def _update_last_seen(self, user_id: Sequence[int], /) -> None:
        await asyncio.to_thread(_last_seen_update, self.conn, user_id)

    async def on_interaction(self, interaction: discord.Interaction[Self]) -> None:
        if not self.is_blocked(interaction.user.id):
            self._last_interaction_waterfall.put(interaction.user.id)

        for relevant_type, regex, mapping in (
            (discord.InteractionType.modal_submit, MODAL_REGEX, self.raw_modal_submits),
            (discord.InteractionType.component, BUTTON_REGEX, self.raw_button_submits),
        ):
            if interaction.type is not relevant_type or interaction.data is None:
                continue
            custom_id: str = cast(str, interaction.data.get("custom_id", ""))
            if match := regex.match(custom_id):
                modal_name, data = match.groups()
                if rs := mapping.get(modal_name):
                    await rs.raw_submit(interaction, data)

    def set_blocked(self, user_id: int, blocked: bool) -> None:
        self.block_cache[user_id] = blocked
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO discord_users (user_id, is_blocked)
                VALUES (?, ?)
                ON CONFLICT (user_id)
                DO UPDATE SET is_blocked=excluded.is_blocked
                """,
                (user_id, blocked),
            )

    def is_blocked(self, user_id: int) -> bool:
        if blocked := self.block_cache.get(user_id, None):
            return blocked

        cursor = self.conn.cursor()
        row = cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM discord_users
                WHERE user_id=? AND is_blocked LIMIT 1
            );
            """,
            (user_id,),
        ).fetchone()
        assert row is not None, "SELECT EXISTS top level query"
        is_blocked: bool = row[0]
        self.block_cache[user_id] = is_blocked
        return is_blocked
