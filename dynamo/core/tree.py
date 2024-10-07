from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any, Self, cast

import discord
import msgspec
import xxhash
from discord import app_commands
from discord.ext import commands

from dynamo.typedefs import AppCommandT, MaybeSnowflake

if TYPE_CHECKING:
    from dynamo.core.bot import Dynamo  # noqa: F401


log = logging.getLogger(__name__)


class Tree(app_commands.CommandTree["Dynamo"]):
    """Versionable and mentionable command tree"""

    type CommandT = commands.Command[Any, ..., Any] | app_commands.Command[Any, ..., Any] | str

    application_commands: dict[int | None, list[app_commands.AppCommand]]
    cache: dict[int | None, dict[CommandT | str, str]]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.application_commands = {}
        self.cache = {}

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
