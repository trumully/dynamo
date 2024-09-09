import logging
from typing import Any, Mapping, ParamSpec, TypeVar

import discord
from discord.ext import commands

from dynamo.bot import Dynamo
from dynamo.utils.format import human_join

CogT = TypeVar("CogT", bound=commands.Cog)
T = TypeVar("T")
R = TypeVar("R")
P = ParamSpec("P")


log = logging.getLogger(__name__)


class HelpEmbed(discord.Embed):
    def __init__(self, color: discord.Color = discord.Color.dark_embed(), **kwargs: dict[str, Any]):
        super().__init__(**kwargs)
        text = (
            "Use help [command] or help [category] for more information"
            "\nRequired parameters: <required> | Optional parameters: [optional]"
        )
        self.set_footer(text=text)
        self.color = color


class DynamoHelp(commands.HelpCommand):
    def __init__(self):
        super().__init__(
            command_attrs={
                "help": "The help command for the bot",
                "aliases": ["commands", "h"],
            }
        )
        self.blacklisted = ["help_command"]

    async def send(self, **kwargs: dict[str, Any]) -> None:
        await self.get_destination().send(**kwargs)

    async def send_bot_help(self, mapping: Mapping[CogT, list[commands.Command[CogT, T, P]]]) -> None:
        ctx = self.context
        embed = HelpEmbed(title=f"{ctx.me.display_name} Help")
        embed.set_thumbnail(url=ctx.me.display_avatar)
        usable = 0

        for cog, command in mapping.items():
            if filtered_commands := await self.filter_commands(command):
                name = cog.qualified_name if cog else "No"
                if name in self.blacklisted:
                    continue
                amount_commands = len(filtered_commands)
                usable += amount_commands
                description = (cog.description or "No description") if cog else "Commands with no category"

                embed.add_field(name=f"{name} Category ({amount_commands})", value=description)

        embed.description = f"{usable} commands"

        await self.send(embed=embed)

    async def send_command_help(self, command: commands.Command[CogT, T, P]) -> None:
        signature = self.get_command_signature(command)

        embed = HelpEmbed(title=signature, description=f"```{command.help or "No help found..."}```")

        embed.add_field(name="Aliases", value=f"`{human_join(command.aliases) or 'None'}`")

        cog = command.cog
        if cog and cog.qualified_name not in self.blacklisted:
            embed.add_field(name="Category", value=cog.qualified_name)

        if command._buckets and (cooldown := command._buckets._cooldown):
            embed.add_field(
                name="Cooldown",
                value=f"{cooldown.rate} per {cooldown.per:.0f} seconds",
            )

        await self.send(embed=embed)

    async def send_help_embed(
        self,
        title: str,
        description: str,
        commands: list[commands.Command],
        aliases: list[str] | None = None,
        category: str | None = None,
    ) -> None:
        embed = HelpEmbed(title=title, description=description or "No help found...")

        if aliases:
            embed.add_field(name="Aliases", value=f"`{human_join(aliases) or 'None'}`")

        if category:
            embed.add_field(name="Category", value=category)

        if filtered_commands := await self.filter_commands(commands):
            sub_commands = [
                f"**{command.name}** - {command.help or 'No help found...'}" for command in filtered_commands
            ]
            subcommand_field_title = "Commands" if title.endswith("Category") else "Subcommands"
            if sub_commands:
                embed.add_field(name=subcommand_field_title, value=f">>> {'\n'.join(sub_commands)}", inline=False)

        await self.send(embed=embed)

    async def send_group_help(self, group: commands.Group) -> None:
        title = self.get_command_signature(group)
        await self.send_help_embed(title, group.help, group.commands, group.aliases, group.cog_name)

    async def send_cog_help(self, cog: commands.Cog) -> None:
        title = cog.qualified_name or "No"
        await self.send_help_embed(f"{title} Category", cog.description, cog.get_commands())


class Help(commands.Cog, name="help_command"):
    def __init__(self, bot: Dynamo) -> None:
        self.bot: Dynamo = bot
        self._original_help_command = bot.help_command
        help_command = DynamoHelp()
        help_command.cog = self
        bot.help_command = help_command

    def cog_unload(self) -> None:
        self.bot.help_command = self._original_help_command


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Help(bot))
