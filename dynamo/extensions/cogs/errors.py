from typing import Any, Callable, Coroutine, Mapping

import discord
from discord import Interaction, app_commands
from discord.ext import commands

from dynamo.bot import Dynamo
from dynamo.utils.base_cog import DynamoCog


class Errors(DynamoCog):
    """Handles errors for the bot."""

    command_error_messages: Mapping[type[commands.CommandError], str] = {
        commands.CommandNotFound: "Command not found: `{}`.",
        commands.MissingRequiredArgument: "Missing required argument: `{}`.",
        commands.BadArgument: "Bad argument.",
        commands.CommandOnCooldown: "You are on cooldown. Try again in `{:.2f}` seconds.",
        commands.TooManyArguments: "Too many arguments.",
        commands.MissingPermissions: "You are not allowed to use this command.",
        commands.BotMissingPermissions: "I am not allowed to use this command.",
        commands.NoPrivateMessage: "This command can only be used in a server.",
        commands.NotOwner: "You are not the owner of this bot.",
        commands.DisabledCommand: "This command is disabled.",
        commands.CheckFailure: "You do not have permission to use this command.",
    }

    app_command_error_messages: Mapping[type[app_commands.AppCommandError], str] = {
        app_commands.CommandNotFound: "Command not found: `{}`.",
        app_commands.CommandOnCooldown: "You are on cooldown. Try again in `{:.2f}` seconds.",
        app_commands.MissingPermissions: "You are not allowed to use this command.",
        app_commands.BotMissingPermissions: "I am not allowed to use this command.",
        app_commands.NoPrivateMessage: "This command can only be used in a server.",
        app_commands.CheckFailure: "You do not have permission to use this command.",
    }

    def __init__(self, bot: Dynamo) -> None:
        super().__init__(bot)

        self.old_tree_error: Callable[
            [Interaction[Dynamo], app_commands.AppCommandError], Coroutine[Any, Any, None]
        ] = self.bot.tree.on_error
        self.bot.tree.on_error = self.on_app_command_error

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
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """
        Event that triggers when a command fails.

        Parameters
        ----------
        ctx : commands.Context
            The context.
        error : commands.CommandError
            The error.
        """
        self.log.error("%s called by %s raised an exception: %s. (%s)", ctx.command, ctx.author, error, ctx.message)

        error_message = self.get_command_error_message(error)

        if isinstance(error, commands.CommandNotFound):
            error_message = error_message.format(ctx.invoked_with)

        elif isinstance(error, commands.MissingRequiredArgument):
            error_message = error_message.format(error.param.name)

        elif isinstance(error, commands.CommandOnCooldown):
            error_message = error_message.format(error.retry_after)

        await ctx.reply(error_message)

        if await self.bot.is_owner(ctx.author):
            command_name = ctx.command.name if ctx.command else "Unknown Command"
            await ctx.author.send(f"An error occurred while running the command `{command_name}`: {error}")

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
        if interaction.command is None:
            self.log.error("Command not found: %s.", interaction.data)
            command_name = interaction.data.get("name", "")
            await interaction.response.send_message(f"Command not found: `{command_name}`.", ephemeral=True)
            return

        self.log.error("%s called by %s raised an exception: %s.", interaction.command.name, interaction.user, error)

        error_message = self.get_app_command_error_message(error)

        if isinstance(error, app_commands.CommandNotFound):
            error_message = error_message.format(interaction.command.name)

        elif isinstance(error, app_commands.CommandOnCooldown):
            error_message = error_message.format(error.retry_after)

        try:
            await interaction.response.send_message(error_message, ephemeral=True)
        except (discord.HTTPException, discord.InteractionResponded, TypeError, ValueError):
            await interaction.followup.send(error_message, ephemeral=True)

        if await self.bot.is_owner(interaction.user):
            await interaction.user.send(
                f"An error occurred while running the command `{interaction.command.name}`: {error}"
            )


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Errors(bot))


async def teardown(bot: Dynamo) -> None:
    await bot.remove_cog(Errors.__name__)
