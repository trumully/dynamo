import re
from typing import Any

import discord
from discord import AppCommandOptionType, app_commands

from dynamo.bot import Dynamo, Interaction
from dynamo.utils.cache import LRU

_guild_events_cache: LRU[int, list[discord.ScheduledEvent]] = LRU(128)

URL_REGEX = (
    r"https?://(?:(ptb|canary|www)\.)?discord\.com/events/(?P<guild_id>[0-9]{15,20})/(?P<event_id>[0-9]{15,20})$"
)
ID_REGEX = r"([0-9]{15,20})$"


class ScheduledEventTransformer(app_commands.Transformer[Dynamo]):
    async def transform(self, interaction: Interaction, value: Any, /) -> discord.ScheduledEvent:
        guild = interaction.guild

        if guild:
            _events = _guild_events_cache.get(guild.id, None)
            if _events is not None:
                result = next((e for e in _events if e.name == value or str(e.id) == value), None)
                if result is not None:
                    return result
            _guild_events_cache[guild.id] = []

        match value:
            case str() as v if match := re.compile(ID_REGEX).match(v):
                event_id = int(match.group(1))
                result = guild.get_scheduled_event(event_id) if guild else None
                if not result:
                    for g in interaction.client.guilds:
                        if result := g.get_scheduled_event(event_id):
                            break

            case str() as v if match := re.match(URL_REGEX, v, flags=re.I):
                if guild := interaction.client.get_guild(int(match.group("guild_id"))):
                    result = guild.get_scheduled_event(int(match.group("event_id")))
                else:
                    result = None

            case str() as name:
                result = discord.utils.get(guild.scheduled_events, name=name) if guild else None
                if not result:
                    for g in interaction.client.guilds:
                        if result := discord.utils.get(g.scheduled_events, name=name):
                            break

            case _:
                result = None

        if result is None:
            raise app_commands.TransformerError(value, self.type, self)

        if guild:
            _guild_events_cache[guild.id].append(result)

        return result

    @property
    def type(self) -> AppCommandOptionType:
        return AppCommandOptionType.string


class StringOrMemberTransformer(app_commands.Transformer[Dynamo]):
    async def transform(self, interaction: Interaction, value: Any, /) -> discord.User | discord.Member | str:
        if not isinstance(value, discord.Member | discord.User | str):
            raise app_commands.TransformerError(value, self.type, self)
        return value

    @property
    def type(self) -> AppCommandOptionType:
        return AppCommandOptionType.string
