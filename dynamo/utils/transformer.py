import re
from typing import Any

import discord
from discord import AppCommandOptionType, app_commands

from dynamo.bot import Dynamo, Interaction
from dynamo.utils.datastructures import LRU

_guild_events_cache: LRU[int, list[discord.ScheduledEvent]] = LRU(128)

URL_REGEX = (
    r"https?://(?:(ptb|canary|www)\.)?discord\.com/events/(?P<guild_id>[0-9]{15,20})/(?P<event_id>[0-9]{15,20})$"
)
ID_REGEX = r"([0-9]{15,20})$"


class ScheduledEventTransformer(app_commands.Transformer[Dynamo]):
    async def transform(self, interaction: Interaction, value: Any, /) -> discord.ScheduledEvent:  # noqa: PLR0912 C901
        guild = interaction.guild
        assert guild is not None, "Not in a guild."

        result: discord.ScheduledEvent | None = None

        try:
            _events = _guild_events_cache.get(guild.id)
        except KeyError:
            _guild_events_cache[guild.id] = []
        else:
            result = next((e for e in _events if e.name == value or str(e.id) == value), None)
            if result is not None:
                return result

        if match := re.compile(ID_REGEX).match(value):
            event_id = int(match.group(1))
            result = guild.get_scheduled_event(event_id) if guild else None
            if not result:
                for g in interaction.client.guilds:
                    if result := g.get_scheduled_event(event_id):
                        break

        if match := re.match(URL_REGEX, value, flags=re.I):
            if guild := interaction.client.get_guild(int(match.group("guild_id"))):
                result = guild.get_scheduled_event(int(match.group("event_id")))
            else:
                result = None

        else:
            result = discord.utils.get(guild.scheduled_events, name=value) if guild else None
            if not result:
                for g in interaction.client.guilds:
                    if result := discord.utils.get(g.scheduled_events, name=value):
                        break

        if result is None:
            raise app_commands.TransformerError(value, self.type, self) from None

        if guild:
            _guild_events_cache[guild.id].append(result)

        return result

    @property
    def type(self) -> AppCommandOptionType:
        return AppCommandOptionType.string


class StringMemberTransformer(app_commands.Transformer[Dynamo]):
    async def transform(self, interaction: Interaction, value: Any, /) -> discord.User | discord.Member | str:  # noqa: ARG002
        if not isinstance(value, discord.Member | discord.User | str):
            raise app_commands.TransformerError(value, self.type, self)
        return value

    @property
    def type(self) -> AppCommandOptionType:
        return AppCommandOptionType.string
