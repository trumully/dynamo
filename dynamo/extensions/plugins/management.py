import contextlib
import itertools
import logging
from collections.abc import Iterable, Mapping
from types import ModuleType
from typing import Any

import discord
from discord.ext import commands

from dynamo.extensions.plugins import Plugin
from dynamo.typedefs import ContextT, CoroFunction

from .utils.context import copy_context_with

log = logging.getLogger(__name__)

_ExtensionConverterBase = commands.Converter[list[str]]


def resolve_extensions(extensions: Mapping[str, ModuleType], name: str) -> list[str]:
    resolved: list[str] = []
    for extension in name.split():
        if extension == "*":
            resolved.extend(extensions)
        else:
            resolved.append(extension)

    return resolved


class ExtensionConverter(_ExtensionConverterBase):
    async def convert(self, ctx: ContextT, argument: str) -> list[str]:
        try:
            return resolve_extensions(ctx.bot.extensions, argument)
        except Exception as e:
            raise commands.BadArgument(str(e)) from e


async def try_extension_method(method: CoroFunction[[str], None], extension: str) -> bool:
    success = True
    try:
        await discord.utils.maybe_coroutine(method, extension)
    except (commands.ExtensionFailed, Exception):
        log.exception("Method %s(%s) failed", method.__name__, extension)
        success = False
    return success


class ManagementPlugin(Plugin):
    @Plugin.Command(parent="dynamo", name="load", aliases=["reload"])
    async def load(self, ctx: ContextT, *extensions: ExtensionConverter) -> None:
        """Load an extension."""
        iterable_extensions: Iterable[str] = extensions  # type: ignore

        failed = False
        for extension in itertools.chain(*iterable_extensions):
            method = self.bot.load_extension if extension not in self.bot.extensions else self.bot.reload_extension
            if not await try_extension_method(method, extension):
                failed = True

        await ctx.send(f"Done. {"Some failed to load, check logs." if failed else ""}")

    @Plugin.Command(parent="dynamo", name="unload")
    async def unload(self, ctx: ContextT, *extensions: ExtensionConverter) -> None:
        """Unload an extension."""
        iterable_extensions: Iterable[str] = extensions  # type: ignore

        failed = False
        for extension in itertools.chain(*iterable_extensions):
            if not await try_extension_method(self.bot.unload_extension, extension):
                failed = True

        await ctx.send(f"Done. {"Some failed to unload, check logs." if failed else ""}")

    @Plugin.Command(parent="dynamo", name="quit", aliases=["q"])
    async def quit(self, ctx: ContextT) -> None:
        """Quit the bot."""
        await ctx.send("Quitting...")
        await self.bot.close()

    @Plugin.Command(parent="dynamo", name="exec")
    async def exec_as(self, ctx: ContextT, user: discord.User | discord.Member, *, command_string: str) -> None:
        """Execute a command as another user."""
        kwargs: dict[str, Any] = {}

        if ctx.prefix:
            kwargs["content"] = ctx.prefix + command_string.lstrip("/")
        else:
            await ctx.send("Reparsing requires a prefix")
            return

        if ctx.guild:
            target_member = None
            with contextlib.suppress(discord.HTTPException):
                target_member = ctx.guild.get_member(user.id) or await ctx.guild.fetch_member(user.id)

            kwargs["author"] = target_member or user

        alt_ctx = await copy_context_with(ctx, **kwargs)

        if alt_ctx.command is None:
            if alt_ctx.invoked_with is None:
                await ctx.send("This bot has been hard-configured to ignore this user.")
                return
            await ctx.send(f'Command "{alt_ctx.invoked_with}" is not found')
            return

        if ctx.invoked_with and ctx.invoked_with.endswith("!"):
            await alt_ctx.command.reinvoke(alt_ctx)
            return

        await alt_ctx.command.invoke(alt_ctx)
