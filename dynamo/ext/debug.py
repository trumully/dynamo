import importlib
import logging
import sys

import discord
from discord import app_commands
from discord.ext import commands

from dynamo.bot import Dynamo
from dynamo.utils.enums import Status

log = logging.getLogger(__name__)


class Debug(commands.GroupCog, group_name="debug"):
    """Debug commands"""

    def __init__(self, bot: Dynamo) -> None:
        self.bot: Dynamo = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.hybrid_group(invoke_without_command=True)
    @app_commands.describe(
        guild_id="The ID of the guild to sync commands to",
        copy="Copy global commands to the specified guild",
    )
    async def sync(self, ctx: commands.Context, guild_id: int | None, copy: bool = False) -> None:
        """Sync slash commands"""
        guild = discord.Object(id=guild_id) if guild_id else ctx.guild

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
        """Clear all slash commands"""
        confirm = await ctx.prompt("Are you sure you want to clear all commands?")
        if not confirm:
            return

        guild = discord.Object(id=guild_id) if guild_id is not None else None

        self.bot.tree.clear_commands(guild=guild)
        await ctx.send("Successfully cleared all commands")

    @commands.hybrid_command(aliases=["l"], hidden=True)
    @app_commands.describe(module="The name of the cog to load")
    async def load(self, ctx: commands.Context, *, module: str) -> None:
        """Load a cog"""
        try:
            await self.bot.load_extension(module)
        except commands.ExtensionError as exc:
            await ctx.send(f"{exc.__class__.__name__}: {exc}")
        else:
            await ctx.send(Status.OK)

    @commands.hybrid_command(aliases=["ul"], hidden=True)
    @app_commands.describe(module="The name of the cog to unload")
    async def unload(self, ctx: commands.Context, *, module: str) -> None:
        """Unload a cog"""
        try:
            await self.bot.unload_extension(module)
        except commands.ExtensionError as exc:
            await ctx.send(f"{exc.__class__.__name__}: {exc}")
        else:
            await ctx.send(Status.OK)

    @commands.hybrid_group(name="reload", aliases=["r"], hidden=True, invoke_without_command=True)
    async def _reload(self, ctx: commands.Context, *, module: str) -> None:
        """Reload a cog."""
        try:
            await self.bot.reload_extension(module)
        except commands.ExtensionError as e:
            await ctx.send(f"{e.__class__.__name__}: {e}")
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

        log.info("!!! STARTING FULL RELOAD !!!")

        # Reload all pre-existing modules from the utils folder
        utils_modules = [mod for mod in sys.modules if mod.startswith("dynamo.utils.")]
        successful_reloads = 0
        for module in utils_modules:
            try:
                importlib.reload(sys.modules[module])
            except (KeyError, ModuleNotFoundError):
                log.exception("Failed to reload %s", module)
            else:
                successful_reloads += 1
        log.info("Reloaded %d/%d utilities", successful_reloads, len(utils_modules))

        extensions = self.bot.extensions.copy()
        statuses: list[tuple[Status, str]] = []
        for ext in extensions:
            try:
                await self.reload_or_load_extension(ext)
            except commands.ExtensionError:
                statuses.append((Status.FAILURE, ext))
            else:
                statuses.append((Status.SUCCESS, ext))

        log.info("Reloaded %d/%d extensions", len(statuses), len(extensions))
        await ctx.reply("\n".join(f"{status} `{ext}`" for status, ext in statuses))

    @commands.hybrid_command(name="quit", aliases=["exit", "shutdown", "q"])
    @commands.is_owner()
    async def shutdown(self, ctx: commands.Context) -> None:
        """Shutdown the bot"""
        await ctx.send("Shutting down...")
        log.info("Shutting down...")
        await self.bot.close()


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Debug(bot))
