from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from dynamo.bot import Dynamo


class Status(StrEnum):
    SUCCESS = "\N{WHITE HEAVY CHECK MARK}"
    FAILURE = "\N{CROSS MARK}"
    WARNING = "\N{WARNING SIGN}"
    OK = "\N{OK HAND SIGN}"


class ConfirmationView(discord.ui.View):
    def __init__(self, *, timeout: float, author_id: int, delete_after: bool) -> None:
        super().__init__(timeout=timeout)
        self.value: bool | None = None
        self.author_id: int = author_id
        self.delete_after: bool = delete_after
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user and interaction.user.id == self.author_id

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = True
        await interaction.response.defer()
        if self.delete_after:
            await interaction.delete_original_response()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.value = False
        await interaction.response.defer()
        if self.delete_after:
            await interaction.delete_original_response()
        self.stop()


class Context(commands.Context):
    channel: discord.VoiceChannel | discord.TextChannel | discord.Thread | discord.DMChannel
    prefix: str
    command: commands.Command[Any, ..., Any]
    bot: Dynamo

    def __init__(self, **kwargs: dict[str, Any]) -> None:
        super().__init__(**kwargs)

    async def prompt(
        self,
        message: str,
        *,
        timeout: float = 60.0,
        delete_after: bool = True,
        author_id: int | None = None,
    ) -> bool | None:
        author_id = author_id or self.author.id
        view = ConfirmationView(timeout=timeout, author_id=author_id, delete_after=delete_after)
        view.message = await self.send(message, view=view, ephemeral=delete_after)
        await view.wait()
        return view.value
