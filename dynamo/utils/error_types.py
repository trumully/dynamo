from collections.abc import Mapping

from discord import app_commands
from discord.ext import commands


class NotFoundWithHelp(commands.CommandError): ...


command_error_messages: Mapping[type[commands.CommandError], str] = {
    commands.CommandNotFound: "Command not found: **`{}`**{}",
    NotFoundWithHelp: "Command not found: **`{}`**{}",
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
    app_commands.CommandNotFound: "Command not found: **`{}`**{}",
    app_commands.CommandOnCooldown: "You are on cooldown. Try again in `{:.2f}` seconds.",
    app_commands.MissingPermissions: "You are not allowed to use this command.",
    app_commands.BotMissingPermissions: "I am not allowed to use this command.",
    app_commands.NoPrivateMessage: "This command can only be used in a server.",
    app_commands.CheckFailure: "You do not have permission to use this command.",
}
