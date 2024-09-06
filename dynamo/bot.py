from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Coroutine, Generator
from typing import Any

import discord
import msgspec
import xxhash
from discord import app_commands
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


class VersionableTree(app_commands.CommandTree["Dynamo"]):
    def __init__(self, *args: tuple[Any, ...], **kwargs: dict[str, Any]) -> None:
        super().__init__(*args, **kwargs)
        self.application_commands: dict[int | None, list[app_commands.AppCommand]] = {}
        self.cache: dict[int | None, dict[app_commands.AppCommand | commands.HybridCommand | str, str]] = {}

    async def get_hash(self, tree: app_commands.CommandTree) -> bytes:
        commands = sorted(self._get_all_commands(guild=None), key=lambda c: c.qualified_name)

        translator = self.translator
        if translator:
            payload = [await command.get_translated_payload(tree, translator) for command in commands]
        else:
            payload = [command.to_dict(tree) for command in commands]

        return xxhash.xxh64_digest(msgspec.msgpack.encode(payload), seed=0)

    # See: https://gist.github.com/LeoCx1000/021dc52981299b95ea7790416e4f5ca4#file-mentionable_tree-py
    async def sync(
        self, *, guild: discord.abc.Snowflake | None = None
    ) -> Coroutine[Any, Any, list[app_commands.AppCommand]]:
        result = await super().sync(guild=guild)
        guild_id = guild.id if guild else None
        self.application_commands[guild_id] = result
        self.cache.pop(guild_id, None)
        return result

    async def fetch_commands(self, guild: discord.abc.Snowflake | None = None) -> list[app_commands.AppCommand]:
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

    async def find_mention_for(
        self,
        command: app_commands.AppCommand | commands.HybridCommand | str,
        *,
        guild: discord.abc.Snowflake | None = None,
    ) -> str | None:
        guild_id = guild.id if guild else None
        try:
            return self.cache[guild_id][command]
        except KeyError:
            pass

        check_global = self.fallback_to_global is True or guild is not None

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
        app_command_found = discord.utils.get(local_commands, name=(_command.root_parent or _command).name)

        if check_global and not app_command_found:
            global_commands = await self.get_or_fetch_commands(guild=None)
            app_command_found = discord.utils.get(global_commands, name=(_command.root_parent or _command).name)

        if not app_command_found:
            return None

        mention = f"</{_command.qualified_name}:{app_command_found.id}>"
        self.cache.setdefault(guild_id, {})
        self.cache[guild_id][command] = mention
        return mention

    def _walk_children(
        self, commands: list[app_commands.Group | app_commands.Command]
    ) -> Generator[app_commands.Command, None, None]:
        for command in commands:
            if isinstance(command, app_commands.Group):
                yield from self._walk_children(command.commands)
            else:
                yield command

    async def walk_mentions(
        self, *, guild: discord.abc.Snowflake | None = None
    ) -> AsyncGenerator[tuple[app_commands.Command, str], None, None]:
        for command in self._walk_children(self.get_commands(guild=guild, type=discord.AppCommandType.chat_input)):
            mention = await self.find_mention_for(command, guild=guild)
            if mention:
                yield command, mention
        if guild and self.fallback_to_global is True:
            for command in self._walk_children(self.get_commands(guild=None, type=discord.AppCommandType.chat_input)):
                mention = await self.find_mention_for(command, guild=guild)
                if mention:
                    yield command, mention
                else:
                    log.warning("Could not find a mention for command %s in the API. Are you out of sync?", command)


class EmbedMinimalHelpCommand(commands.MinimalHelpCommand):
    async def send_pages(self) -> None:
        destination = self.get_destination()
        for page in self.paginator.pages:
            e = discord.Embed(description=page)
            await destination.send(embed=e)


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
    tree: VersionableTree

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        allowed_mentions = discord.AllowedMentions(roles=False, everyone=False, users=True)
        intents = discord.Intents(
            guilds=True,
            members=True,
            messages=True,
            message_content=True,
        )
        super().__init__(
            *args,
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
            help_command=EmbedMinimalHelpCommand(),
            **kwargs,
        )

    async def setup_hook(self) -> None:
        self.prefixes: dict[int, list[str]] = {}

        self.bot_app_info = await self.application_info()
        self.owner_id = self.bot_app_info.owner.id

        for ext in initial_extensions:
            try:
                await self.load_extension(ext)
                log.debug("Loaded ext %s", ext)
            except commands.ExtensionError:
                log.exception("Failed to load extension %s", ext)

        tree_path = resolve_path_with_links(platformdir.user_cache_path / "tree.hash")
        tree_hash = await self.tree.get_hash(self.tree)
        with tree_path.open("r+b") as fp:
            data = fp.read()
            if data != tree_hash:
                log.info("Syncing commands to dev guild (ID: %s)", self.dev_guild.id)
                self.tree.copy_global_to(guild=self.dev_guild)
                await self.tree.sync(guild=self.dev_guild)
                fp.seek(0)
                fp.write(tree_hash)

        self._cd = commands.CooldownMapping.from_cooldown(2, 5, commands.BucketType.user)
        for cmd in self.walk_commands():
            cmd._buckets = self._cd

    @property
    def owner(self) -> discord.User:
        return self.bot_app_info.owner

    @property
    def dev_guild(self) -> discord.Guild:
        return discord.Object(id=681408104495448088, type=discord.Guild)

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        return await super().start(token, reconnect=reconnect)

    async def close(self) -> None:
        return await super().close()

    async def on_ready(self) -> None:
        if not hasattr(self, "uptime"):
            self.uptime = discord.utils.utcnow()

        log.info("Ready: %s (ID: %s)", self.user, self.user.id)

    async def get_context(
        self, origin: discord.Interaction | discord.Message, /, *, cls: type[Context] = Context
    ) -> Context:
        return await super().get_context(origin, cls=cls)
