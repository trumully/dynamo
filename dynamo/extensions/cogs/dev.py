import importlib
import importlib.abc
import importlib.metadata
import sys
from collections.abc import Callable
from typing import Literal, cast

import discord
from discord.ext import commands

from dynamo import Cog, Context, Dynamo
from dynamo.core.bot import Emojis
from dynamo.typedefs import Coro
from dynamo.utils.checks import is_owner
from dynamo.utils.format import code_block

type SyncSpec = Literal["~", "*", "^"]


class Dev(Cog, name="dev"):
    """Dev-only commands"""

    def __init__(self, bot: Dynamo) -> None:
        super().__init__(bot)

    async def _execute_extension_action(self, action: Callable[[str], Coro[None]], cog: str) -> bool:
        try:
            await action(self.bot.get_cog_name(cog))
        except commands.ExtensionError:
            self.log.exception("Action '%s' failed for cog %s", action.__name__, cog)
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
        results: list[bool] = [await self._sync_guild(cast(discord.Guild, guild)) for guild in guilds]
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
        """Load a cog

        Parameters
        ----------
        module : str
            The name of the module to load
        """
        success = await self._execute_extension_action(self.bot.load_extension, module)
        await ctx.message.add_reaction(ctx.Status.OK if success else ctx.Status.FAILURE)

    @commands.hybrid_command(aliases=("ul",))
    @is_owner()
    async def unload(self, ctx: Context, *, module: str) -> None:
        """Unload a cog

        Parameters
        ----------
        module : str
            The name of the module to unload
        """
        success = await self._execute_extension_action(self.bot.unload_extension, module)
        await ctx.message.add_reaction(ctx.Status.OK if success else ctx.Status.FAILURE)

    @commands.hybrid_group(name="reload", aliases=("r",), invoke_without_command=True)
    @is_owner()
    async def _reload(self, ctx: Context, *, module: str) -> None:
        """Reload a cog.

        Parameters
        ----------
        module : str
            The name of the module to reload
        """
        success = await self._reload_extension(module)
        await ctx.message.add_reaction(ctx.Status.OK if success else ctx.Status.FAILURE)

    async def _reload_extension(self, module: str) -> bool:
        result = await self._execute_extension_action(self.bot.reload_extension, module)
        if not result:
            return await self._execute_extension_action(self.bot.load_extension, module)
        return result

    def _reload_utils(self) -> list[tuple[Context.Status, str]]:
        modules_to_reload = frozenset(sys.modules[m] for m in sys.modules if m.startswith("dynamo.utils."))
        result: list[tuple[Context.Status, str]] = []
        for module in modules_to_reload:
            try:
                importlib.reload(module)
                result.append((Context.Status.SUCCESS, module.__name__))
            except Exception:
                self.log.exception("Failed to reload module %s. Never imported?", module.__name__)
                result.append((Context.Status.FAILURE, module.__name__))
        return result

    async def _reload_extensions(self) -> list[tuple[Context.Status, str]]:
        extensions = frozenset(self.bot.cogs)
        result: list[tuple[Context.Status, str]] = []
        for extension in extensions:
            try:
                await self._reload_extension(extension)
                result.append((Context.Status.SUCCESS, extension))
            except Exception:
                self.log.exception("Failed to reload extension %s", extension)
                result.append((Context.Status.FAILURE, extension))
        return result

    @_reload.command(name="all")
    @is_owner()
    async def reload_all(self, ctx: Context) -> None:
        """Reload extensions and utils"""
        if not await ctx.prompt("Are you sure you want to reload all extensions and utils?"):
            return

        extensions = await self._reload_extensions()
        utils = self._reload_utils()

        await ctx.send(self._pretty_results(extensions, utils) or "No extensions or utils to reload.")

    def _pretty_results(
        self, extensions: list[tuple[Context.Status, str]], utils: list[tuple[Context.Status, str]]
    ) -> str:
        result = ""
        if extensions:
            result += "### Extensions\n"
            result += "\n".join(f"> {status.value}\t`{self.bot.get_cog_name(name)}`" for status, name in extensions)
        if utils:
            result += f"{"\n" if extensions else ""}"
            result += "### Utils\n"
            result += "\n".join(f"> {status.value}\t`{name}`" for status, name in utils)
        return result

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
