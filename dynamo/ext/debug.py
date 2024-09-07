import importlib
import logging
import sys

import discord
from discord import app_commands
from discord.ext import commands

from dynamo.bot import Dynamo
from dynamo.utils.cache import cached_functions
from dynamo.utils.context import Status

log = logging.getLogger(__name__)


class Debug(commands.GroupCog, group_name="debug"):
    """Debug commands"""

    def __init__(self, bot: Dynamo) -> None:
        self.bot: Dynamo = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.hybrid_group(invoke_without_command=True)
    @app_commands.describe(guild_id="The ID of the guild to sync commands to", copy="Copy global commands to the guild")
    async def sync(self, ctx: commands.Context, guild_id: int | None, copy: bool = False) -> None:
        """Sync slash commands

        Parameters
        ----------
        guild_id: int | None
            The ID of the guild to sync commands to. If nothing is provided, the current guild will be used.
        copy: bool
            Whether to copy global commands to the specified guild.
        """
        guild: discord.Guild = discord.Object(id=guild_id, type=discord.Guild) if guild_id else ctx.guild

        if copy:
            self.bot.tree.copy_global_to(guild=guild)

        commands = await self.bot.tree.sync(guild=guild)
        await ctx.send(f"Successfully synced {len(commands)} commands")

    @sync.command(name="global")
    async def sync_global(self, ctx: commands.Context) -> None:
        """Sync global slash commands"""
        commands = await self.bot.tree.sync(guild=None)
        await ctx.send(f"Successfully synced {len(commands)} commands")

    @sync.command(name="clear")
    async def clear_commands(self, ctx: commands.Context, guild_id: int | None) -> None:
        """Clear all slash commands

        Parameters
        ----------
        guild_id: int | None
            The ID of the guild to clear commands from. If nothing is provided, the current guild will be used.
        """
        confirm = await ctx.prompt("Are you sure you want to clear all commands?")
        if not confirm:
            return

        guild: discord.Guild | None = discord.Object(id=guild_id, type=discord.Guild) if guild_id else None

        self.bot.tree.clear_commands(guild=guild)
        await ctx.send("Successfully cleared all commands")

    @commands.hybrid_command(aliases=("l",), hidden=True)
    @app_commands.describe(module="The name of the cog to load")
    async def load(self, ctx: commands.Context, *, module: str) -> None:
        """Load a cog

        Parameters
        ----------
        module: str
            The name of the cog to load.
        """
        try:
            await self.bot.load_extension(module)
        except commands.ExtensionError:
            log.exception("Failed to load %s", module)
        else:
            await ctx.send(Status.OK)

    @commands.hybrid_command(aliases=("ul",), hidden=True)
    @app_commands.describe(module="The name of the cog to unload")
    async def unload(self, ctx: commands.Context, *, module: str) -> None:
        """Unload a cog

        Parameters
        ----------
        module: str
            The name of the cog to unload.
        """
        try:
            await self.bot.unload_extension(module)
        except commands.ExtensionError:
            log.exception("Failed to unload %s", module)
        else:
            await ctx.send(Status.OK)

    @commands.hybrid_group(name="reload", aliases=("r",), hidden=True, invoke_without_command=True)
    async def _reload(self, ctx: commands.Context, *, module: str) -> None:
        """Reload a cog.

        Parameters
        ----------
        module: str
            The name of the cog to reload.
        """
        try:
            await self.bot.reload_extension(module)
        except commands.ExtensionError:
            log.exception("Failed to reload %s", module)
        else:
            await ctx.send(Status.OK)

    async def reload_or_load_extension(self, module: str) -> None:
        try:
            await self.bot.reload_extension(module)
        except commands.ExtensionNotLoaded:
            await self.bot.load_extension(module)

    @_reload.command(name="all", hidden=True)
    async def _reload_all(self, ctx: commands.Context) -> None:
        """Reload all cogs"""
        confirm = await ctx.prompt("Are you sure you want to reload all cogs?")
        if not confirm:
            return

        # Reload all pre-existing modules from the utils folder
        utils_modules: set[str] = {mod for mod in sys.modules if mod.startswith("dynamo.utils.")}
        utils_reloads = 0
        for module in utils_modules:
            try:
                importlib.reload(sys.modules[module])
            except (KeyError, ModuleNotFoundError):
                log.exception("Failed to reload %s", module)
            else:
                utils_reloads += 1
        log.info("Reloaded %d/%d utilities", utils_reloads, len(utils_modules))

        extensions = self.bot.extensions.copy()
        statuses: list[tuple[Status, str]] = []
        ext_reloads = 0
        for ext in extensions:
            try:
                await self.reload_or_load_extension(ext)
            except commands.ExtensionError:
                log.exception("Failed to reload extension %s", ext)
                statuses.append((Status.FAILURE, ext))
            else:
                statuses.append((Status.SUCCESS, ext))
                ext_reloads += 1

        log.info("Reloaded %d/%d extensions", ext_reloads, len(extensions))
        await ctx.send("\n".join(f"{status} `{ext}`" for status, ext in statuses))

    @commands.hybrid_group(name="cache")
    async def cache(self, ctx: commands.Context) -> None:
        """Peek into the cache"""
        await ctx.send(cached_functions() or "No cached functions")

    @commands.hybrid_command(name="quit", aliases=("exit", "shutdown", "q"))
    @commands.is_owner()
    async def shutdown(self, ctx: commands.Context) -> None:
        """Shutdown the bot"""
        await ctx.send("Shutting down...")
        log.info("Shutting down...")
        await self.bot.close()


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Debug(bot))
