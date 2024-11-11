from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator, Generator
from typing import Any, Self, cast

import aiohttp
import apsw
import discord
import msgspec
import xxhash
from discord import InteractionType, app_commands

from dynamo.types import AppCommandT, DynamoLike, Emojis, HasExports, RawSubmittable
from dynamo.utils.cache import LRU
from dynamo.utils.helper import platformdir, resolve_path_with_links

log = logging.getLogger(__name__)

MODAL_REGEX = re.compile(r"^m:(.{1,10}):(.*)$", flags=re.DOTALL)
BUTTON_REGEX = re.compile(r"^b:(.{1,10}):(.*)$", flags=re.DOTALL)
COG_SPEC = "dynamo.extensions.cogs"

type Interaction = discord.Interaction["Dynamo"]

WARMUP_GUILDS = {681408104495448088, 696276827341324318}


class DynamoTree(app_commands.CommandTree["Dynamo"]):
    """Versionable and mentionable command tree"""

    application_commands: dict[int | None, list[app_commands.AppCommand]]
    cache: dict[int | None, LRU[AppCommandT | str, str]]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.application_commands = {}
        self.cache = {}

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

    # See: https://gist.github.com/LeoCx1000/021dc52981299b95ea7790416e4f5ca4#file-mentionable_tree-py
    async def sync(self, *, guild: discord.abc.Snowflake | None = None) -> list[app_commands.AppCommand]:
        result = await super().sync(guild=guild)
        guild_id = guild.id if guild else None
        self.application_commands[guild_id] = result
        self.cache.pop(guild_id, None)
        return result

    async def fetch_commands(self, *, guild: discord.abc.Snowflake | None = None) -> list[app_commands.AppCommand]:
        result = await super().fetch_commands(guild=guild)
        guild_id = guild.id if guild else None
        self.application_commands[guild_id] = result
        self.cache.pop(guild_id, None)
        return result

    async def get_or_fetch_commands(self, guild: discord.abc.Snowflake | None = None) -> list[app_commands.AppCommand]:
        try:
            return self.application_commands[guild.id if guild else None]
        except KeyError:
            return await self.fetch_commands(guild=guild)

    async def find_mention_for(self, command: AppCommandT, *, guild: discord.abc.Snowflake | None = None) -> str | None:
        guild_id = guild.id if guild else None
        try:
            return self.cache[guild_id].get(command)
        except KeyError:
            pass

        check_global = self.fallback_to_global is True or guild is None

        if isinstance(command, str):
            # Workaround: discord.py doesn't return children from tree.get_command
            _command = discord.utils.get(self.walk_commands(guild=guild), qualified_name=command)
            if check_global and not _command:
                _command = discord.utils.get(self.walk_commands(), qualified_name=command)
        else:
            _command = command

        if not _command:
            return None

        local_commands = await self.get_or_fetch_commands(guild=guild)
        root_command = _command.root_parent or _command
        app_command_found = discord.utils.get(local_commands, name=root_command.name)

        if check_global and not app_command_found:
            global_commands = await self.get_or_fetch_commands(guild=None)
            app_command_found = discord.utils.get(global_commands, name=(_command.root_parent or _command).name)

        if not app_command_found:
            return None

        self.cache.setdefault(guild_id, LRU(256))
        self.cache[guild_id][command] = mention = f"</{_command.qualified_name}:{app_command_found.id}>"
        return mention

    def _walk_children(self, commands: list[AppCommandT]) -> Generator[AppCommandT]:
        for command in commands:
            if isinstance(command, app_commands.Group):
                cmds: list[AppCommandT] = cast(list[AppCommandT], command.commands)
                yield from self._walk_children(cmds)
            else:
                yield command

    async def walk_mentions(
        self, *, guild: discord.abc.Snowflake | None = None
    ) -> AsyncGenerator[tuple[AppCommandT, str]]:
        commands = cast(list[AppCommandT], self.get_commands(guild=guild, type=discord.AppCommandType.chat_input))
        for command in self._walk_children(commands):
            mention = await self.find_mention_for(command, guild=guild)
            if mention:
                yield command, mention
        if guild and self.fallback_to_global is True:
            commands = cast(list[AppCommandT], self.get_commands(guild=None, type=discord.AppCommandType.chat_input))
            for command in self._walk_children(commands):
                mention = await self.find_mention_for(command, guild=guild)
                if mention:
                    yield command, mention
                else:
                    log.warning("Could not find a mention for command %s in the API. Are you out of sync?", command)


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

        self.guild_events: LRU[int, list[discord.ScheduledEvent]] = LRU(128)

    @property
    def owner(self) -> discord.User:
        return self.bot_app_info.owner

    @property
    def user(self) -> discord.ClientUser:
        return cast(discord.ClientUser, super().user)

    @property
    def dev_guild(self) -> discord.Guild:
        return cast(discord.Guild, discord.Object(id=681408104495448088, type=discord.Guild))

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        return await super().start(token, reconnect=reconnect)

    async def close(self) -> None:
        await self.session.close()
        await super().close()

    async def setup_hook(self) -> None:
        """Initialize bot and sync commands."""
        self.bot_app_info = await self.application_info()
        self.owner_id = self.bot_app_info.owner.id
        self.app_emojis = Emojis(await self.fetch_application_emojis())

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

        events_path = platformdir.user_cache_path / "events.hash"
        events_path = resolve_path_with_links(events_path)

    async def on_ready(self) -> None:
        if not hasattr(self, "uptime"):
            self.uptime = discord.utils.utcnow()
        log.info("Ready: %s (ID: %s)", self.user, self.user.id)

    async def on_interaction(self, interaction: Interaction) -> None:
        for relevant_type, regex, mapping in (
            (discord.InteractionType.modal_submit, MODAL_REGEX, self.raw_modal_submits),
            (discord.InteractionType.component, BUTTON_REGEX, self.raw_button_submits),
        ):
            if interaction.type is not relevant_type or interaction.data is None:
                continue
            custom_id = interaction.data.get("custom_id", "")
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
        if blocked := self.block_cache.get(user_id):
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
