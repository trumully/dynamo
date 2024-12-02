import datetime
import logging
from collections.abc import Generator
from contextlib import contextmanager
from io import BytesIO
from typing import Any, NamedTuple

import aiohttp
import discord
from dynamo_utils.task_cache import lru_task_cache
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from dynamo.typedefs import SequenceNotStr
from dynamo.utils.format import FONTS, human_join, is_cjk
from dynamo.utils.helper import ROOT
from dynamo.utils.wrappers import executor_function

log = logging.getLogger(__name__)


class Layout(NamedTuple):
    width: int
    height: int
    padding: int
    border: int
    album_size: int
    logo_size: int
    content_offset: int


LAYOUT = Layout(
    width=800,
    height=250,
    padding=15,
    border=0,
    album_size=250,
    logo_size=48,
    content_offset=20,
)

# Font sizes
FONT_SIZES = {
    "title": 28,
    "artist": 22,
    "progress": 18,
}

SPOTIFY_LOGO_PATH = ROOT / "dynamo" / "assets" / "images" / "spotify.png"

# Layout
CONTENT_START_X: int = LAYOUT.album_size + LAYOUT.content_offset
CONTENT_WIDTH: int = (
    LAYOUT.width - CONTENT_START_X - LAYOUT.padding - LAYOUT.border - LAYOUT.logo_size
)
TITLE_START_Y: int = LAYOUT.padding

# Progress bar
PROGRESS_BAR_START_X: int = CONTENT_START_X
PROGRESS_BAR_WIDTH: int = (
    LAYOUT.width - CONTENT_START_X - LAYOUT.padding - LAYOUT.border - 70
)
PROGRESS_BAR_HEIGHT: int = 6
PROGRESS_BAR_Y: int = (
    LAYOUT.height - LAYOUT.padding - LAYOUT.border - PROGRESS_BAR_HEIGHT - 30
)
PROGRESS_TEXT_Y: int = LAYOUT.height - LAYOUT.padding - LAYOUT.border - 24

BASE_SLIDING_SPEED: int = 2
MAX_SLIDING_SPEED: int = 10
TOTAL_ANIMATION_TIME: int = 1000
MIN_FRAME_DURATION: int = 30
MAX_FRAME_DURATION: int = 100


@contextmanager
def open_image_bytes(image: bytes) -> Generator[Image.Image]:
    buffer = BytesIO(image)
    buffer.seek(0)
    try:
        yield Image.open(buffer)
    finally:
        buffer.close()


class StaticDrawArgs(NamedTuple):
    artists: SequenceNotStr[str]
    artist_font: ImageFont.FreeTypeFont
    duration: datetime.timedelta | None
    end: datetime.datetime | None
    spotify_logo: Image.Image


def make_embed(
    user: discord.Member | discord.User,
    activity: discord.Spotify,
    image: BytesIO,
    emoji: str,
    *,
    ext: str,
) -> tuple[discord.Embed, discord.File]:
    """Make an embed for the currently playing Spotify track."""
    filename = f"spotify-card.{ext}"
    track = f"[{activity.title}](<{activity.track_url}>)"
    file = discord.File(image, filename=filename)
    description = f"{user.mention} is listening to **{track}** by **{human_join(activity.artists, conjunction='and')}**"
    embed = discord.Embed(
        title=f"{emoji} Now Playing", description=description, color=activity.color
    )
    embed.set_image(url=f"attachment://{filename}")
    return embed, file


@executor_function
def draw(activity: discord.Spotify, album: bytes) -> tuple[BytesIO, str]:
    with open_image_bytes(album) as album_image:
        base, base_draw = create_base_image(album_image)
        paste_album_cover(base, album_image)

    title_font = get_font(activity.title, FONT_SIZES["title"], bold=True)
    artist_font = get_font(", ".join(activity.artists), FONT_SIZES["artist"])
    spotify_logo = Image.open(SPOTIFY_LOGO_PATH).resize((
        LAYOUT.logo_size,
        LAYOUT.logo_size,
    ))
    static_args = StaticDrawArgs(
        artists=activity.artists,
        artist_font=artist_font,
        duration=activity.duration,
        end=activity.end,
        spotify_logo=spotify_logo,
    )

    # Check if title fits and handle accordingly
    if int(title_font.getbbox(activity.title)[2]) <= CONTENT_WIDTH:
        base_draw.text(
            (CONTENT_START_X, TITLE_START_Y),
            activity.title,
            fill=(255, 255, 255),
            font=title_font,
        )
        draw_static_elements(base_draw, base, static_args)
        return save_image(base, "PNG")

    # Handle animated title
    frames = [
        create_frame(base, text_frame, static_args)
        for text_frame in draw_text_scroll(title_font, activity.title, CONTENT_WIDTH)
    ]
    frame_duration = min(
        max(TOTAL_ANIMATION_TIME // len(frames), MIN_FRAME_DURATION), MAX_FRAME_DURATION
    )
    return save_image(
        frames[0],
        "GIF",
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration,
        loop=0,
    )


def draw_static_image(
    base: Image.Image,
    base_draw: ImageDraw.ImageDraw,
    activity: discord.Spotify,
    title_font: ImageFont.FreeTypeFont,
    artist_font: ImageFont.FreeTypeFont,
) -> tuple[BytesIO, str]:
    base_draw.text(
        (CONTENT_START_X, TITLE_START_Y),
        activity.title,
        fill=(255, 255, 255),
        font=title_font,
    )
    spotify_logo = Image.open(SPOTIFY_LOGO_PATH).resize((
        LAYOUT.logo_size,
        LAYOUT.logo_size,
    ))
    static_args = StaticDrawArgs(
        activity.artists, artist_font, activity.duration, activity.end, spotify_logo
    )
    draw_static_elements(base_draw, base, static_args)
    return save_image(base, "PNG")


def draw_animated_image(
    base: Image.Image,
    activity: discord.Spotify,
    title_font: ImageFont.FreeTypeFont,
    artist_font: ImageFont.FreeTypeFont,
    available_width: int,
) -> tuple[BytesIO, str]:
    text_frames = list(draw_text_scroll(title_font, activity.title, available_width))
    spotify_logo = Image.open(SPOTIFY_LOGO_PATH).resize((
        LAYOUT.logo_size,
        LAYOUT.logo_size,
    ))
    static_args = StaticDrawArgs(
        activity.artists, artist_font, activity.duration, activity.end, spotify_logo
    )

    frames = [create_frame(base, text_frame, static_args) for text_frame in text_frames]
    frame_duration = min(
        max(TOTAL_ANIMATION_TIME // len(frames), MIN_FRAME_DURATION), MAX_FRAME_DURATION
    )

    return save_image(
        frames[0],
        "GIF",
        save_all=True,
        append_images=frames[1:],
        duration=frame_duration,
        loop=0,
    )


def create_frame(
    base: Image.Image, text_frame: Image.Image, static_args: StaticDrawArgs
) -> Image.Image:
    frame = base.copy()
    frame.paste(text_frame, (CONTENT_START_X, TITLE_START_Y), text_frame)
    draw_static_elements(ImageDraw.Draw(frame), frame, static_args)
    return frame


def save_image(
    image: Image.Image, image_format: str, **kwargs: Any
) -> tuple[BytesIO, str]:
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
    """Convert a track duration in seconds to a string."""
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{f'{hours}:' if hours else ''}{minutes:02d}:{seconds:02d}"


def get_progress(end: datetime.datetime, duration: datetime.timedelta) -> float:
    """Get the progress of the track as a percentage."""
    now = datetime.datetime.now(tz=datetime.UTC)
    return 1 - (end - now).total_seconds() / duration.total_seconds()


def create_base_image(album: Image.Image) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    base = Image.new("RGBA", (LAYOUT.width, LAYOUT.height))
    gradient = create_gradient_background(album)
    base.paste(gradient, (0, 0))
    base_draw = ImageDraw.Draw(base)
    return base, base_draw


def create_gradient_background(album: Image.Image) -> Image.Image:
    # Resize and blur the album cover
    blurred = (
        album.copy()
        .resize((LAYOUT.width, LAYOUT.height))
        .filter(ImageFilter.GaussianBlur(radius=30))
    )

    # Create a gradient overlay
    gradient = Image.new("RGBA", (LAYOUT.width, LAYOUT.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient)
    for y in range(LAYOUT.height):
        alpha = int(255 * (1 - y / LAYOUT.height))
        draw.line([(0, y), (LAYOUT.width, y)], fill=(0, 0, 0, alpha))

    # Composite the blurred image and gradient
    blurred = Image.alpha_composite(blurred.convert("RGBA"), gradient)

    # Darken the overall image
    darkened = Image.new("RGBA", blurred.size, (0, 0, 0, 64))
    return Image.alpha_composite(blurred, darkened)


def paste_album_cover(base: Image.Image, album_image: Image.Image) -> None:
    album_resized = album_image.resize((LAYOUT.album_size, LAYOUT.album_size))
    base.paste(album_resized, (LAYOUT.border, LAYOUT.border))


def draw_static_elements(
    draw: ImageDraw.ImageDraw, image: Image.Image, args: StaticDrawArgs
) -> None:
    draw.text(
        xy=(CONTENT_START_X, TITLE_START_Y + FONT_SIZES["title"] + 5),
        text=", ".join(args.artists),
        fill=(255, 255, 255),  # White text
        font=args.artist_font,
    )

    if args.duration and args.end:
        progress = get_progress(args.end, args.duration)
        draw_track_bar(draw, progress, args.duration)

    image.paste(
        args.spotify_logo,
        (
            LAYOUT.width - LAYOUT.logo_size - LAYOUT.padding - LAYOUT.border,
            LAYOUT.padding + LAYOUT.border,
        ),
        args.spotify_logo,
    )


def draw_track_bar(
    draw: ImageDraw.ImageDraw, progress: float, duration: datetime.timedelta
) -> None:
    duration_width = PROGRESS_BAR_START_X + PROGRESS_BAR_WIDTH
    progress_width = max(
        PROGRESS_BAR_START_X,
        min(duration_width, PROGRESS_BAR_START_X + (PROGRESS_BAR_WIDTH * progress)),
    )

    draw.rectangle(
        (
            PROGRESS_BAR_START_X,
            PROGRESS_BAR_Y,
            duration_width,
            PROGRESS_BAR_Y + PROGRESS_BAR_HEIGHT,
        ),
        fill=(64, 64, 64),  # Dark gray for the background bar
    )

    if progress_width > PROGRESS_BAR_START_X:
        draw.rectangle(
            (
                PROGRESS_BAR_START_X,
                PROGRESS_BAR_Y,
                progress_width,
                PROGRESS_BAR_Y + PROGRESS_BAR_HEIGHT,
            ),
            fill=(255, 255, 255),  # White for the progress bar
        )

    played_seconds = min(
        int(duration.total_seconds()), int(duration.total_seconds() * progress)
    )
    progress_text = f"{track_duration(played_seconds)} / {track_duration(int(duration.total_seconds()))}"
    progress_font = get_font(progress_text, FONT_SIZES["progress"])
    draw.text(
        (PROGRESS_BAR_START_X, PROGRESS_TEXT_Y),
        progress_text,
        fill=(255, 255, 255),
        font=progress_font,
    )


def draw_text_scroll(
    font: ImageFont.FreeTypeFont, text: str, width: int
) -> list[Image.Image]:
    text_width = int(font.getbbox(text)[2])
    if text_width <= width:
        return [create_text_frame(text, width, int(font.getbbox(text)[3]), font)]

    padded_text = f"{text}   {text}"
    full_width = font.getbbox(padded_text)[2]
    sliding_speed = min(
        MAX_SLIDING_SPEED,
        max(
            BASE_SLIDING_SPEED, full_width // (TOTAL_ANIMATION_TIME // MIN_FRAME_DURATION)
        ),
    )
    num_frames = int(
        min(TOTAL_ANIMATION_TIME // MIN_FRAME_DURATION, full_width // sliding_speed)
    )

    return [
        create_text_frame(
            padded_text,
            width,
            int(font.getbbox(text)[3]),
            font,
            int(-i * sliding_speed % full_width),
        )
        for i in range(num_frames)
    ]


def create_text_frame(
    text: str, width: int, height: int, font: ImageFont.FreeTypeFont, x_pos: int = 0
) -> Image.Image:
    frame = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(frame)
    draw.text((x_pos, 0), text, fill=(255, 255, 255), font=font)
    draw.text((x_pos + font.getbbox(text)[2], 0), text, fill=(255, 255, 255), font=font)
    return frame


@lru_task_cache(maxsize=128)
async def fetch_album_cover(url: str, session: aiohttp.ClientSession) -> bytes | None:
    try:
        async with session.get(url) as response:
            if response.status == 200:  # noqa: PLR2004
                return await response.read()
            log.warning("Failed to fetch album cover: %s", response.status)
    except aiohttp.ClientResponseError:
        log.exception("Error fetching album cover: %s", url)

    return None
