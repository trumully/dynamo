import logging

from discord.ext import commands

from dynamo.bot import Dynamo
from dynamo.utils.helper import get_cog


class DynamoCog(commands.Cog):
    def __init__(self, bot: Dynamo) -> None:
        self.bot: Dynamo = bot
        self.log = logging.getLogger(get_cog(self.__class__.__name__))

    async def cog_load(self) -> None:
        self.log.debug("%s cog loaded", self.__class__.__name__)
