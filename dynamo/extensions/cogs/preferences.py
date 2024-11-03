from typing import Annotated

import apsw
from discord.ext import commands

from dynamo import Cog, Context, Dynamo
from dynamo.utils.format import code_block


class Preferences(Cog, name="preferences"):
    """Server-specific settings and preferences"""

    def _get_prefixes(self, guild_id: int) -> list[str]:
        """Get prefixes for a guild from the database"""
        cursor = self.bot.conn.cursor()
        rows = cursor.execute("SELECT prefix FROM prefixes WHERE guild_id = ?", (guild_id,)).fetchall()
        # Always include default prefixes
        return [str(row[0]) for row in rows] if rows else ["d!", "d?"]

    @commands.hybrid_group(name="prefix", invoke_without_command=True)
    @commands.guild_only()
    async def prefix(self, ctx: Context) -> None:
        """View the current prefix(es) for this server"""
        if not ctx.guild:
            return

        prefixes = self._get_prefixes(ctx.guild.id)
        prefix_list = "\n".join(f"> {p}" for p in prefixes)
        await ctx.send(f"Current prefixes:\n{prefix_list}")

    @prefix.command(name="add")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def prefix_add(
        self,
        ctx: Context,
        prefix: Annotated[str, commands.clean_content],
    ) -> None:
        """Add a prefix for this server

        Parameters
        ----------
        prefix : str
            The prefix to add
        """
        if not ctx.guild:
            return

        if len(prefix) > 10:
            await ctx.send("Prefix must be 10 characters or less")
            return

        # Get custom prefixes only for length check
        cursor = ctx.bot.conn.cursor()
        custom_prefixes = cursor.execute("SELECT prefix FROM prefixes WHERE guild_id = ?", (ctx.guild.id,)).fetchall()

        if len(custom_prefixes) >= 5:
            await ctx.send("You can only have up to 5 custom prefixes")
            return

        # Check against all prefixes (including defaults)
        current_prefixes = self._get_prefixes(ctx.guild.id)
        if prefix in current_prefixes:
            await ctx.send("That prefix already exists!")
            return

        try:
            cursor.execute(
                "INSERT INTO prefixes (guild_id, prefix) VALUES (?, ?)",
                (ctx.guild.id, prefix),
            )
        except apsw.Error:
            await ctx.send("Failed to add prefix")
            return

        await ctx.send(f"Added prefix: {code_block(prefix)}")

    @prefix.command(name="remove")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def prefix_remove(
        self,
        ctx: Context,
        prefix: Annotated[str, commands.clean_content],
    ) -> None:
        """Remove a prefix from this server

        Parameters
        ----------
        prefix : str
            The prefix to remove
        """
        if not ctx.guild:
            return

        current_prefixes = self._get_prefixes(ctx.guild.id)

        # Don't allow removing default prefixes if they're being used as fallback
        if prefix in ["d!", "d?"] and current_prefixes == ["d!", "d?"]:
            await ctx.send("Cannot remove default prefixes!")
            return

        if prefix not in current_prefixes:
            await ctx.send("That prefix doesn't exist!")
            return

        cursor = ctx.bot.conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM prefixes WHERE guild_id = ? AND prefix = ?",
                (ctx.guild.id, prefix),
            )
        except apsw.Error:
            await ctx.send("Failed to remove prefix")
            return

        # If we removed the last custom prefix, remind about defaults
        remaining = self._get_prefixes(ctx.guild.id)
        if not remaining:  # If no custom prefixes remain
            await ctx.send(f"Removed prefix: {code_block(prefix)}\n" "Using default prefixes: `d!` and `d?`")
        else:
            await ctx.send(f"Removed prefix: {code_block(prefix)}")


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Preferences(bot))


async def teardown(bot: Dynamo) -> None:
    await bot.remove_cog(Preferences.__name__)
