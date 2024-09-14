import datetime
import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import ClassVar

import aiohttp
from PIL import Image, ImageDraw, ImageFont

from dynamo.utils.cache import async_lru_cache
from dynamo.utils.format import CJK, is_cjk
from dynamo.utils.helper import ROOT, resolve_path_with_links, valid_url

log = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class FontFamily:
    regular: Path
    bold: Path


latin: FontFamily = FontFamily(
    regular=resolve_path_with_links(Path(ROOT / "assets" / "fonts" / "static" / "NotoSans-Regular.ttf")),
    bold=resolve_path_with_links(Path(ROOT / "assets" / "fonts" / "static" / "NotoSans-Bold.ttf")),
)

chinese: FontFamily = FontFamily(
    regular=resolve_path_with_links(Path(ROOT / "assets" / "fonts" / "static" / "NotoSansTC-Regular.ttf")),
    bold=resolve_path_with_links(Path(ROOT / "assets" / "fonts" / "static" / "NotoSansTC-Bold.ttf")),
)

japanese: FontFamily = FontFamily(
    regular=resolve_path_with_links(Path(ROOT / "assets" / "fonts" / "static" / "NotoSansJP-Regular.ttf")),
    bold=resolve_path_with_links(Path(ROOT / "assets" / "fonts" / "static" / "NotoSansJP-Bold.ttf")),
)

korean: FontFamily = FontFamily(
    regular=resolve_path_with_links(Path(ROOT / "assets" / "fonts" / "static" / "NotoSansKR-Regular.ttf")),
    bold=resolve_path_with_links(Path(ROOT / "assets" / "fonts" / "static" / "NotoSansKR-Bold.ttf")),
)

SPOTIFY_LOGO_PATH = resolve_path_with_links(Path(ROOT / "assets" / "images" / "spotify.png"))

FONTS: dict[CJK, FontFamily] = {
    CJK.NONE: latin,
    CJK.CHINESE: chinese,
    CJK.JAPANESE: japanese,
    CJK.KOREAN: korean,
}

# Dark blue
BACKGROUND_COLOR: tuple[int, int, int] = (5, 5, 25)

# White
TEXT_COLOR = PROGRESS_BAR_COLOR = (255, 255, 255)

# Light gray
LENGTH_BAR_COLOR: tuple[int, int, int] = (64, 64, 64)


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

    @staticmethod
    def get_font(text: str, bold: bool = False, size: int = 22) -> ImageFont.FreeTypeFont:
        font_family = FONTS[is_cjk(text)]
        font_path = font_family.bold if bold else font_family.regular
        return ImageFont.truetype(font_path, size)

    @staticmethod
    def track_duration(seconds: int) -> str:
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def get_progress(end: datetime.datetime, duration: datetime.timedelta) -> float:
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        return 1 - (end - now).total_seconds() / duration.total_seconds()

    def draw(
        self,
        name: str,
        artists: list[str],
        color: tuple[int, int, int],
        album: BytesIO,
        duration: datetime.timedelta | None = None,
        end: datetime.datetime | None = None,
    ) -> BytesIO:
        # Create base image with the colored border
        base = Image.new("RGBA", (self.width, self.height), color)
        base_draw = ImageDraw.Draw(base)

        # Draw the background, leaving a 5px border
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

        # Progress bar and duration
        if duration and end:
            progress = self.get_progress(end, duration)

            base_draw.rectangle(
                (
                    self.progress_bar_start_x,
                    self.progress_bar_y,
                    self.progress_bar_start_x + self.progress_bar_width,
                    self.progress_bar_y + self.progress_bar_height,
                ),
                fill=LENGTH_BAR_COLOR,
            )

            base_draw.rectangle(
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

            base_draw.text(
                (self.progress_bar_start_x, self.progress_text_y),
                text=progress_text,
                fill=TEXT_COLOR,
                font=progress_font,
            )

        # Spotify logo
        spotify_logo = Image.open(SPOTIFY_LOGO_PATH).resize((self.logo_size, self.logo_size))
        base.paste(spotify_logo, (self.logo_x, self.logo_y), spotify_logo)

        buffer = BytesIO()
        base.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer


@async_lru_cache()
async def fetch_album_cover(url: str, session: aiohttp.ClientSession) -> BytesIO | None:
    if not valid_url(url):
        log.exception("Invalid URL: %s", url)
        return None

    async with session.get(url) as response:
        if response.status != 200:
            log.exception("Failed to fetch album cover: %s", response.status)
            return None

        buffer = BytesIO(await response.read())
        buffer.seek(0)
        return buffer
