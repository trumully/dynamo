from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord.ext import commands

from dynamo.typedefs import RawSubmittable

if TYPE_CHECKING:
    from dynamo import Dynamo


class Cog(commands.Cog):
    """Dynamo cog. Sets up logging and any existing raw submittables."""

    __slots__ = ("bot", "log")

    def __init__(
        self,
        bot: Dynamo,
        raw_modal_submits: dict[str, type[RawSubmittable]] | None = None,
        raw_button_submits: dict[str, type[RawSubmittable]] | None = None,
    ) -> None:
        self.bot: Dynamo = bot
        self.log = self._get_logger()
        if raw_modal_submits is not None:
            self.bot.raw_modal_submits.update(raw_modal_submits)
        if raw_button_submits is not None:
            self.bot.raw_button_submits.update(raw_button_submits)

    def _get_logger(self) -> logging.Logger:
        return logging.getLogger(self.bot.get_cog_name(self.__class__.__name__))

    async def cog_load(self) -> None:
        self.log.debug("%s cog loaded", self.__class__.__name__)
