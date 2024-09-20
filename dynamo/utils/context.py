from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

import aiohttp
import discord
from discord.ext import commands

if TYPE_CHECKING:
    from dynamo.bot import Dynamo


class Status(StrEnum):
    """Status emojis for the bot"""

    SUCCESS = "\N{WHITE HEAVY CHECK MARK}"
    FAILURE = "\N{CROSS MARK}"
    WARNING = "\N{WARNING SIGN}"
    OK = "\N{OK HAND SIGN}"


class ConfirmationView(discord.ui.View):
    """A view for confirming an action"""

    def __init__(self, *, timeout: float, author_id: int, delete_after: bool) -> None:
        """
        Parameters
        ----------
        timeout: float
            The timeout for the view.
        author_id: int
            The ID of the author of the view.
        delete_after: bool
            Whether to delete the message after the view times out.
        """
        super().__init__(timeout=timeout)
        self.value: bool | None = None
        self.author_id: int = author_id
        self.delete_after: bool = delete_after
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is from the author of the view"""
        return bool(interaction.user and interaction.user.id == self.author_id)

    async def _defer_and_stop(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        if self.delete_after:
            await interaction.delete_original_response()
        self.stop()

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Confirm the action"""
        self.value = True
        await self._defer_and_stop(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Cancel the action"""
        self.value = False
        await self._defer_and_stop(interaction)


class Context(commands.Context):
    channel: discord.VoiceChannel | discord.TextChannel | discord.Thread | discord.DMChannel
    prefix: str
    command: commands.Command[Any, ..., Any]
    bot: Dynamo

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    @property
    def session(self) -> aiohttp.ClientSession:
        return self.bot.session

    async def prompt(
        self,
        message: str,
        *,
        timeout: float = 60.0,
        delete_after: bool = True,
        author_id: int | None = None,
    ) -> bool | None:
        """Prompt the user to confirm an action

        Parameters
        ----------
        message: str
            The message to send to the user.
        timeout: float
            The timeout for the view.
        author_id: int | None
            The ID of the author of the view. If not provided, the author of the context is used.
        delete_after: bool
            Whether to delete the message after the view times out.

        Returns
        -------
        bool | None
            Whether the user confirmed the action.
        """
        author_id = author_id or self.author.id
        view = ConfirmationView(timeout=timeout, author_id=author_id, delete_after=delete_after)
        view.message = await self.send(message, view=view, ephemeral=delete_after)
        await view.wait()
        return view.value
