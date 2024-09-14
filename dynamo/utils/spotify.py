import asyncio
import datetime
import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import ClassVar

import aiohttp
from PIL import Image, ImageDraw, ImageFont

from dynamo.utils.cache import async_lru_cache
from dynamo.utils.format import FONTS, is_cjk
from dynamo.utils.helper import ROOT, resolve_path_with_links, valid_url

log = logging.getLogger(__name__)

# Dark blue
BACKGROUND_COLOR: tuple[int, int, int] = (5, 5, 25)

# White
TEXT_COLOR = PROGRESS_BAR_COLOR = (255, 255, 255)

# Light gray
LENGTH_BAR_COLOR: tuple[int, int, int] = (64, 64, 64)


SPOTIFY_LOGO_PATH = resolve_path_with_links(Path(ROOT / "assets" / "images" / "spotify.png"))


@dataclass(frozen=True)
class SpotifyCard:
    # Card dimensions
    width: ClassVar[int] = 800
    height: ClassVar[int] = 250
    padding: ClassVar[int] = 15
    border: ClassVar[int] = 8

    # Album cover
    album_size: ClassVar[int] = height - (border * 2)  # Fits exactly within the blue box

    # Font settings
    title_font_size: ClassVar[int] = 28
    artist_font_size: ClassVar[int] = 22
    progress_font_size: ClassVar[int] = 18

    # Spotify logo
    logo_size: ClassVar[int] = 48
    logo_x: ClassVar[int] = width - logo_size - padding - border
    logo_y: ClassVar[int] = padding + border

    # Layout
    content_start_x: ClassVar[int] = album_size + border * 2
    content_width: ClassVar[int] = width - content_start_x - padding - border
    title_start_y: ClassVar[int] = padding

    # Progress bar
    progress_bar_start_x: ClassVar[int] = content_start_x
    progress_bar_width: ClassVar[int] = width - content_start_x - padding - border - 70  # Account for Spotify logo
    progress_bar_height: ClassVar[int] = 6
    progress_bar_y: ClassVar[int] = height - padding - border - progress_bar_height - 30
    progress_text_y: ClassVar[int] = height - padding - border - 24

    sliding_speed: ClassVar[int] = 2  # pixels per frame
    max_frames: ClassVar[int] = 480  # number of frames for sliding animation
    frame_duration: ClassVar[int] = 50  # duration of each frame in milliseconds

    @staticmethod
    def get_font(text: str, bold: bool = False, size: int = 22) -> ImageFont.FreeTypeFont:
        font_family = FONTS[is_cjk(text)]
        font_path = font_family.bold if bold else font_family.regular
        return ImageFont.truetype(font_path, size)

    @staticmethod
    def track_duration(seconds: int) -> str:
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def get_progress(end: datetime.datetime, duration: datetime.timedelta) -> float:
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        return 1 - (end - now).total_seconds() / duration.total_seconds()

    async def draw(
        self,
        name: str,
        artists: list[str],
        color: tuple[int, int, int],
        album: BytesIO,
        duration: datetime.timedelta | None = None,
        end: datetime.datetime | None = None,
    ) -> tuple[BytesIO, str]:
        return await asyncio.to_thread(self._draw, name, artists, color, album, duration, end)

    def _draw(
        self,
        name: str,
        artists: list[str],
        color: tuple[int, int, int],
        album: BytesIO,
        duration: datetime.timedelta | None = None,
        end: datetime.datetime | None = None,
    ) -> tuple[BytesIO, str]:
        # Create base image with the colored border
        base = Image.new("RGBA", (self.width, self.height), color)
        base_draw = ImageDraw.Draw(base)

        # Draw the background, leaving a border
        base_draw.rectangle(
            (self.border, self.border, self.width - self.border, self.height - self.border),
            fill=BACKGROUND_COLOR,
        )

        # Resize and paste the album cover
        album_bytes = Image.open(album).resize((self.album_size, self.album_size))
        album_position = (self.border, self.border)
        base.paste(album_bytes, album_position)

        # Title and artist
        title_font = self.get_font(name, bold=True, size=self.title_font_size)
        artist_font = self.get_font(", ".join(artists), bold=False, size=self.artist_font_size)

        base_draw.text(
            (self.content_start_x, self.title_start_y),
            text=name,
            fill=TEXT_COLOR,
            font=title_font,
        )

        base_draw.text(
            (self.content_start_x, self.title_start_y + self.title_font_size + 5),
            text=", ".join(artists),
            fill=TEXT_COLOR,
            font=artist_font,
        )

        if duration and end:
            progress = self.get_progress(end, duration)
            self._draw_progress_bar(base_draw, progress, duration)

        # Draw Spotify logo
        spotify_logo = Image.open(SPOTIFY_LOGO_PATH).resize((self.logo_size, self.logo_size))
        base.paste(spotify_logo, (self.logo_x, self.logo_y), spotify_logo)

        # Save as static PNG
        buffer = BytesIO()
        base.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer, "png"

    def _draw_progress_bar(self, draw: ImageDraw.Draw, progress: float, duration: datetime.timedelta):
        draw.rectangle(
            (
                self.progress_bar_start_x,
                self.progress_bar_y,
                self.progress_bar_start_x + self.progress_bar_width,
                self.progress_bar_y + self.progress_bar_height,
            ),
            fill=LENGTH_BAR_COLOR,
        )

        draw.rectangle(
            (
                self.progress_bar_start_x,
                self.progress_bar_y,
                self.progress_bar_start_x + int(self.progress_bar_width * progress),
                self.progress_bar_y + self.progress_bar_height,
            ),
            fill=PROGRESS_BAR_COLOR,
        )

        played = self.track_duration(int(duration.total_seconds() * progress))
        track_duration = self.track_duration(int(duration.total_seconds()))
        progress_text = f"{played} / {track_duration}"
        progress_font = self.get_font(progress_text, bold=False, size=self.progress_font_size)

        draw.text(
            (self.progress_bar_start_x, self.progress_text_y),
            text=progress_text,
            fill=TEXT_COLOR,
            font=progress_font,
        )


@async_lru_cache()
async def fetch_album_cover(url: str, session: aiohttp.ClientSession) -> bytes | None:
    """Fetch album cover from a URL

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

    async def _fetch(url: str, session: aiohttp.ClientSession) -> bytes | None:
        if not valid_url(url):
            log.exception("Invalid URL: %s", url)
            return None

        try:
            async with session.get(url) as response:
                if response.status != 200:
                    log.exception("Failed to fetch album cover: %s", response.status)
                    return None

                return await response.read()
        except Exception:
            log.exception("Error fetching album cover: %s", url)
            return None

    return await _fetch(url, session)
