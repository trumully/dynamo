import operator
from collections.abc import Callable
from typing import Final, NamedTuple, cast

import discord
from discord import app_commands
from dynamo_utils.task_cache import task_cache

from dynamo.bot import Interaction
from dynamo.typedefs import BotExports


class PinnedMessage(NamedTuple):
    channel: int
    message: int
    author: int


_past_channels: Final[set[int]] = {
    696276827341324323,
    748654855262044181,
    793711844241309706,
    810621985418903555,
    841964091974615081,
    865779116351291442,
    883184413427519498,
    897811533973827594,
    918426907522007080,
    924612519702716417,
    931877946598240276,
    937627871332155392,
    980421204663992400,
    998073401421865063,
    1012232065879638047,
    1013679438447247481,
    1013727606522253372,
    1032115970279489567,
    1045963510959587348,
    1055765680089219163,
    1075649279907070022,
    1085689611734503435,
    1087702986794479716,
    1126354886540402771,
    1153246112350748722,
    1180466068884574248,
    1217978228438859776,
    1271041914300399629,
}
_GUILD: int = 696276827341324318


type ChannelFetchMethod = Callable[
    [int], discord.abc.GuildChannel | discord.Thread | discord.abc.PrivateChannel | None
]


@task_cache
async def fetch_channel_pins(
    fetch_method: ChannelFetchMethod, channel_id: int
) -> list[PinnedMessage]:
    try:
        channel: discord.TextChannel = cast(
            "discord.TextChannel", fetch_method(channel_id)
        )
        pins = await channel.pins()
    except (discord.HTTPException, discord.Forbidden):
        return []
    return [PinnedMessage(channel.id, pin.id, pin.author.id) for pin in pins]


pins_group = app_commands.Group(name="pins", description="Check pinned message stats.")


def sort_and_count_by_user(pins: list[PinnedMessage]) -> dict[int, int]:
    count_by_author: dict[int, int] = {}
    for message in pins:
        count_by_author.setdefault(message.author, 0)
        count_by_author[message.author] += 1
    return count_by_author


def get_as_embed(count_by_author: dict[int, int]) -> discord.Embed:
    return discord.Embed(
        title="Pins by user",
        description="\n".join(
            f"<@{user_id}>: {count}"
            for user_id, count in sorted(
                count_by_author.items(), key=operator.itemgetter(1), reverse=True
            )
        ),
    )


@pins_group.command(name="list")
@app_commands.describe(channel="The channel to get pins from. All if empty.")
@app_commands.guild_only()
async def get_pins(itx: Interaction, channel: discord.TextChannel | None = None) -> None:
    assert itx.guild is not None
    assert itx.guild.id == _GUILD

    await itx.response.defer()

    pins: list[PinnedMessage] = []
    if channel is not None:
        pins = await fetch_channel_pins(itx.client.get_channel, channel.id)
    else:
        # TODO
        ...

    await itx.followup.send(embed=get_as_embed(sort_and_count_by_user(pins)))


exports = BotExports(commands=[pins_group])
