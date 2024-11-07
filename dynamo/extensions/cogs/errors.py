import sys
from functools import partial

import discord
from discord import app_commands
from discord.ext import commands
from rapidfuzz import fuzz

from dynamo import Cog, Context, Dynamo, Interaction
from dynamo.typedefs import CoroFunction, NotFoundWithHelp, app_command_error_messages, command_error_messages

type AppCommandErrorMethod = CoroFunction[[Interaction, app_commands.AppCommandError], None]


class Errors(Cog, name="errors"):
    """Handles errors for the bot."""

    def __init__(self, bot: Dynamo) -> None:
        super().__init__(bot)

        self.old_tree_error: AppCommandErrorMethod = self.bot.tree.on_error
        self.bot.tree.on_error = self.on_app_command_error
        self.command_error_messages = command_error_messages
        self.app_command_error_messages = app_command_error_messages

    async def cog_unload(self) -> None:
        """Restores the old tree error handler on unload."""
        self.bot.tree.on_error = self.old_tree_error
        await super().cog_unload()

    def get_command_error_message(self, error: commands.CommandError) -> str:
        """Get the error message for the given error."""
        return self.command_error_messages.get(type(error), "An unknown error occurred.")

    def get_app_command_error_message(self, error: app_commands.AppCommandError) -> str:
        """Get the error message for the given error."""
        return self.app_command_error_messages.get(type(error), "An unknown error occurred.")

    @commands.Cog.listener()
    async def on_command_error(self, ctx: Context, error: commands.CommandError) -> None:
        """Event that triggers when a command fails."""
        self.bot._last_error = sys.exc_info()[1]  # type: ignore

        error_message = self.get_command_error_message(error)
        self.log.exception("%s called by %s raised an exception: %s", ctx.command, ctx.author, ctx.message)

        if isinstance(error, commands.CommandNotFound | NotFoundWithHelp):
            invoked = ctx.invoked_with
            trigger: str = invoked if invoked and isinstance(error, commands.CommandNotFound) else error.args[0]

            is_similar = partial(fuzz.ratio, trigger)
            matches = [
                f"**{c.qualified_name}** - {c.short_doc or "No description provided"}"
                for c in self.bot.commands
                if is_similar(c.name) > 70
            ]
            matches_string = (
                f"\n\nDid you mean \N{RIGHT-POINTING MAGNIFYING GLASS}\n>>> {"\n".join(matches)}" if matches else ""
            )

            error_message = error_message.format(trigger, matches_string)

        elif isinstance(error, commands.MissingRequiredArgument):
            error_message = error_message.format(error.param.name)

        elif isinstance(error, commands.CommandOnCooldown):
            error_message = error_message.format(error.retry_after)

        await ctx.reply(error_message)

    @commands.Cog.listener()
    async def on_app_command_error(self, itx: Interaction, error: app_commands.AppCommandError) -> None:
        """Event that triggers when a command fails."""
        if (command := itx.command) is None:
            name: str = "Unknown" if itx.data is None else itx.data.get("name", "Unknown")
            self.log.error("Command not found: %s.", name)
            is_similar = partial(fuzz.ratio, name)
            matches = [str(c) for c in self.bot.tree.get_commands() if is_similar(c.name) > 70]
            msg = f"Command not found: '{name}'"
            if matches:
                msg += f"\n\nDid you mean \N{RIGHT-POINTING MAGNIFYING GLASS}\n>>> {"\n".join(matches)}"

            await itx.response.send_message(ephemeral=True, content=msg)
            return

        error_message = self.get_app_command_error_message(error)
        self.log.exception("%s called by %s raised an exception: %s", itx.command, itx.user, error)
        self.bot._last_error = sys.exc_info()[1]  # type: ignore

        if isinstance(error, app_commands.CommandNotFound):
            error_message = error_message.format(command.name)

        elif isinstance(error, app_commands.CommandOnCooldown):
            error_message = error_message.format(error.retry_after)

        try:
            await itx.response.send_message(error_message, ephemeral=True)
        except (discord.HTTPException, discord.InteractionResponded, TypeError, ValueError):
            await itx.followup.send(error_message, ephemeral=True)


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Errors(bot))


async def teardown(bot: Dynamo) -> None:
    await bot.remove_cog(Errors.__name__)
