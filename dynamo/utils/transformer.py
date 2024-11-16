import re
from typing import Any

import discord
from discord import AppCommandOptionType, app_commands

from dynamo.bot import Dynamo, Interaction
from dynamo.utils.cache import LRU

ID_REGEX = re.compile(r"([0-9]{15,20})$")

_guild_events_cache: LRU[int, list[discord.ScheduledEvent]] = LRU(128)


class ScheduledEventTransformer(app_commands.Transformer[Dynamo]):
    async def transform(self, interaction: Interaction, value: Any, /) -> discord.ScheduledEvent:
        guild = interaction.guild
        match = ID_REGEX.match(value)
        result = None

        # Don't query Discord if we don't have to
        if guild:
            if _guild_events_cache.get(guild.id, None) is None:
                _guild_events_cache[guild.id] = []
            else:
                events = _guild_events_cache[guild.id]
                result = next((e for e in events if e.name == value or str(e.id) == value), None)
                if result is not None:
                    return result

        if match:
            # ID match
            event_id = int(match.group(1))
            if guild:
                result = guild.get_scheduled_event(event_id)
            else:
                for guild in interaction.client.guilds:
                    result = guild.get_scheduled_event(event_id)
                    if result:
                        break
        else:
            pattern = (
                r"https?://(?:(ptb|canary|www)\.)?discord\.com/events/"
                r"(?P<guild_id>[0-9]{15,20})/"
                r"(?P<event_id>[0-9]{15,20})$"
            )
            match = re.match(pattern, value, flags=re.I)
            if match:
                # URL match
                guild = interaction.client.get_guild(int(match.group("guild_id")))

                if guild:
                    event_id = int(match.group("event_id"))
                    result = guild.get_scheduled_event(event_id)
            # lookup by name
            elif guild:
                result = discord.utils.get(guild.scheduled_events, name=value)
            else:
                for guild in interaction.client.guilds:
                    result = discord.utils.get(guild.scheduled_events, name=value)
                    if result:
                        break
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
        if isinstance(value, discord.Member | discord.User | str):
            return value
        raise app_commands.TransformerError(value, self.type, self)

    @property
    def type(self) -> AppCommandOptionType:
        return AppCommandOptionType.string
