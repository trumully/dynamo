from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

import aiohttp
import discord
from discord.ext import commands

from dynamo._typing import V

if TYPE_CHECKING:
    from dynamo.core.bot import Dynamo


class ConfirmationView(discord.ui.View):
    """A view for confirming an action"""

    value: bool
    message: discord.Message | None

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
        self.author_id: int = author_id
        self.delete_after: bool = delete_after
        self.value = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is from the author of the view"""
        return bool(interaction.user and interaction.user.id == self.author_id)

    async def _defer_and_stop(self, interaction: discord.Interaction[Dynamo]) -> None:
        """Defer the interaction and stop the view.

        Parameters
        ----------
        interaction : discord.Interaction
            The interaction to defer.
        """
        await interaction.response.defer()
        if self.delete_after and self.message:
            await interaction.delete_original_response()
        self.stop()

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True

        if self.message:
            await self.message.delete()

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction[Dynamo], button: discord.ui.Button[V]) -> None:
        """Confirm the action"""
        self.value = True
        await self._defer_and_stop(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction[Dynamo], button: discord.ui.Button[V]) -> None:
        """Cancel the action"""
        await self._defer_and_stop(interaction)


class Context(commands.Context["Dynamo"]):
    bot: Dynamo

    class Status(StrEnum):
        """Status emojis for the bot"""

        SUCCESS = "\N{WHITE HEAVY CHECK MARK}"
        FAILURE = "\N{CROSS MARK}"
        WARNING = "\N{WARNING SIGN}"
        OK = "\N{OK HAND SIGN}"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    @property
    def session(self) -> aiohttp.ClientSession:
        return self.bot.session

    async def prompt(
        self,
        message: str,
        *,
        timeout: float = 30.0,
        delete_after: bool = True,
        author_id: int | None = None,
    ) -> bool:
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
        bool
            Whether the user confirmed the action.
        """
        author_id = author_id or self.author.id
        view = ConfirmationView(timeout=timeout, author_id=author_id, delete_after=delete_after)
        view.message = await self.send(message, view=view, ephemeral=delete_after)
        await view.wait()
        return view.value
