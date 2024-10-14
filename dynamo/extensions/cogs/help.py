import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Never, TypedDict

import discord
from discord.ext import commands

from dynamo import Cog, Dynamo
from dynamo.typedefs import CogT, CommandT, NotFoundWithHelp
from dynamo.utils.format import code_block, human_join

log = logging.getLogger(__name__)


@dataclass
class EmbedField(TypedDict):
    name: str
    value: str


class HelpEmbed(discord.Embed):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.set_footer(text="Use help [command] or help [category] for more information")
        self.colour = discord.Color.dark_embed()


def wrap_with_braces(param: commands.Parameter, with_description: bool = True) -> str:
    name = f"<{param.name}>" if param.default is commands.Parameter.empty else f"[{param.name}]"
    return f"  {name}\n    {param.description or "No description provided."}" if with_description else name


class DynamoHelp(commands.HelpCommand):
    def __init__(self) -> None:
        super().__init__(
            command_attrs={
                "help": "The help command for the bot",
                "aliases": ["commands", "h"],
            }
        )
        self.blacklisted: set[str] = {"help"}

    async def send(self, **kwargs: Any) -> None:
        await self.get_destination().send(**kwargs)

    async def send_bot_help(self, mapping: Mapping[CogT | None, list[CommandT]]) -> None:
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
        raise NotFoundWithHelp(string) from None

    async def add_cog_commands_to_embed(self, cog: commands.Cog, commands: list[CommandT]) -> EmbedField | None:
        name = cog.qualified_name if cog else "None"
        filtered_commands = await self.filter_commands(commands)
        if name in self.blacklisted or not filtered_commands:
            return None

        description = (cog.description or "No description") if cog else "Commands with no category"
        return EmbedField(name=f"{name.title()} ({len(filtered_commands)})", value=code_block(description))

    async def send_command_help(self, command: commands.Command[CogT, ..., Any]) -> None:
        description = command.help or "No help found..."
        params = [wrap_with_braces(p) for p in command.params.values()]
        if params:
            description += f"\n\nParameters:\n{"\n".join(params)}"

        params_no_description = [wrap_with_braces(p, with_description=False) for p in command.params.values()]
        command_name = f"{command.qualified_name} {" ".join(params_no_description)}"
        colored_description = "\n".join(f"\u001b[1;33m{line}\u001b[0m" for line in description.split("\n"))
        full_description = (
            f"**`<required> | [optional]`**\n{code_block(colored_description, "ansi", line_numbers=True)}"
        )
        embed = HelpEmbed(title=command_name, description=full_description)

        embed.add_field(name="Aliases", value=f"`{human_join(command.aliases) or "N/A"}`")

        if (cog := command.cog) and cog.qualified_name not in self.blacklisted:
            embed.add_field(name="Category", value=cog.qualified_name.title())

        if (buckets := getattr(command, "_buckets", None)) and (cooldown := getattr(buckets, "_cooldown", None)):
            embed.add_field(name="Cooldown", value=f"{cooldown.rate} per {cooldown.per:.0f} seconds")

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
            embed.add_field(name="Aliases", value=f"`{human_join(aliases) or "None"}`")

        if category:
            embed.add_field(name="Category", value=category.title())

        sub_commands = [f"**{c.name}** - {c.help or "No help found..."}" for c in await self.filter_commands(commands)]
        if sub_commands:
            subcommand_field_title = "Commands" if title.endswith("Category") else "Subcommands"
            embed.add_field(name=subcommand_field_title, value=f">>> {"\n".join(sub_commands)}", inline=False)

        await self.send(embed=embed)

    async def send_group_help(self, group: commands.Group[CogT, ..., CommandT]) -> None:
        title = self.get_command_signature(group)
        await self.send_help_embed(
            title, code_block(group.help or "No help found..."), group.commands, group.aliases, group.cog_name
        )

    async def send_cog_help(self, cog: commands.Cog) -> None:
        title = cog.qualified_name or "No"
        await self.send_help_embed(
            f"{title.title()}", code_block(cog.description or "No description"), set(cog.get_commands())
        )


class Help(Cog, name="help"):
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
