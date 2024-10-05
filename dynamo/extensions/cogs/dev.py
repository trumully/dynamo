import contextlib
import importlib
import sys
from collections.abc import AsyncGenerator, Callable
from typing import Literal, cast

import discord
from discord.ext import commands

from dynamo._types import Coro
from dynamo.core import Cog, Dynamo
from dynamo.core.bot import Emojis
from dynamo.utils.checks import is_owner
from dynamo.utils.context import Context
from dynamo.utils.format import code_block
from dynamo.utils.helper import get_cog

type SyncSpec = Literal["~", "*", "^"]


class Dev(Cog):
    """Dev-only commands"""

    def __init__(self, bot: Dynamo) -> None:
        super().__init__(bot)

    async def _execute_extension_action(self, action: Callable[[str], Coro[None]], cog: str) -> bool:
        try:
            await action(get_cog(cog))
        except commands.ExtensionError:
            self.log.exception("Extension %s failed for cog %s", action.__name__, cog)
            return False
        return True

    @commands.hybrid_command(name="sync", aliases=("s",))
    @commands.guild_only()
    @is_owner()
    async def sync(self, ctx: Context, guilds: commands.Greedy[discord.Object], spec: SyncSpec | None = None) -> None:
        """Sync application commands globally or with guilds"""
        if not ctx.guild:
            return

        if not guilds:
            synced = await self._sync_commands(ctx.guild, spec)
            scope = "globally" if spec is None else "to the current guild"
            await ctx.send(f"Synced {len(synced)} commands {scope}.")
        else:
            success = await self._sync_to_guilds(guilds)
            await ctx.send(f"Synced the tree to {success}/{len(guilds)} guilds.")

    async def _sync_commands(
        self, guild: discord.Guild, spec: SyncSpec | None
    ) -> list[discord.app_commands.AppCommand]:
        if spec == "~":
            return await self.bot.tree.sync(guild=guild)
        if spec == "*":
            self.bot.tree.copy_global_to(guild=guild)
            return await self.bot.tree.sync(guild=guild)
        if spec == "^":
            self.bot.tree.clear_commands(guild=guild)
            await self.bot.tree.sync(guild=guild)
            return []
        return await self.bot.tree.sync()

    async def _sync_to_guilds(self, guilds: commands.Greedy[discord.Object]) -> int:
        async with contextlib.aclosing(cast(AsyncGenerator[discord.Guild], guilds)) as gen:
            results: list[bool] = [await self._sync_guild(guild) async for guild in gen]
        return sum(results)

    async def _sync_guild(self, guild: discord.Guild) -> bool:
        try:
            await self.bot.tree.sync(guild=guild)
        except discord.HTTPException:
            self.log.exception("Failed to sync guild %s", guild.id)
            return False
        return True

    @commands.hybrid_command(name="load", aliases=("l",))
    @is_owner()
    async def load(self, ctx: Context, *, module: str) -> None:
        """Load a cog"""
        success = await self._execute_extension_action(self.bot.load_extension, module)
        await ctx.message.add_reaction(ctx.Status.OK if success else ctx.Status.FAILURE)

    @commands.hybrid_command(aliases=("ul",))
    @is_owner()
    async def unload(self, ctx: Context, *, module: str) -> None:
        """Unload a cog"""
        success = await self._execute_extension_action(self.bot.unload_extension, module)
        await ctx.message.add_reaction(ctx.Status.OK if success else ctx.Status.FAILURE)

    @commands.hybrid_group(name="reload", aliases=("r",), invoke_without_command=True)
    @is_owner()
    async def _reload(self, ctx: Context, *, module: str) -> None:
        """Reload a cog."""
        success = await self._reload_extension(module)
        await ctx.message.add_reaction(ctx.Status.OK if success else ctx.Status.FAILURE)

    async def _reload_extension(self, module: str) -> bool:
        try:
            await self.bot.reload_extension(module)
        except commands.ExtensionNotLoaded:
            self.log.warning("Extension %s is not loaded. Attempting to load...", module)
            return await self._execute_extension_action(self.bot.load_extension, module)
        return True

    @_reload.command(name="all")
    @is_owner()
    async def _reload_all(self, ctx: Context) -> None:
        """Reload all cogs"""
        if not await ctx.prompt("Are you sure you want to reload all cogs?"):
            return

        utils_modules = self._reload_utils_modules()
        extensions_status = await self._reload_all_extensions()

        await ctx.send(self._format_reload_results(utils_modules, extensions_status))

    def _reload_utils_modules(self) -> tuple[int, int]:
        utils_modules = [mod for mod in sys.modules if mod.startswith("dynamo.utils.")]
        success = sum(self._reload_module(mod) for mod in utils_modules)
        return success, len(utils_modules)

    def _reload_module(self, module: str) -> bool:
        try:
            importlib.reload(sys.modules[module])
        except (KeyError, ModuleNotFoundError, NameError):
            self.log.exception("Failed to reload %s", module)
            return False
        return True

    async def _reload_all_extensions(self) -> list[tuple[Context.Status, str]]:
        extensions = list(self.bot.extensions)
        success = Context.Status.SUCCESS
        failure = Context.Status.FAILURE
        return [(success if await self._reload_extension(ext) else failure, ext) for ext in extensions]

    def _format_reload_results(
        self, utils_result: tuple[int, int], extensions_status: list[tuple[Context.Status, str]]
    ) -> str:
        utils_success, utils_total = utils_result
        extensions_success = sum(1 for status, _ in extensions_status if status == Context.Status.SUCCESS)
        extensions_total = len(extensions_status)

        result = [
            f"Reloaded {utils_success}/{utils_total} utilities",
            f"Reloaded {extensions_success}/{extensions_total} extensions",
            "\n".join(f"{status} `{ext}`" for status, ext in extensions_status),
        ]
        return "\n".join(result)

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

        all_emojis = [f"`{name}`\t{emoji}" for name, emoji in new_emojis.items()]
        added = [f"`{name}`\t{emoji}" for name, emoji in new_emojis.items() if name not in old_emojis]
        removed = [f"`{name}`\t{emoji}" for name, emoji in old_emojis.items() if name not in new_emojis]

        result = f"{"\n".join(all_emojis)}\n"

        if added:
            result += code_block("+ Added\n", "diff") + "\n".join(added)

        if removed:
            result += code_block("- Removed\n", "diff") + "\n".join(removed)

        await ctx.send(result.strip())


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Dev(bot))


async def teardown(bot: Dynamo) -> None:
    await bot.remove_cog(Dev.__name__)
