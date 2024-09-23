from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord.ext import commands

from dynamo.utils.helper import get_cog

if TYPE_CHECKING:
    from dynamo.core import Dynamo


class DynamoCog(commands.Cog):
    __slots__ = ("bot", "log")

    def __init__(self, bot: Dynamo) -> None:
        self.bot: Dynamo = bot
        self.log = logging.getLogger(get_cog(self.__class__.__name__))

    async def cog_load(self) -> None:
        self.log.debug("%s cog loaded", self.__class__.__name__)
