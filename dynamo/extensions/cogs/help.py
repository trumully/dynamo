import logging
from dataclasses import dataclass
from typing import Any, Mapping, Never, TypedDict

import discord
from discord.ext import commands

from dynamo._typing import CogT, CommandT
from dynamo.core import Dynamo, DynamoCog
from dynamo.utils.error_types import NotFoundWithHelp
from dynamo.utils.format import code_block, human_join

log = logging.getLogger(__name__)


help_footer = (
    "Use help [command] or help [category] for more information\n"
    "Required parameters: <required> | Optional parameters: [optional]"
)


@dataclass
class EmbedField(TypedDict):
    name: str
    value: str


class HelpEmbed(discord.Embed):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.set_footer(text=help_footer)
        self.colour = discord.Color.dark_embed()


class DynamoHelp(commands.HelpCommand):
    def __init__(self) -> None:
        super().__init__(
            command_attrs={
                "help": "The help command for the bot",
                "aliases": ["commands", "h"],
            }
        )
        self.blacklisted = [Help.__name__]

    async def send(self, **kwargs: Any) -> None:
        await self.get_destination().send(**kwargs)

    async def send_bot_help(self, mapping: Mapping[CogT, list[CommandT]]) -> None:
        ctx = self.context
        embed = HelpEmbed(title=f"{ctx.me.display_name} Help")
        embed.set_thumbnail(url=ctx.me.display_avatar)

        for cog, command in mapping.items():
            filtered_commands = await self.filter_commands(command)
            if (cog and cog.qualified_name not in self.blacklisted) and filtered_commands:
                cog_field = await self.add_cog_commands_to_embed(cog, command)
                if cog_field is not None:
                    embed.add_field(**cog_field)

        await self.send(embed=embed)

    def command_not_found(self, string: str) -> Never:
        log.debug("Command not found: %s", string)
        raise NotFoundWithHelp(string)

    async def add_cog_commands_to_embed(self, cog: CogT, commands: list[CommandT]) -> EmbedField | None:
        name = cog.qualified_name if cog else "None"
        filtered_commands = await self.filter_commands(commands)
        if name in self.blacklisted or not filtered_commands:
            return None

        description = (cog.description or "No description") if cog else "Commands with no category"
        return EmbedField(name=f"{name} ({len(filtered_commands)})", value=code_block(description))

    async def send_command_help(self, command: CommandT) -> None:
        description = command.help or "No help found..."
        embed = HelpEmbed(title=command.qualified_name, description=code_block(description))

        embed.add_field(name="Aliases", value=f"`{human_join(command.aliases) or 'N/A'}`")

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
        commands: set[CommandT],
        aliases: list[str] | tuple[str] | None = None,
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
        await self.send_help_embed(title, code_block(group.help), group.commands, group.aliases, group.cog_name)

    async def send_cog_help(self, cog: commands.Cog) -> None:
        title = cog.qualified_name or "No"
        await self.send_help_embed(f"{title}", code_block(cog.description or "No description"), set(cog.get_commands()))


class Help(DynamoCog):
    def __init__(self, bot: Dynamo) -> None:
        super().__init__(bot)
        self._original_help_command, self.bot.help_command = self.bot.help_command, DynamoHelp()
        self.bot.help_command.cog = self

    async def cog_unload(self) -> None:
        self.bot.help_command = self._original_help_command
        self.log.debug("Restoring original help command")
        await super().cog_unload()


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Help(bot))


async def teardown(bot: Dynamo) -> None:
    await bot.remove_cog(Help.__name__)
