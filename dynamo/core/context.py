from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

import aiohttp
import discord
from discord.ext import commands
from discord.ui import View

if TYPE_CHECKING:
    from dynamo.core.bot import Dynamo, Interaction  # noqa: F401


class ConfirmationView(View):
    """A view for confirming an action"""

    value: bool
    message: discord.Message | None

    def __init__(self, *, timeout: float, author_id: int, delete_after: bool) -> None:
        super().__init__(timeout=timeout)
        self.author_id: int = author_id
        self.delete_after: bool = delete_after
        self.value = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is from the author of the view"""
        return bool(interaction.user and interaction.user.id == self.author_id)

    async def _defer_and_stop(self, interaction: Interaction) -> None:
        """Defer the interaction and stop the view."""
        await interaction.response.defer()
        if self.delete_after and self.message:
            await interaction.delete_original_response()
        self.stop()

    async def on_timeout(self) -> None:
        """Disable the buttons and delete the message"""
        for i in self.children:
            item = cast(discord.ui.Button[ConfirmationView], i)
            item.disabled = True

        if self.message:
            await self.message.delete()

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm[V: View](self, interaction: Interaction, button: discord.ui.Button[V]) -> None:
        """Confirm the action"""
        self.value = True
        await self._defer_and_stop(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel[V: View](self, interaction: Interaction, button: discord.ui.Button[V]) -> None:
        """Cancel the action"""
        await self._defer_and_stop(interaction)


class Context(commands.Context["Dynamo"]):
    interaction: Interaction | None

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
        """
        |coro|

        Prompt the user to confirm an action
        """
        author_id = author_id or self.author.id
        view = ConfirmationView(timeout=timeout, author_id=author_id, delete_after=delete_after)
        view.message = await self.send(message, view=view, ephemeral=delete_after)
        await view.wait()
        return view.value
