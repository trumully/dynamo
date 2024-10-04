import importlib
import sys
from typing import Literal

import discord
from discord.ext import commands

from dynamo.core import Dynamo, DynamoCog
from dynamo.utils.checks import is_owner
from dynamo.utils.context import Context
from dynamo.utils.emoji import Emojis
from dynamo.utils.format import code_block
from dynamo.utils.helper import get_cog

type SyncSpec = Literal["~", "*", "^"]


class Dev(DynamoCog):
    """Dev-only commands"""

    @commands.hybrid_command(name="sync", aliases=("s",))
    @commands.guild_only()
    @is_owner()
    async def sync(self, ctx: Context, guilds: commands.Greedy[discord.Object], spec: SyncSpec | None = None) -> None:
        """Sync application commands globally or with guilds

        Parameters
        ----------
        guilds: commands.Greedy[discord.Object]
            The guilds to sync the commands to
        spec: SyncSpec | None, optional
            The sync specification, by default None

        See
        ---
        - https://about.abstractumbra.dev/discord.py/2023/01/29/sync-command-example.html
        """
        if not ctx.guild:
            return

        if not guilds:
            synced = await self._sync_commands(ctx.guild, spec)
            scope = "globally" if spec is None else "to the current guild"
            await ctx.send(f"Synced {len(synced)} commands {scope}.")
            return

        success = await self._sync_to_guilds(guilds)
        await ctx.send(f"Synced the tree to {success}/{len(guilds)} guilds.")

    async def _sync_commands(
        self, guild: discord.Guild, spec: SyncSpec | None
    ) -> list[discord.app_commands.AppCommand]:
        # This will sync all guild commands for the current context's guild.
        if spec == "~":
            return await self.bot.tree.sync(guild=guild)
        # This will copy all global commands to the current guild (within the CommandTree) and syncs.
        if spec == "*":
            self.bot.tree.copy_global_to(guild=guild)
            return await self.bot.tree.sync(guild=guild)
        # This command will remove all guild commands from the CommandTree and syncs,
        # which effectively removes all commands from the guild.
        if spec == "^":
            self.bot.tree.clear_commands(guild=guild)
            await self.bot.tree.sync(guild=guild)
            return []
        # This takes all global commands within the CommandTree and sends them to Discord
        return await self.bot.tree.sync()

    async def _sync_to_guilds(self, guilds: commands.Greedy[discord.Object]) -> int:
        success = 0
        for guild in guilds:
            try:
                await self.bot.tree.sync(guild=guild)
                success += 1
            except discord.HTTPException:
                self.log.exception("Failed to sync guild %s", guild.id)
        return success

    @commands.hybrid_command(name="load", aliases=("l",))
    @is_owner()
    async def load(self, ctx: Context, *, module: str) -> None:
        """Load a cog

        Parameters
        ----------
        module: str
            The name of the cog to load.
        """
        message = ctx.message
        cog = get_cog(module)
        try:
            await self.bot.load_extension(cog)
        except commands.ExtensionError as ex:
            await ctx.send(f"{ex.__class__.__name__}: {ex}")
            self.log.exception("Failed to load %s", cog)
        else:
            await message.add_reaction(ctx.Status.OK)

    @commands.hybrid_command(aliases=("ul",))
    @is_owner()
    async def unload(self, ctx: Context, *, module: str) -> None:
        """Unload a cog

        Parameters
        ----------
        module: str
            The name of the cog to unload.
        """
        message = ctx.message
        cog = get_cog(module)
        try:
            await self.bot.unload_extension(cog)
        except commands.ExtensionError as ex:
            await ctx.send(f"{ex.__class__.__name__}: {ex}")
            self.log.exception("Failed to unload %s", cog)
        else:
            await message.add_reaction(ctx.Status.OK)

    @commands.hybrid_group(name="reload", aliases=("r",), invoke_without_command=True)
    @is_owner()
    async def _reload(self, ctx: Context, *, module: str) -> None:
        """Reload a cog.

        Parameters
        ----------
        module: str
            The name of the cog to reload.
        """
        message: discord.Message | None = ctx.message
        cog = get_cog(module)
        try:
            await self.bot.reload_extension(cog)
        except commands.ExtensionError as ex:
            await ctx.send(f"{ex.__class__.__name__}: {ex}")
            self.log.exception("Failed to reload %s", cog)
        else:
            await message.add_reaction(ctx.Status.OK)

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
