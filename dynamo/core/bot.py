from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator, Generator
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import aiohttp
import apsw
import discord
import msgspec
import xxhash
from discord import app_commands
from discord.ext import commands

from dynamo._types import AppCommandT, MaybeSnowflake, RawSubmittable
from dynamo.utils.context import Context
from dynamo.utils.helper import get_cog, platformdir, resolve_path_with_links

log = logging.getLogger(__name__)

initial_extensions = tuple(get_cog(e) for e in ("errors", "help", "dev", "events", "general", "info", "tags"))

description = """
Quantum entanglement.
"""

modal_regex = re.compile(r"^m:(.{1,10}):(.*)$", flags=re.DOTALL)
button_regex = re.compile(r"^b:(.{1,10}):(.*)$", flags=re.DOTALL)


class DynamoTree(app_commands.CommandTree["Dynamo"]):
    """Versionable and mentionable command tree"""

    type CommandT = commands.Command[Any, ..., Any] | app_commands.Command[Any, ..., Any] | str

    application_commands: dict[int | None, list[app_commands.AppCommand]]
    cache: dict[int | None, dict[CommandT | str, str]]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.application_commands = {}
        self.cache = {}

    async def get_hash(self, tree: app_commands.CommandTree) -> bytes:
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
        self,
        commands: list[AppCommandT[CogT, P, T]],
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


type Interaction = discord.Interaction[Dynamo]


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
            tree_cls=DynamoTree,
            activity=discord.Activity(name="The Cursed Apple", type=discord.ActivityType.watching),
        )
        self.raw_modal_submits: dict[str, RawSubmittable] = {}
        self.raw_button_submits: dict[str, RawSubmittable] = {}

    async def setup_hook(self) -> None:
        self.prefixes: dict[int, list[str]] = {}

        self.bot_app_info = await self.application_info()
        self.owner_id = self.bot_app_info.owner.id

        self.app_emojis = Emojis(await self.fetch_application_emojis())
        self.cog_file_times: dict[str, float] = {}

        for extension in initial_extensions:
            await self.load_extension_with_timestamp(extension)

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

    def get_cog_path(self, cog: str) -> Path:
        module = import_module(cog)
        if module.__file__ is None:
            error = f"Could not determine file path for cog {cog}"
            log.exception(error)
            raise RuntimeError(error)
        return Path(module.__file__)

    async def load_extension_with_timestamp(self, extension: str) -> None:
        try:
            await self.load_extension(extension)
            self.cog_file_times[extension] = self.get_cog_path(extension).lstat().st_mtime
        except commands.ExtensionError:
            log.exception("Failed to load extension %s", extension)

    async def lazy_load_cog(self, cog_name: str) -> None:
        """Lazily load a cog if it has been modified."""
        cog_path = self.get_cog_path(cog_name)
        current_mtime = cog_path.lstat().st_mtime
        if current_mtime > self.cog_file_times.get(cog_name, 0):
            try:
                await self.reload_extension(cog_name)
                self.cog_file_times[cog_name] = current_mtime
                log.info("Reloaded modified cog: %s", cog_name)
            except commands.ExtensionError:
                log.exception("Failed to reload cog: %s", cog_name)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: Context) -> None:
        if ctx.cog:
            await self.lazy_load_cog(ctx.cog.__module__)

    @property
    def owner(self) -> discord.User:
        return self.bot_app_info.owner

    @property
    def user(self) -> discord.ClientUser:
        return cast(discord.ClientUser, super().user)

    @property
    def tree(self) -> DynamoTree:
        return cast(DynamoTree, super().tree)

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

    async def get_context[ContextT: commands.Context[Any]](
        self,
        origin: discord.Message | discord.Interaction,
        /,
        *,
        cls: type[ContextT] = Context,
    ) -> ContextT:
        return await super().get_context(origin, cls=cls)
