import asyncio
import datetime
import logging
from collections.abc import Generator
from dataclasses import dataclass
from functools import partial
from io import BytesIO
from pathlib import Path

import aiohttp
import discord
from PIL import Image, ImageDraw, ImageFont

from dynamo.utils.cache import async_cache
from dynamo.utils.format import FONTS, human_join, is_cjk
from dynamo.utils.helper import ROOT, resolve_path_with_links, valid_url

log = logging.getLogger(__name__)

# Dark blue
BACKGROUND_COLOR: tuple[int, int, int] = (5, 5, 25)

# White
TEXT_COLOR: tuple[int, int, int] = (255, 255, 255)
PROGRESS_BAR_COLOR: tuple[int, int, int] = (255, 255, 255)

# Light gray
LENGTH_BAR_COLOR: tuple[int, int, int] = (64, 64, 64)


SPOTIFY_LOGO_PATH = resolve_path_with_links(Path(ROOT / "assets" / "images" / "spotify.png"))

WIDTH: int = 800
HEIGHT: int = 250
PADDING: int = 15
BORDER: int = 8

# Album cover
ALBUM_SIZE: int = HEIGHT - (BORDER * 2) + 1  # Fits exactly within the blue box

# Font settings
TITLE_FONT_SIZE: int = 28
ARTIST_FONT_SIZE: int = 22
PROGRESS_FONT_SIZE: int = 18

# Spotify logo
LOGO_SIZE: int = 48
LOGO_X: int = WIDTH - LOGO_SIZE - PADDING - BORDER
LOGO_Y: int = PADDING + BORDER

# Layout
CONTENT_START_X: int = ALBUM_SIZE + BORDER * 2
CONTENT_WIDTH: int = WIDTH - CONTENT_START_X - PADDING - BORDER
TITLE_START_Y: int = PADDING

# Progress bar
PROGRESS_BAR_START_X: int = CONTENT_START_X
PROGRESS_BAR_WIDTH: int = WIDTH - CONTENT_START_X - PADDING - BORDER - 70  # Account for Spotify logo
PROGRESS_BAR_HEIGHT: int = 6
PROGRESS_BAR_Y: int = HEIGHT - PADDING - BORDER - PROGRESS_BAR_HEIGHT - 30
PROGRESS_TEXT_Y: int = HEIGHT - PADDING - BORDER - 24

SLIDING_SPEED: int = 6  # pixels per frame
MAX_FRAMES: int = 480  # number of frames for sliding animation
FRAME_DURATION: int = 50  # duration of each frame in milliseconds


@dataclass(frozen=True)
class StaticDrawArgs:
    artists: list[str]
    artist_font: ImageFont.FreeTypeFont
    duration: datetime.timedelta | None
    end: datetime.datetime | None
    spotify_logo: Image.Image


@dataclass(frozen=True)
class DrawArgs:
    name: str
    artists: list[str]
    color: tuple[int, int, int]
    album: bytes
    duration: datetime.timedelta | None = None
    end: datetime.datetime | None = None


def make_embed(
    user: discord.Member | discord.User, activity: discord.Spotify, image: BytesIO, emoji: str, *, ext: str
) -> tuple[discord.Embed, discord.File]:
    """Make an embed for the currently playing Spotify track.

    Parameters
    ----------
    spotify_info : bytes
        The Spotify info as bytes
    album : bytes
        The album cover as bytes

    Returns
    -------
    tuple[discord.Embed, discord.File]
        The embed for the currently playing Spotify track and the file for the Spotify card
    """
    fname = f"spotify-card.{ext}"
    track = f"[{activity.title}](<{activity.track_url}>)"
    file = discord.File(image, filename=fname)
    embed = discord.Embed(
        title=f"{emoji} Now Playing",
        description=f"{user.mention} is listening to **{track}** by"
        f" **{human_join(activity.artists, conjunction="and")}**",
        color=activity.color,
    )
    embed.set_image(url=f"attachment://{fname}")
    return embed, file


async def draw(activity: discord.Spotify, album: bytes) -> tuple[BytesIO, str]:
    """Draw a Spotify card based on what the user is currently listening to. If the track's title is too long to fit
    on the card, the title will scroll instead."""
    name = activity.title
    artists = activity.artists
    color = activity.color.to_rgb()
    duration = activity.duration
    end = activity.end

    return await asyncio.to_thread(_draw, DrawArgs(name, artists, color, album, duration, end))


def get_font(text: str, size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get a font for the given text based on the text's language."""
    font_family = FONTS[is_cjk(text)]
    font_path = font_family.bold if bold else font_family.regular
    return ImageFont.truetype(font_path, size)


def track_duration(seconds: int) -> str:
    """Convert a track duration in seconds to a string"""
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{f"{hours}:" if hours else ""}{minutes:02d}:{seconds:02d}"


def get_progress(end: datetime.datetime, duration: datetime.timedelta) -> float:
    """Get the progress of the track as a percentage"""
    now = datetime.datetime.now(tz=datetime.UTC)
    return 1 - (end - now).total_seconds() / duration.total_seconds()


def create_base_image(color: tuple[int, int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    base = Image.new("RGBA", (WIDTH, HEIGHT), color)
    base_draw = ImageDraw.Draw(base)
    base_draw.rectangle((BORDER, BORDER, WIDTH - BORDER, HEIGHT - BORDER), fill=BACKGROUND_COLOR)
    return base, base_draw


def paste_album_cover(base: Image.Image, album: bytes) -> None:
    with Image.open(BytesIO(album)) as album_image:
        album_resized = album_image.resize((ALBUM_SIZE, ALBUM_SIZE))
        base.paste(album_resized, (BORDER, BORDER))


def _draw(args: DrawArgs) -> tuple[BytesIO, str]:
    base, base_draw = create_base_image(args.color)
    paste_album_cover(base, args.album)

    title_font = get_font(args.name, TITLE_FONT_SIZE, bold=True)
    artist_font = get_font(", ".join(args.artists), ARTIST_FONT_SIZE, bold=False)

    title_width = title_font.getbbox(args.name)[2]
    available_width = WIDTH - CONTENT_START_X - LOGO_SIZE - PADDING * 2 - BORDER

    spotify_logo = Image.open(SPOTIFY_LOGO_PATH).resize((LOGO_SIZE, LOGO_SIZE))
    draw_static = partial(
        draw_static_elements,
        args=StaticDrawArgs(args.artists, artist_font, args.duration, args.end, spotify_logo),
    )

    if title_width <= available_width:
        base_draw.text((CONTENT_START_X, TITLE_START_Y), args.name, fill=TEXT_COLOR, font=title_font)  # type: ignore
        draw_static(draw=base_draw, image=base)
        buffer = BytesIO()
        base.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer, "png"

    title_frames = draw_text_scroll(title_font, args.name, available_width)
    frames: list[Image.Image] = []
    for title_frame in title_frames:
        frame = base.copy()
        frame.paste(title_frame, (CONTENT_START_X, TITLE_START_Y), title_frame)
        draw_static(draw=ImageDraw.Draw(frame), image=frame)
        frames.append(frame)

    buffer = BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=FRAME_DURATION)
    buffer.seek(0)
    return buffer, "gif"


def draw_static_elements(image: Image.Image, draw: ImageDraw.ImageDraw, *, args: StaticDrawArgs) -> None:
    draw.text(  # type: ignore
        xy=(CONTENT_START_X, TITLE_START_Y + TITLE_FONT_SIZE + 5),
        text=str(", ".join(args.artists)),
        fill=TEXT_COLOR,
        font=args.artist_font,
    )

    if args.duration and args.end:
        progress = get_progress(args.end, args.duration)
        _draw_track_bar(draw, progress, args.duration)

    image.paste(args.spotify_logo, (LOGO_X, LOGO_Y), args.spotify_logo)


def _draw_track_bar(draw: ImageDraw.ImageDraw, progress: float, duration: datetime.timedelta) -> None:
    """Draw the duration and progress bar of a given track."""
    duration_width = PROGRESS_BAR_START_X + PROGRESS_BAR_WIDTH
    progress_width = max(
        PROGRESS_BAR_START_X, min(duration_width, PROGRESS_BAR_START_X + (PROGRESS_BAR_WIDTH * progress))
    )

    draw.rectangle(
        (PROGRESS_BAR_START_X, PROGRESS_BAR_Y, duration_width, PROGRESS_BAR_Y + PROGRESS_BAR_HEIGHT),
        fill=LENGTH_BAR_COLOR,
    )

    if progress_width > PROGRESS_BAR_START_X:
        draw.rectangle(
            (PROGRESS_BAR_START_X, PROGRESS_BAR_Y, progress_width, PROGRESS_BAR_Y + PROGRESS_BAR_HEIGHT),
            fill=PROGRESS_BAR_COLOR,
        )

    played_seconds = min(int(duration.total_seconds()), int(duration.total_seconds() * progress))
    progress_text = f"{track_duration(played_seconds)} / {track_duration(int(duration.total_seconds()))}"
    progress_font = get_font(progress_text, PROGRESS_FONT_SIZE)
    draw.text((PROGRESS_BAR_START_X, PROGRESS_TEXT_Y), progress_text, fill=TEXT_COLOR, font=progress_font)  # type: ignore


def draw_text_scroll(font: ImageFont.FreeTypeFont, text: str, width: int) -> Generator[Image.Image, None, None]:
    text_bbox = font.getbbox(text)
    text_width, text_height = int(text_bbox[2] - text_bbox[0]), int(text_bbox[3] - text_bbox[1])

    if text_width <= width:
        frame = Image.new("RGBA", (width, text_height))
        ImageDraw.Draw(frame).text((0, 0), text, fill=TEXT_COLOR, font=font)  # type: ignore
        yield frame
        return

    full_text = text + "   " + text
    full_text_width = int(font.getbbox(full_text)[2] - font.getbbox(full_text)[0])

    pause_frames, total_frames = 30, 30 + (full_text_width // SLIDING_SPEED)

    for i in range(total_frames):
        frame = Image.new("RGBA", (width, text_height))
        x_pos = 0 if i < pause_frames else -((i - pause_frames) * SLIDING_SPEED) % full_text_width
        ImageDraw.Draw(frame).text((x_pos, 0), full_text, fill=TEXT_COLOR, font=font)  # type: ignore
        yield frame


@async_cache
async def fetch_album_cover(url: str, session: aiohttp.ClientSession) -> bytes | None:
    """|coro|

    Fetch album cover from a URL.

    Parameters
    ----------
    url : str
        The URL of the album cover
    session : aiohttp.ClientSession
        The aiohttp session to use for the request

    Returns
    -------
    bytes | None
        The album cover as bytes, or None if the fetch failed
    """
    if not valid_url(url):
        log.exception("Invalid URL: %s", url)
        return None

    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.read()
            log.warning("Failed to fetch album cover: %s", response.status)
    except aiohttp.ClientResponseError:
        log.exception("Error fetching album cover: %s", url)

    return None
