import re
from typing import Any

import discord
from discord import AppCommandOptionType, app_commands

from dynamo.bot import Dynamo, Interaction
from dynamo.utils.datastructures import LRU

_guild_events_cache: LRU[int, tuple[discord.ScheduledEvent, ...]] = LRU(128)

URL_REGEX = (
    r"https?://(?:(ptb|canary|www)\.)?discord\.com/events/(?P<guild_id>[0-9]{15,20})/(?P<event_id>[0-9]{15,20})$"
)
ID_REGEX = r"([0-9]{15,20})$"


def _check_by_cache(guild_id: int, value: Any, /) -> discord.ScheduledEvent | None:
    try:
        events = _guild_events_cache.get(guild_id)
    except KeyError:
        return None

    return next((e for e in events if e.name == value or str(e.id) == value), None)


def _check_by_id(interaction: Interaction, guild: discord.Guild, value: Any, /) -> discord.ScheduledEvent | None:
    if match := re.compile(ID_REGEX).match(value):
        event_id = int(match.group(1))
        if (result := guild.get_scheduled_event(event_id)) is not None:
            return result

        for g in interaction.client.guilds:
            if (result := g.get_scheduled_event(event_id)) is not None:
                return result

    return None


def _check_by_guilds(interaction: Interaction, value: Any, /) -> discord.ScheduledEvent | None:
    for g in interaction.client.guilds:
        if (result := discord.utils.get(g.scheduled_events, name=value)) is not None:
            return result
    return None


def _check_by_url(interaction: Interaction, value: Any, /) -> discord.ScheduledEvent | None:
    if match := re.match(URL_REGEX, value, flags=re.I):
        fetch_guild = interaction.client.get_guild(int(match.group("guild_id")))
        if fetch_guild is not None:
            return fetch_guild.get_scheduled_event(int(match.group("event_id")))
    return None


class ScheduledEventTransformer(app_commands.Transformer[Dynamo]):
    async def transform(self, interaction: Interaction, value: Any, /) -> discord.ScheduledEvent:
        guild = interaction.guild
        # Only want this transformer to be used in a guild context
        assert guild is not None, "Not in a guild."

        checks = (
            (_check_by_cache, (guild.id, value)),
            (_check_by_id, (interaction, guild, value)),
            (_check_by_url, (interaction, value)),
            (discord.utils.get, (guild.scheduled_events, value)),
            (_check_by_guilds, (interaction, value)),
        )

        for check_func, args in checks:
            if (result := check_func(*args)) is not None:
                _guild_events_cache[guild.id] = (*_guild_events_cache.get(guild.id, ()), result)
                return result

        raise app_commands.TransformerError(value, self.type, self) from None

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
