import asyncio
import datetime
import logging
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import aiohttp
import discord
from PIL import Image, ImageDraw, ImageFont

from dynamo.utils.cache import async_cache
from dynamo.utils.format import FONTS, human_join, is_cjk
from dynamo.utils.helper import ROOT, resolve_path_with_links, valid_url

log = logging.getLogger(__name__)

# Color constants
COLORS = {
    "background": (5, 5, 25),
    "text": (255, 255, 255),
    "progress_bar": (255, 255, 255),
    "length_bar": (64, 64, 64),
}

# Layout constants
LAYOUT = {
    "width": 800,
    "height": 250,
    "padding": 15,
    "border": 8,
    "album_size": 250 - (8 * 2) + 1,
    "logo_size": 48,
}

# Font sizes
FONT_SIZES = {
    "title": 28,
    "artist": 22,
    "progress": 18,
}

SPOTIFY_LOGO_PATH = resolve_path_with_links(Path(ROOT / "assets" / "images" / "spotify.png"))

# Layout
CONTENT_START_X: int = LAYOUT["album_size"] + LAYOUT["border"] * 2
CONTENT_WIDTH: int = LAYOUT["width"] - CONTENT_START_X - LAYOUT["padding"] - LAYOUT["border"]
TITLE_START_Y: int = LAYOUT["padding"]

# Progress bar
PROGRESS_BAR_START_X: int = CONTENT_START_X
PROGRESS_BAR_WIDTH: int = LAYOUT["width"] - CONTENT_START_X - LAYOUT["padding"] - LAYOUT["border"] - 70
PROGRESS_BAR_HEIGHT: int = 6
PROGRESS_BAR_Y: int = LAYOUT["height"] - LAYOUT["padding"] - LAYOUT["border"] - PROGRESS_BAR_HEIGHT - 30
PROGRESS_TEXT_Y: int = LAYOUT["height"] - LAYOUT["padding"] - LAYOUT["border"] - 24

BASE_SLIDING_SPEED: int = 2
MAX_SLIDING_SPEED: int = 10
TOTAL_ANIMATION_TIME: int = 1000
MIN_FRAME_DURATION: int = 30
MAX_FRAME_DURATION: int = 100


@contextmanager
def open_image_bytes(image: bytes) -> Generator[Image.Image, None, None]:
    buffer = BytesIO(image)
    buffer.seek(0)
    try:
        yield Image.open(buffer)
    finally:
        buffer.close()


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
    """Make an embed for the currently playing Spotify track."""
    filename = f"spotify-card.{ext}"
    track = f"[{activity.title}](<{activity.track_url}>)"
    file = discord.File(image, filename=filename)
    description = f"{user.mention} is listening to **{track}** by **{human_join(activity.artists, conjunction="and")}**"
    embed = discord.Embed(title=f"{emoji} Now Playing", description=description, color=activity.color)
    embed.set_image(url=f"attachment://{filename}")
    return embed, file


async def draw(activity: discord.Spotify, album: bytes) -> tuple[BytesIO, str]:
    """Draw a Spotify card based on what the user is currently listening to."""
    args = DrawArgs(
        name=activity.title,
        artists=activity.artists,
        color=activity.color.to_rgb(),
        album=album,
        duration=activity.duration,
        end=activity.end,
    )
    return await asyncio.to_thread(_draw, args)


def _draw(args: DrawArgs) -> tuple[BytesIO, str]:
    base, base_draw = create_base_image(args.color)
    paste_album_cover(base, args.album)

    title_font = get_font(args.name, FONT_SIZES["title"], bold=True)
    artist_font = get_font(", ".join(args.artists), FONT_SIZES["artist"])

    available_width = calculate_available_width()

    if is_title_fits(args.name, title_font, available_width):
        return draw_static_image(base, base_draw, args, title_font, artist_font)
    return draw_animated_image(base, args, title_font, artist_font, available_width)


def calculate_available_width() -> int:
    return LAYOUT["width"] - CONTENT_START_X - LAYOUT["logo_size"] - LAYOUT["padding"] * 2 - LAYOUT["border"]


def is_title_fits(title: str, font: ImageFont.FreeTypeFont, available_width: int) -> bool:
    return font.getbbox(title)[2] <= available_width


def draw_static_image(
    base: Image.Image,
    base_draw: ImageDraw.ImageDraw,
    args: DrawArgs,
    title_font: ImageFont.FreeTypeFont,
    artist_font: ImageFont.FreeTypeFont,
) -> tuple[BytesIO, str]:
    base_draw.text((CONTENT_START_X, TITLE_START_Y), args.name, fill=COLORS["text"], font=title_font)  # type: ignore
    spotify_logo = Image.open(SPOTIFY_LOGO_PATH).resize((LAYOUT["logo_size"], LAYOUT["logo_size"]))
    static_args = StaticDrawArgs(args.artists, artist_font, args.duration, args.end, spotify_logo)
    draw_static_elements(base_draw, base, static_args)
    return save_image(base, "PNG")


def draw_animated_image(
    base: Image.Image,
    args: DrawArgs,
    title_font: ImageFont.FreeTypeFont,
    artist_font: ImageFont.FreeTypeFont,
    available_width: int,
) -> tuple[BytesIO, str]:
    text_frames = list(draw_text_scroll(title_font, args.name, available_width))
    spotify_logo = Image.open(SPOTIFY_LOGO_PATH).resize((LAYOUT["logo_size"], LAYOUT["logo_size"]))
    static_args = StaticDrawArgs(args.artists, artist_font, args.duration, args.end, spotify_logo)

    frames: list[Image.Image] = []
    for text_frame in text_frames:
        frame = base.copy()
        frame.paste(text_frame, (CONTENT_START_X, TITLE_START_Y), text_frame)
        draw_static_elements(ImageDraw.Draw(frame), frame, static_args)
        frames.append(frame)

    # Calculate frame duration based on the number of frames
    frame_duration = min(max(TOTAL_ANIMATION_TIME // len(frames), MIN_FRAME_DURATION), MAX_FRAME_DURATION)

    return save_image(frames[0], "GIF", save_all=True, append_images=frames[1:], duration=frame_duration, loop=0)


def save_image(image: Image.Image, image_format: str, **kwargs: Any) -> tuple[BytesIO, str]:
    buffer = BytesIO()
    image.save(buffer, format=image_format, **kwargs)
    buffer.seek(0)
    return buffer, image_format.lower()


def get_font(text: str, size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get a font for the given text based on the text's language."""
    font_family = FONTS[is_cjk(text)]
    font_path = font_family.bold if bold else font_family.regular
    return ImageFont.truetype(str(font_path), size)


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
    base = Image.new("RGBA", (LAYOUT["width"], LAYOUT["height"]), color)
    base_draw = ImageDraw.Draw(base)
    base_draw.rectangle(
        (LAYOUT["border"], LAYOUT["border"], LAYOUT["width"] - LAYOUT["border"], LAYOUT["height"] - LAYOUT["border"]),
        fill=COLORS["background"],
    )
    return base, base_draw


def paste_album_cover(base: Image.Image, album: bytes) -> None:
    with open_image_bytes(album) as album_image:
        album_resized = album_image.resize((LAYOUT["album_size"], LAYOUT["album_size"]))
        base.paste(album_resized, (LAYOUT["border"], LAYOUT["border"]))


def draw_static_elements(draw: ImageDraw.ImageDraw, image: Image.Image, args: StaticDrawArgs) -> None:
    draw.text(  # type: ignore
        xy=(CONTENT_START_X, TITLE_START_Y + FONT_SIZES["title"] + 5),
        text=", ".join(args.artists),
        fill=COLORS["text"],
        font=args.artist_font,
    )

    if args.duration and args.end:
        progress = get_progress(args.end, args.duration)
        draw_track_bar(draw, progress, args.duration)

    image.paste(
        args.spotify_logo,
        (
            LAYOUT["width"] - LAYOUT["logo_size"] - LAYOUT["padding"] - LAYOUT["border"],
            LAYOUT["padding"] + LAYOUT["border"],
        ),
        args.spotify_logo,
    )


def draw_track_bar(draw: ImageDraw.ImageDraw, progress: float, duration: datetime.timedelta) -> None:
    """Draw the duration and progress bar of a given track."""
    duration_width = PROGRESS_BAR_START_X + PROGRESS_BAR_WIDTH
    progress_width = max(
        PROGRESS_BAR_START_X, min(duration_width, PROGRESS_BAR_START_X + (PROGRESS_BAR_WIDTH * progress))
    )

    draw.rectangle(
        (PROGRESS_BAR_START_X, PROGRESS_BAR_Y, duration_width, PROGRESS_BAR_Y + PROGRESS_BAR_HEIGHT),
        fill=COLORS["length_bar"],
    )

    if progress_width > PROGRESS_BAR_START_X:
        draw.rectangle(
            (PROGRESS_BAR_START_X, PROGRESS_BAR_Y, progress_width, PROGRESS_BAR_Y + PROGRESS_BAR_HEIGHT),
            fill=COLORS["progress_bar"],
        )

    played_seconds = min(int(duration.total_seconds()), int(duration.total_seconds() * progress))
    progress_text = f"{track_duration(played_seconds)} / {track_duration(int(duration.total_seconds()))}"
    progress_font = get_font(progress_text, FONT_SIZES["progress"])
    draw.text((PROGRESS_BAR_START_X, PROGRESS_TEXT_Y), progress_text, fill=COLORS["text"], font=progress_font)  # type: ignore


def create_animated_frames(
    base: Image.Image,
    args: DrawArgs,
    title_font: ImageFont.FreeTypeFont,
    artist_font: ImageFont.FreeTypeFont,
    available_width: int,
) -> Generator[Image.Image, None, None]:
    text_frames = list(draw_text_scroll(title_font, args.name, available_width))
    spotify_logo = Image.open(SPOTIFY_LOGO_PATH).resize((LAYOUT["logo_size"], LAYOUT["logo_size"]))
    static_args = StaticDrawArgs(args.artists, artist_font, args.duration, args.end, spotify_logo)

    for text_frame in text_frames:
        frame = base.copy()
        frame.paste(text_frame, (CONTENT_START_X, TITLE_START_Y), text_frame)
        draw_static_elements(ImageDraw.Draw(frame), frame, static_args)
        yield frame


def draw_text_scroll(font: ImageFont.FreeTypeFont, text: str, width: int) -> Generator[Image.Image, None, None]:
    text_width, text_height = (int(x) for x in font.getbbox(text)[2:4])

    if text_width <= width:
        yield create_text_frame(text, width, text_height, font)
        return

    # Add padding to ensure smooth transition
    padded_text = text + "   " + text
    full_width = int(font.getbbox(padded_text)[2])

    # Calculate the number of frames based on TOTAL_ANIMATION_TIME and MIN_FRAME_DURATION
    max_frames = TOTAL_ANIMATION_TIME // MIN_FRAME_DURATION

    # Calculate the sliding speed based on text length
    sliding_speed = min(MAX_SLIDING_SPEED, max(BASE_SLIDING_SPEED, full_width // max_frames))

    # Calculate the number of frames needed for one complete cycle
    num_frames = min(max_frames, full_width // sliding_speed)

    for i in range(num_frames):
        x_pos = -i * sliding_speed % full_width
        yield create_text_frame(padded_text, width, text_height, font, x_pos)


def create_text_frame(text: str, width: int, height: int, font: ImageFont.FreeTypeFont, x_pos: int = 0) -> Image.Image:
    frame = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(frame)
    draw.text((x_pos, 0), text, fill=COLORS["text"], font=font)  # type: ignore
    draw.text((x_pos + font.getbbox(text)[2], 0), text, fill=COLORS["text"], font=font)  # type: ignore
    return frame


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
