from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator, Generator
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Self, cast

import aiohttp
import apsw
import discord
import msgspec
import xxhash
from discord import InteractionType, app_commands
from discord.ext import commands

from dynamo.core.context import Context
from dynamo.typedefs import AppCommandT, MaybeSnowflake, RawSubmittable
from dynamo.utils.cache import LRU
from dynamo.utils.helper import platformdir, resolve_path_with_links

log = logging.getLogger(__name__)

description = """
Quantum entanglement.
"""

modal_regex = re.compile(r"^m:(.{1,10}):(.*)$", flags=re.DOTALL)
button_regex = re.compile(r"^b:(.{1,10}):(.*)$", flags=re.DOTALL)


def _prefix_callable(bot: Dynamo, msg: discord.Message) -> list[str]:
    user_id = bot.user.id
    base = [f"<@{user_id}> ", f"<@!{user_id}> "]
    if msg.guild is None:
        base.extend(["d!", "d?"])
    else:
        base.extend(bot.prefixes.get(msg.guild.id, ["d!", "d?"]))
    return base


class Emojis(dict[str, str]):
    def __init__(self, emojis: list[discord.Emoji], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        for emoji in emojis:
            self[emoji.name] = f"<{"a" if emoji.animated else ""}:{emoji.name}:{emoji.id}>"


type Interaction = discord.Interaction["Dynamo"]


class Tree(app_commands.CommandTree["Dynamo"]):
    """Versionable and mentionable command tree"""

    type CommandT = commands.Command[Any, ..., Any] | app_commands.Command[Any, ..., Any] | str

    application_commands: dict[int | None, list[app_commands.AppCommand]]
    cache: dict[int | None, dict[CommandT | str, str]]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.application_commands = {}
        self.cache = {}

    async def interaction_check(self, interaction: Interaction) -> bool:
        if is_blocked := interaction.client.is_blocked(interaction.user.id):
            response = interaction.response
            if interaction.type is InteractionType.application_command:
                await response.send_message("You are blocked from using this bot.", ephemeral=True)
            else:
                await response.defer(ephemeral=True)
        return not is_blocked

    async def get_hash(self, tree: Self) -> bytes:
        """Get the hash of the command tree."""
        commands = sorted(self._get_all_commands(guild=None), key=lambda c: c.qualified_name)

        if translator := self.translator:
            payload = [await command.get_translated_payload(tree, translator) for command in commands]
        else:
            payload = [command.to_dict(tree) for command in commands]

        return xxhash.xxh64_digest(msgspec.msgpack.encode(payload), seed=0)

    # See: https://gist.github.com/LeoCx1000/021dc52981299b95ea7790416e4f5ca4#file-mentionable_tree-py
    async def sync(self, *, guild: MaybeSnowflake = None) -> list[app_commands.AppCommand]:
        result = await super().sync(guild=guild)
        guild_id = guild.id if guild else None
        self.application_commands[guild_id] = result
        self.cache.pop(guild_id, None)
        return result

    async def fetch_commands(self, *, guild: MaybeSnowflake = None) -> list[app_commands.AppCommand]:
        result = await super().fetch_commands(guild=guild)
        guild_id = guild.id if guild else None
        self.application_commands[guild_id] = result
        self.cache.pop(guild_id, None)
        return result

    async def get_or_fetch_commands(self, guild: MaybeSnowflake = None) -> list[app_commands.AppCommand]:
        try:
            return self.application_commands[guild.id if guild else None]
        except KeyError:
            return await self.fetch_commands(guild=guild)

    async def find_mention_for(self, command: CommandT, *, guild: discord.abc.Snowflake | None = None) -> str | None:
        guild_id = guild.id if guild else None
        try:
            return self.cache[guild_id][command]
        except KeyError:
            pass

        check_global = self.fallback_to_global is True or guild is None

        if isinstance(command, str):
            # Workaround: discord.py doesn't return children from tree.get_command
            _command = discord.utils.get(self.walk_commands(guild=guild), qualified_name=command)
            if check_global and not _command:
                _command = discord.utils.get(self.walk_commands(), qualified_name=command)
        else:
            _command = cast(AppCommandT[Any, ..., Any], command)

        if not _command:
            return None

        local_commands = await self.get_or_fetch_commands(guild=guild)
        app_command_found = discord.utils.get(local_commands, name=(_command.root_parent or _command).name)

        if check_global and not app_command_found:
            global_commands = await self.get_or_fetch_commands(guild=None)
            app_command_found = discord.utils.get(global_commands, name=(_command.root_parent or _command).name)

        if not app_command_found:
            return None

        self.cache.setdefault(guild_id, {})
        self.cache[guild_id][command] = mention = f"</{_command.qualified_name}:{app_command_found.id}>"
        return mention

    def _walk_children[CogT: commands.Cog, **P, T](
        self, commands: list[AppCommandT[CogT, P, T]]
    ) -> Generator[AppCommandT[CogT, P, T], None, None]:
        for command in commands:
            if isinstance(command, app_commands.Group):
                cmds: list[AppCommandT[CogT, P, T]] = cast(list[AppCommandT[CogT, P, T]], command.commands)
                yield from self._walk_children(cmds)
            else:
                yield command

    async def walk_mentions[CogT: commands.Cog, **P, T](
        self, *, guild: MaybeSnowflake = None
    ) -> AsyncGenerator[tuple[AppCommandT[CogT, P, T], str], None]:
        commands = cast(
            list[AppCommandT[CogT, P, T]], self.get_commands(guild=guild, type=discord.AppCommandType.chat_input)
        )
        for command in self._walk_children(commands):
            mention = await self.find_mention_for(command, guild=guild)
            if mention:
                yield command, mention
        if guild and self.fallback_to_global is True:
            commands = cast(
                list[AppCommandT[CogT, P, T]], self.get_commands(guild=None, type=discord.AppCommandType.chat_input)
            )
            for command in self._walk_children(commands):
                mention = await self.find_mention_for(command, guild=guild)
                if mention:
                    yield command, mention
                else:
                    log.warning("Could not find a mention for command %s in the API. Are you out of sync?", command)


class Dynamo(commands.AutoShardedBot):
    session: aiohttp.ClientSession
    connector: aiohttp.TCPConnector
    conn: apsw.Connection
    context: Context
    logging_handler: Any
    bot_app_info: discord.AppInfo

    def __init__(self, connector: aiohttp.TCPConnector, conn: apsw.Connection, session: aiohttp.ClientSession) -> None:
        self.session = session
        self.conn = conn
        allowed_mentions = discord.AllowedMentions(roles=False, everyone=False, users=True)
        intents = discord.Intents(guilds=True, members=True, messages=True, message_content=True, presences=True)
        super().__init__(
            connector=connector,
            command_prefix=_prefix_callable,
            description=description,
            pm_help=None,
            help_attrs={"hidden": True},
            chunk_guilds_at_startup=False,
            heartbeat_timeout=150.0,
            allowed_mentions=allowed_mentions,
            intents=intents,
            enable_debug_events=True,
            tree_cls=Tree,
            activity=discord.Activity(name="The Cursed Apple", type=discord.ActivityType.watching),
        )
        self.raw_modal_submits: dict[str, RawSubmittable] = {}
        self.raw_button_submits: dict[str, RawSubmittable] = {}
        self.block_cache: LRU[int, bool] = LRU(512)

    async def setup_hook(self) -> None:
        self.prefixes: dict[int, list[str]] = {}

        self.bot_app_info = await self.application_info()
        self.owner_id = self.bot_app_info.owner.id

        self.app_emojis = Emojis(await self.fetch_application_emojis())
        self.extension_files: dict[Path, float] = {}

        self.cog_spec = find_spec("dynamo.extensions.cogs")
        if self.cog_spec is None or self.cog_spec.origin is None:
            log.critical("Failed to find cog spec! Loading without cogs.")
            return

        all_cogs = Path(self.cog_spec.origin).parent
        cog_paths = [c for c in all_cogs.rglob("**/*.py") if c.is_file() and not c.name.startswith("_")]
        for cog_path in cog_paths:
            cog_name = self.get_cog_name(cog_path.stem)
            try:
                await self.load_extension(cog_name)
            except commands.ExtensionError:
                log.exception("Failed to load cog %s", cog_name)

        tree_path = resolve_path_with_links(platformdir.user_cache_path / "tree.hash")
        tree_hash = await self.tree.get_hash(self.tree)
        with tree_path.open("r+b") as fp:
            if fp.read() == tree_hash:
                return
            log.info("Syncing commands to dev guild (ID: %s)", self.dev_guild.id)
            self.tree.copy_global_to(guild=self.dev_guild)
            await self.tree.sync(guild=self.dev_guild)
            fp.seek(0)
            fp.write(tree_hash)

    def get_cog_name(self, name: str) -> str:
        return name.lower() if self.cog_spec is None else f"{self.cog_spec.name}.{name.lower()}"

    @property
    def owner(self) -> discord.User:
        return self.bot_app_info.owner

    @property
    def user(self) -> discord.ClientUser:
        return cast(discord.ClientUser, super().user)

    @property
    def tree(self) -> Tree:
        return cast(Tree, super().tree)

    @property
    def dev_guild(self) -> discord.Guild:
        return cast(discord.Guild, discord.Object(id=681408104495448088, type=discord.Guild))

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        return await super().start(token, reconnect=reconnect)

    async def close(self) -> None:
        await self.session.close()
        await super().close()

    async def on_ready(self) -> None:
        if not hasattr(self, "uptime"):
            self.uptime = discord.utils.utcnow()

        log.info("Ready: %s (ID: %s)", self.user, self.user.id)

    async def on_interaction(self, interaction: Interaction) -> None:
        for relevant_type, regex, mapping in (
            (discord.InteractionType.modal_submit, modal_regex, self.raw_modal_submits),
            (discord.InteractionType.component, button_regex, self.raw_button_submits),
        ):
            if interaction.type is relevant_type:
                assert interaction.data is not None
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
        blocked = self.block_cache.get(user_id, None)
        if blocked is not None:
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

    async def get_context[ContextT: commands.Context[Any]](
        self,
        origin: discord.Message | discord.Interaction,
        /,
        *,
        cls: type[ContextT] = Context,
    ) -> ContextT:
        return await super().get_context(origin, cls=cls)
