import importlib
import sys

import discord
from discord.ext import commands

from dynamo.core import Dynamo, DynamoCog
from dynamo.utils.checks import is_owner
from dynamo.utils.context import Context
from dynamo.utils.converter import GuildConverter
from dynamo.utils.emoji import Emojis
from dynamo.utils.helper import get_cog


class Dev(DynamoCog):
    """Dev-only commands"""

    def __init__(self, bot: Dynamo) -> None:
        super().__init__(bot)

    @commands.hybrid_group(invoke_without_command=True, name="sync", aliases=("s",))
    @is_owner()
    async def sync(
        self,
        ctx: Context,
        guild: discord.Guild = commands.param(converter=GuildConverter, default=None, displayed_name="guild_id"),
        copy: bool = False,
    ) -> None:
        """Sync slash commands

        Parameters
        ----------
        guild_id: int | None
            The ID of the guild to sync commands to. Current guild by default.
        copy: bool
            Copy global commands to the specified guild. (Default: False)
        """
        if copy:
            self.bot.tree.copy_global_to(guild=guild)

        commands = await self.bot.tree.sync(guild=guild)
        await ctx.send(f"Successfully synced {len(commands)} commands")

    @sync.command(name="global", aliases=("g",))
    @is_owner()
    async def sync_global(self, ctx: Context) -> None:
        """Sync global slash commands"""
        commands = await self.bot.tree.sync(guild=None)
        await ctx.send(f"Successfully synced {len(commands)} commands")

    @sync.command(name="clear", aliases=("c",))
    @is_owner()
    async def clear_commands(
        self,
        ctx: Context,
        guild: discord.Guild = commands.param(converter=GuildConverter, default=None, displayed_name="guild_id"),
    ) -> None:
        """Clear all slash commands

        Parameters
        ----------
        guild_id: int | None
            The ID of the guild to clear commands from. Current guild by default.
        """
        if not await ctx.prompt("Are you sure you want to clear all commands?"):
            return

        self.bot.tree.clear_commands(guild=guild)
        await ctx.send("Successfully cleared all commands")

    @commands.hybrid_command(name="load", aliases=("l",))
    @is_owner()
    async def load(self, ctx: Context, *, module: str) -> None:
        """Load a cog

        Parameters
        ----------
        module: str
            The name of the cog to load.
        """
        m = get_cog(module)
        try:
            await self.bot.load_extension(m)
        except commands.ExtensionError as ex:
            await ctx.send(f"{ex.__class__.__name__}: {ex}")
            self.log.exception("Failed to load %s", m)
        else:
            await ctx.send(ctx.Status.OK)

    @commands.hybrid_command(aliases=("ul",))
    @is_owner()
    async def unload(self, ctx: Context, *, module: str) -> None:
        """Unload a cog

        Parameters
        ----------
        module: str
            The name of the cog to unload.
        """
        m = get_cog(module)
        try:
            await self.bot.unload_extension(m)
        except commands.ExtensionError as ex:
            await ctx.send(f"{ex.__class__.__name__}: {ex}")
            self.log.exception("Failed to unload %s", m)
        else:
            await ctx.send(ctx.Status.OK)

    @commands.hybrid_group(name="reload", aliases=("r",), invoke_without_command=True)
    @is_owner()
    async def _reload(self, ctx: Context, *, module: str) -> None:
        """Reload a cog.

        Parameters
        ----------
        module: str
            The name of the cog to reload.
        """
        m = get_cog(module)

        try:
            await self.bot.reload_extension(m)
        except commands.ExtensionError as ex:
            await ctx.send(f"{ex.__class__.__name__}: {ex}")
            self.log.exception("Failed to reload %s", m)
        else:
            await ctx.send(ctx.Status.OK)

    async def reload_or_load_extension(self, module: str) -> None:
        try:
            await self.bot.reload_extension(module)
        except commands.ExtensionNotLoaded:
            self.log.exception("%s is not loaded. Attempting to load...", module)
            try:
                await self.bot.load_extension(module)
            except commands.ExtensionError:
                self.log.exception("Failed to load %s", module)

    @_reload.command(name="all")
    @is_owner()
    async def _reload_all(self, ctx: Context) -> None:
        """Reload all cogs"""
        if not await ctx.prompt("Are you sure you want to reload all cogs?"):
            return

        # Reload all pre-existing modules from the utils folder
        utils_modules: frozenset[str] = frozenset(mod for mod in sys.modules if mod.startswith("dynamo.utils."))
        fail = 0
        for module in utils_modules:
            try:
                importlib.reload(sys.modules[module])
            except (KeyError, ModuleNotFoundError):
                fail += 1
                self.log.exception("Failed to reload %s", module)
        self.log.debug("Reloaded %d/%d utilities", len(utils_modules) - fail, len(utils_modules))

        extensions = frozenset(self.bot.extensions)
        statuses: set[tuple[ctx.Status, str]] = set()
        for ext in extensions:
            try:
                await self.reload_or_load_extension(ext)
            except commands.ExtensionError:
                self.log.exception("Failed to reload extension %s", ext)
                statuses.add((ctx.Status.FAILURE, ext))
            else:
                statuses.add((ctx.Status.SUCCESS, ext))

        success_count = sum(1 for status, _ in statuses if status == ctx.Status.SUCCESS)
        self.log.debug("Reloaded %d/%d extensions", success_count, len(extensions))
        await ctx.send("\n".join(f"{status} `{ext}`" for status, ext in statuses))

    @commands.hybrid_command(name="quit", aliases=("exit", "shutdown", "q"))
    @is_owner()
    async def shutdown(self, ctx: Context) -> None:
        """Shutdown the bot"""
        await ctx.send("Shutting down...")
        await self.bot.close()

    @commands.hybrid_command(name="emoji")
    @is_owner()
    async def emoji(self, ctx: Context) -> None:
        """Refresh the bot's emoji"""
        old_emojis = self.bot.app_emojis
        self.bot.app_emojis = new_emojis = Emojis(await self.bot.fetch_application_emojis())

        # All emojis
        all_emojis = [f"`{name}`\t{emoji}" for name, emoji in new_emojis.items()]

        # Added emojis
        added = [f"`{name}`\t{emoji}" for name, emoji in new_emojis.items() if name not in old_emojis]

        # Removed emojis
        removed = [f"`{name}`\t{emoji}" for name, emoji in old_emojis.items() if name not in new_emojis]

        result = f"{'\n'.join(all_emojis)}\n"

        if added:
            result += "```diff\n+ Added\n```\n"
            result += "\n".join(added) + "\n"

        if removed:
            result += "```diff\n- Removed\n```\n"
            result += "\n".join(removed)

        await ctx.send(result.strip())


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Dev(bot))


async def teardown(bot: Dynamo) -> None:
    await bot.remove_cog(Dev.__name__)
