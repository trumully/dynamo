from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import Callable, Sequence
from itertools import chain
from typing import TYPE_CHECKING, Final, NamedTuple, cast

import discord
import pandas as pd
from discord import app_commands
from dynamo_utils.task_cache import task_cache

from dynamo.typedefs import BotExports, IsIterable
from dynamo.utils.check import in_personal_guild
from dynamo.utils.helper import b2048_pack, b2048_unpack

if TYPE_CHECKING:
    from dynamo.bot import Interaction

log = logging.getLogger(__name__)


class PinnedMessage(NamedTuple):
    channel: int
    message: int
    author: int


def sort_by_user(pins: IsIterable[PinnedMessage]) -> dict[int, list[str]]:
    sorted_by_user: dict[int, list[str]] = {}
    for message in pins:
        sorted_by_user.setdefault(message.author, []).append(
            f"https://discord.com/channels/{_GUILD}/{message.channel}/{message.message}"
        )
    return sorted_by_user


def sort_by_channel(pins: IsIterable[PinnedMessage]) -> dict[int, list[PinnedMessage]]:
    pins_by_channel: dict[int, list[PinnedMessage]] = {}
    for pin in pins:
        pins_by_channel.setdefault(pin.channel, []).append(pin)
    return pins_by_channel


_past_channels: Final[tuple[int, ...]] = (
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
)

_GUILD: Final[int] = 696276827341324318


type Channel = discord.abc.GuildChannel | discord.Thread | discord.abc.PrivateChannel
type ChannelFetchMethod = Callable[[int], Channel | None]


@task_cache
async def fetch_channel_pins(
    method: ChannelFetchMethod,
    channel_id: int,
) -> list[str]:
    try:
        channel: discord.TextChannel = cast("discord.TextChannel", method(channel_id))
        pins = await channel.pins()
    except (discord.HTTPException, discord.Forbidden):
        return []
    return [b2048_pack((pin.channel.id, pin.id, pin.author.id)) for pin in pins]


async def write_to_excel(data: Sequence[int], method: ChannelFetchMethod) -> bytes:
    out = io.BytesIO()

    log.info("Processing channels")
    tasks = (fetch_channel_pins(method, channel_id) for channel_id in data)
    pins = chain.from_iterable(await asyncio.gather(*tasks))
    unpacked_pins = (b2048_unpack(pin, PinnedMessage) for pin in pins)
    pins_by_channel = sort_by_channel(unpacked_pins)

    log.info("Writing to Excel")
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        for i, (channel_id, pins) in enumerate(pins_by_channel.items()):
            log.info("Processing results for channel #%d: %d", i + 1, channel_id)
            sorted_by_user = sort_by_user(pins)
            all_data = (
                (author, len(urls), "|||".join(urls))
                for author, urls in sorted_by_user.items()
            )
            pinned_dataframe = pd.DataFrame(
                all_data, columns=["Author", "Total Messages", "Links"]
            )
            sheet_name = f"Pinned Messages {i + 1}"
            pinned_dataframe.to_excel(writer, sheet_name=sheet_name, index=False)  # type: ignore[reportUnknownMemberType]

    out.seek(0)
    return out.read()


pins_group = app_commands.Group(name="pins", description="Check pinned message stats.")


@pins_group.command(name="generate")
@in_personal_guild()
async def generate_pins_excel(itx: Interaction) -> None:
    """Generate an Excel file with pinned message stats."""
    await itx.response.defer()

    excel_file = await write_to_excel(_past_channels, itx.client.get_channel)
    file_obj = io.BytesIO(excel_file)
    await itx.followup.send(file=discord.File(file_obj, filename="pins.xlsx"))


exports = BotExports(commands=[pins_group])
