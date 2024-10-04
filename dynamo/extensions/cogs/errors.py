from collections.abc import Callable
from functools import partial

import discord
from discord import app_commands
from discord.ext import commands
from rapidfuzz import fuzz

from dynamo._types import Coro, NotFoundWithHelp, app_command_error_messages, command_error_messages
from dynamo.core import Cog, Dynamo
from dynamo.core.bot import Interaction
from dynamo.utils.context import Context

type AppCommandErrorMethod = Callable[[Interaction, app_commands.AppCommandError], Coro[None]]


class Errors(Cog):
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
        """Get the error message for the given error.

        Parameters
        ----------
        error : commands.CommandError
            The error.

        Returns
        -------
        str
            The error message.
        """
        return self.command_error_messages.get(type(error), "An unknown error occurred.")

    def get_app_command_error_message(self, error: app_commands.AppCommandError) -> str:
        """
        Get the error message for the given error.

        Parameters
        ----------
        error : app_commands.AppCommandError
            The error.

        Returns
        -------
        str
            The error message.
        """
        return self.app_command_error_messages.get(type(error), "An unknown error occurred.")

    @commands.Cog.listener()
    async def on_command_error(self, ctx: Context, error: commands.CommandError) -> None:
        """
        Event that triggers when a command fails.

        Parameters
        ----------
        error : commands.CommandError
            The error.
        """
        self.log.exception("%s called by %s raised an exception: %s", ctx.command, ctx.author, ctx.message)

        error_message = self.get_command_error_message(error)

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
    async def on_app_command_error(self, interaction: Interaction, error: app_commands.AppCommandError) -> None:
        """
        Event that triggers when a command fails.

        Parameters
        ----------
        interaction : Interaction
            The interaction object.
        error : app_commands.AppCommandError
            The exception.
        """
        if (command := interaction.command) is None:
            name: str = "Unknown" if interaction.data is None else interaction.data.get("name", "Unknown")
            self.log.error("Command not found: %s.", name)
            is_similar = partial(fuzz.ratio, name)
            matches = [str(c) for c in self.bot.tree.get_commands() if is_similar(c.name) > 70]
            msg = f"Command not found: '{name}'"
            if matches:
                msg += f"\n\nDid you mean \N{RIGHT-POINTING MAGNIFYING GLASS}\n>>> {"\n".join(matches)}"

            await interaction.response.send_message(ephemeral=True, content=msg)
            return

        self.log.error("%s called by %s raised an exception: %s.", command.name, interaction.user, error)

        error_message = self.get_app_command_error_message(error)

        if isinstance(error, app_commands.CommandNotFound):
            error_message = error_message.format(command.name)

        elif isinstance(error, app_commands.CommandOnCooldown):
            error_message = error_message.format(error.retry_after)

        try:
            await interaction.response.send_message(error_message, ephemeral=True)
        except (discord.HTTPException, discord.InteractionResponded, TypeError, ValueError):
            await interaction.followup.send(error_message, ephemeral=True)


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Errors(bot))


async def teardown(bot: Dynamo) -> None:
    await bot.remove_cog(Errors.__name__)
