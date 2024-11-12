from __future__ import annotations

import re
from typing import Any

import discord
from discord import AppCommandOptionType, app_commands
from discord.ext import commands

from dynamo.bot import Interaction

ID_REGEX = re.compile(r"([0-9]{15,20})$")


class ScheduledEventTransformer(app_commands.Transformer):
    async def transform(self, interaction: Interaction, value: Any, /) -> discord.ScheduledEvent:
        guild = interaction.guild
        match = ID_REGEX.match(value)
        result = None

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
            raise commands.ScheduledEventNotFound(value)

        return result

    @property
    def type(self) -> AppCommandOptionType:
        return AppCommandOptionType.string
