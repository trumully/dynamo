import datetime
import logging
import re
import textwrap
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import ClassVar

import aiohttp
from PIL import Image, ImageDraw, ImageFont

from dynamo.utils.cache import async_lru_cache
from dynamo.utils.helper import ROOT, resolve_path_with_links

log = logging.getLogger(__name__)

FONT_PATH = resolve_path_with_links(Path(ROOT / "assets" / "fonts" / "Roboto-Regular.ttf"))
BOLD_FONT_PATH = resolve_path_with_links(Path(ROOT / "assets" / "fonts" / "Roboto-Bold.ttf"))
SPOTIFY_LOGO_PATH = resolve_path_with_links(Path(ROOT / "assets" / "img" / "spotify.png"))


# Dark blue
BACKGROUND_COLOR: tuple[int, int, int] = (5, 5, 25)

# White
TEXT_COLOR = PROGRESS_BAR_COLOR = (255, 255, 255)

# Light gray
LENGTH_BAR_COLOR: tuple[int, int, int] = (64, 64, 64)


@dataclass(frozen=True)
class SpotifyCard:
    album_size: ClassVar[tuple[int, int]] = (160, 160)
    width: ClassVar[int] = 500
    height: ClassVar[int] = 170
    padding: ClassVar[int] = 5
    max_size: ClassVar[int] = 20
    percentage: ClassVar[float] = 0.75

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
        # Create base image with the green border
        base = Image.new("RGBA", (self.width, self.height), color)
        base_draw = ImageDraw.Draw(base)

        # Draw the background, leaving a 5px border
        base_draw.rectangle(
            (self.padding, self.padding, self.width - self.padding, self.height - self.padding), fill=BACKGROUND_COLOR
        )

        # Resize and paste the album cover
        album_size = self.height - 2 * self.padding
        album_bytes = Image.open(album).resize((album_size, album_size))
        base.paste(album_bytes, (self.padding, self.padding))

        font_size = min(self.max_size, int(self.width * self.percentage))
        font = ImageFont.truetype(FONT_PATH, int(font_size * 0.8))
        bold = ImageFont.truetype(BOLD_FONT_PATH, font_size)

        # Title
        max_title_width = 437 - (album_size + 2 * self.padding)
        title_lines = textwrap.wrap(name, width=int(max_title_width / (font_size * 0.6)))
        title_height = 0
        for i, line in enumerate(title_lines[:2]):  # Limit to 2 lines
            base_draw.text(
                (album_size + 2 * self.padding, self.max_size + i * (font_size + 2)),
                text=line,
                fill=TEXT_COLOR,
                font=bold,
            )
            title_height += font_size + 2

        # Artists
        max_artists_width = 437 - (album_size + 2 * self.padding)
        artists_text = ", ".join(artists)
        artists_lines = textwrap.wrap(artists_text, width=int(max_artists_width / (font_size * 0.5)))
        for i, line in enumerate(artists_lines[:2]):  # Limit to 2 lines
            base_draw.text(
                (album_size + 2 * self.padding, self.max_size + title_height + 5 + i * (int(font_size * 0.8) + 2)),
                text=line,
                fill=TEXT_COLOR,
                font=font,
            )

        # Progress bar
        if duration and end:
            progress = self.get_progress(end, duration)
            base_draw.rectangle((175, 135, 375, 140), fill=LENGTH_BAR_COLOR)
            base_draw.rectangle((175, 135, 175 + int(200 * progress), 140), fill=PROGRESS_BAR_COLOR)

            played = self.track_duration(int(duration.total_seconds() * progress))
            track_duration = self.track_duration(int(duration.total_seconds()))
            progress_text = f"{played} / {track_duration}"
            base_draw.text((175, 145), text=progress_text, fill=TEXT_COLOR, font=font)

        spotify_logo = Image.open(SPOTIFY_LOGO_PATH).resize((48, 48))
        base.paste(spotify_logo, (437, 15), spotify_logo)

        buffer = BytesIO()
        base.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer


def valid_url(url: str) -> bool:
    return re.match(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", url) is not None


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
