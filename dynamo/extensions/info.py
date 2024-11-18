from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NamedTuple

import discord
from discord import app_commands

from dynamo.types import BotExports
from dynamo.utils import aura, spotify
from dynamo.utils.cache import task_cache

if TYPE_CHECKING:
    from dynamo.bot import Interaction

log = logging.getLogger(__name__)


class UserAssets(NamedTuple):
    avatar: discord.Asset
    banner: discord.Asset | None


@task_cache(ttl=1800)
async def fetch_user_assets(user: discord.Member | discord.User) -> UserAssets:
    avatar = user.display_avatar.with_static_format("png")
    banner = user.banner.with_static_format("png") if user.banner else None

    return UserAssets(avatar, banner)


def embed_from_user(member: discord.Member | discord.User) -> discord.Embed:
    embed = discord.Embed()
    embed.set_footer(text=f"ID: {member.id}")
    avatar = member.display_avatar.with_static_format("png")
    embed.set_image(url=avatar)
    return embed


@app_commands.context_menu(name="Avatar")
async def user_avatar(itx: Interaction, user: discord.Member | discord.User) -> None:
    await itx.response.send_message(embed=embed_from_user(user), ephemeral=True)


@app_commands.context_menu(name="Aura")
async def get_aura(itx: Interaction, user: discord.Member | discord.User) -> None:
    await itx.response.defer()

    fetched_user = await itx.client.fetch_user(user.id)
    assets = await fetch_user_assets(fetched_user)

    avatar_bytes = await assets.avatar.read()
    banner_bytes = await assets.banner.read() if assets.banner else None

    score, description = await aura.get_aura(avatar_bytes, banner_bytes, itx.client.session)

    embed = discord.Embed(
        title=f"Aura of {user.name}",
        description=f"### {description}\nScore: **{score:.1f}** / 10",
        color=fetched_user.accent_color or fetched_user.color,
    )
    embed.set_thumbnail(url=user.display_avatar.with_static_format("png"))
    if assets.banner:
        embed.set_image(url=assets.banner.with_static_format("png"))

    await itx.followup.send(embed=embed)


@app_commands.command(name="spotify")
@app_commands.describe(user="The user to get the Spotify status of")
@app_commands.guild_only()
async def get_spotify(itx: Interaction, user: discord.Member | discord.User) -> None:
    """Get the Spotify status of a user."""
    assert itx.guild is not None

    member: discord.Member | None = itx.guild.get_member(user.id)
    if member is None:
        await itx.response.send_message("The user is not in the server", ephemeral=True)
        return

    spotify_activity = next((act for act in member.activities if isinstance(act, discord.Spotify)), None)
    if spotify_activity is None:
        await itx.response.send_message("The user is not listening to Spotify", ephemeral=True)
        return

    album_cover = await spotify.fetch_album_cover(spotify_activity.album_cover_url, itx.client.session)
    if album_cover is None:
        await itx.response.send_message("Something went wrong while fetching the album cover. Try again.")
        spotify.fetch_album_cover.cache_discard(spotify_activity.album_cover_url, itx.client.session)
        return

    buffer, extension = await spotify.draw(spotify_activity, album_cover)
    embed, file = spotify.make_embed(user, spotify_activity, buffer, "🎧", ext=extension)

    await itx.response.send_message(embed=embed, file=file)


exports = BotExports([user_avatar, get_aura, get_spotify])
