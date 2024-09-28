import asyncio
import datetime
import logging
from collections.abc import Generator
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import aiohttp
import discord
from PIL import Image, ImageDraw, ImageFont

from dynamo.utils.cache import async_cache
from dynamo.utils.format import FONTS, is_cjk
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


async def draw(activity: discord.Spotify, album: bytes) -> tuple[BytesIO, str]:
    """Draw a Spotify card based on what the user is currently listening to. If the track's title is too long to fit
    on the card, the title will scroll instead.

    Parameters
    ----------
    name : str
        The name of the track
    artists : list[str]
        The artists of the track
    color : tuple[int, int, int]
        The background color of the card
    album : BytesIO
        The album cover of the track
    duration : datetime.timedelta | None, optional
        The duration of the track, by default None
    end : datetime.datetime | None, optional
        The end time of the track, by default None

    Returns
    -------
    tuple[BytesIO, str]
        The Spotify card buffer and the output format

    See
    ---
    :func:`fetch_album_cover`
    :func:`_draw`
    :func:`_draw_static_elements`
    :func:`_draw_track_bar`
    :func:`_draw_text_scroll`
    """
    name = activity.title
    artists = activity.artists
    color = activity.color.to_rgb()
    duration = activity.duration
    end = activity.end

    return await asyncio.to_thread(_draw, DrawArgs(name, artists, color, album, duration, end))


def get_font(text: str, bold: bool = False, size: int = 22) -> ImageFont.FreeTypeFont:
    """Get a font for the given text based on the text's language.

    Parameters
    ----------
    text : str
        The text to get the font for
    bold : bool, optional
        Whether the font should be bold, by default False
    size : int, optional
        The size of the font, by default 22

    Returns
    -------
    ImageFont.FreeTypeFont
        The font for the given text

    See
    ---
    :func:`dynamo.utils.format.is_cjk`
    :const:`dynamo.utils.format.FONTS`
    """
    font_family = FONTS[is_cjk(text)]
    font_path = font_family.bold if bold else font_family.regular
    return ImageFont.truetype(font_path, size)


def track_duration(seconds: int) -> str:
    """Convert a track duration in seconds to a string

    Parameters
    ----------
    seconds : int
        The duration of the track in seconds

    Returns
    -------
    str
        The duration of the track in (hours):minutes:seconds
    """
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def get_progress(end: datetime.datetime, duration: datetime.timedelta) -> float:
    """Get the progress of the track as a percentage

    Parameters
    ----------
    end : datetime.datetime
        The end time of the track
    duration : datetime.timedelta
        The duration of the track

    Returns
    -------
    float
        The progress of the track as a percentage
    """
    now = datetime.datetime.now(tz=datetime.UTC)
    return 1 - (end - now).total_seconds() / duration.total_seconds()


@dataclass(frozen=True)
class DrawArgs:
    name: str
    artists: list[str]
    color: tuple[int, int, int]
    album: bytes
    duration: datetime.timedelta | None = None
    end: datetime.datetime | None = None


def _draw(args: DrawArgs) -> tuple[BytesIO, str]:
    # Base
    base = Image.new("RGBA", (WIDTH, HEIGHT), args.color)
    base_draw = ImageDraw.Draw(base)
    base_draw.rectangle((BORDER, BORDER, WIDTH - BORDER, HEIGHT - BORDER), fill=BACKGROUND_COLOR)

    # Album cover
    album_bytes = Image.open(BytesIO(args.album)).resize((ALBUM_SIZE, ALBUM_SIZE))
    album_position = (BORDER, BORDER)
    base.paste(album_bytes, album_position)

    # Spotify logo
    spotify_logo = Image.open(SPOTIFY_LOGO_PATH).resize((LOGO_SIZE, LOGO_SIZE))

    # Track title and artist
    title_font = get_font(args.name, bold=True, size=TITLE_FONT_SIZE)
    artist_font = get_font(", ".join(args.artists), bold=False, size=ARTIST_FONT_SIZE)

    title_width = title_font.getbbox(args.name)[2]
    available_width = WIDTH - CONTENT_START_X - LOGO_SIZE - PADDING * 2 - BORDER

    # Draw only one frame if the title fits
    if title_width <= available_width:
        base_draw.text((CONTENT_START_X, TITLE_START_Y), text=args.name, fill=TEXT_COLOR, font=title_font)  # type: ignore

        draw_static_elements(
            StaticDrawArgs(base_draw, base, args.artists, artist_font, args.duration, args.end, spotify_logo)
        )

        buffer = BytesIO()
        base.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer, "png"

    # Generate scrolling frames for the title
    title_frames = draw_text_scroll(title_font, args.name, available_width)
    num_frames = len(list(title_frames))

    frames: list[Image.Image] = []
    for _ in range(num_frames):
        frame = base.copy()
        frame_draw = ImageDraw.Draw(frame)
        frame.paste(next(title_frames), (CONTENT_START_X, TITLE_START_Y), next(title_frames))
        draw_static_elements(
            StaticDrawArgs(frame_draw, frame, args.artists, artist_font, args.duration, args.end, spotify_logo)
        )
        frames.append(frame)

    buffer = BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=FRAME_DURATION, loop=0)
    buffer.seek(0)
    return buffer, "gif"


@dataclass(frozen=True)
class StaticDrawArgs:
    draw: ImageDraw.ImageDraw
    image: Image.Image
    artists: list[str]
    artist_font: ImageFont.FreeTypeFont
    duration: datetime.timedelta | None
    end: datetime.datetime | None
    spotify_logo: Image.Image


def draw_static_elements(args: StaticDrawArgs) -> None:
    # Draw artist name
    draw.text(  # type: ignore
        (CONTENT_START_X, TITLE_START_Y + TITLE_FONT_SIZE + 5),
        text=", ".join(args.artists),
        fill=TEXT_COLOR,
        font=args.artist_font,
    )

    # Draw progress bar if duration and end are provided
    if args.duration and args.end:
        progress = get_progress(args.end, args.duration)
        _draw_track_bar(args.draw, progress, args.duration)

    args.image.paste(args.spotify_logo, (LOGO_X, LOGO_Y), args.spotify_logo)


def _draw_track_bar(draw: ImageDraw.ImageDraw, progress: float, duration: datetime.timedelta) -> None:
    """Draw the duration and progress bar of a given track.

    Parameters
    ----------
    draw : ImageDraw.Draw
        The draw object to use for drawing the progress bar
    progress : float
        The progress of the track as a percentage
    duration : datetime.timedelta
        The duration of the track
    """
    duration_width = PROGRESS_BAR_START_X + PROGRESS_BAR_WIDTH
    progress_width = max(
        PROGRESS_BAR_START_X, min(duration_width, PROGRESS_BAR_START_X + (PROGRESS_BAR_WIDTH * progress))
    )
    height = PROGRESS_BAR_Y + PROGRESS_BAR_HEIGHT
    x, y = PROGRESS_BAR_START_X, PROGRESS_BAR_Y

    # Draw background bar
    draw.rectangle((x, y, duration_width, height), fill=LENGTH_BAR_COLOR)

    # Draw progress bar only if it has a positive width
    if progress_width > x:
        draw.rectangle((x, y, progress_width, height), fill=PROGRESS_BAR_COLOR)

    played_seconds = min(int(duration.total_seconds()), int(duration.total_seconds() * progress))
    played = track_duration(played_seconds)
    track_duration_str = track_duration(int(duration.total_seconds()))
    progress_text = f"{played} / {track_duration_str}"
    progress_font = get_font(progress_text, bold=False, size=PROGRESS_FONT_SIZE)

    draw.text((x, PROGRESS_TEXT_Y), text=progress_text, fill=TEXT_COLOR, font=progress_font)  # type: ignore


def draw_text_scroll(font: ImageFont.FreeTypeFont, text: str, width: int) -> Generator[Image.Image, None, None]:
    """Draw the text of a given track. If the text is too long to fit on the card, the text will scroll instead.

    Parameters
    ----------
    font : ImageFont.FreeTypeFont
        The font to use for the text
    text : str
        The text to draw
    width : int
        The width of the card

    Yields
    ------
    Image.Image
        A frame of the text scrolling
    """
    text_bbox = font.getbbox(text)
    text_width = int(text_bbox[2] - text_bbox[0])
    text_height = int(text_bbox[3] - text_bbox[1])

    if text_width <= width:
        frame = Image.new("RGBA", (width, text_height))
        frame_draw = ImageDraw.Draw(frame)
        frame_draw.text((0, 0), text, fill=TEXT_COLOR, font=font)  # type: ignore
        yield frame
        return

    # Add space between end and start for continuous scrolling
    full_text = text + "   " + text
    full_text_bbox = font.getbbox(full_text)
    full_text_width = int(full_text_bbox[2] - full_text_bbox[0])

    pause_frames = 30
    total_frames = pause_frames + (full_text_width // SLIDING_SPEED)

    for i in range(total_frames):
        frame = Image.new("RGBA", (width, text_height))
        frame_draw = ImageDraw.Draw(frame)

        x_pos = 0 if i < pause_frames else -((i - pause_frames) * SLIDING_SPEED) % full_text_width

        frame_draw.text((x_pos, 0), full_text, fill=TEXT_COLOR, font=font)  # type: ignore
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
