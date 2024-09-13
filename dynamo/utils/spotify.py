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

from dynamo.utils.helper import ROOT, resolve_path_with_links

log = logging.getLogger(__name__)

FONT_PATH = resolve_path_with_links(Path(ROOT / "assets" / "fonts" / "Roboto-Regular.ttf"))
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
        album_bytes = Image.open(album).resize(self.album_size)

        base = Image.new("RGBA", (self.width, self.height), color)
        base_draw = ImageDraw.Draw(base)
        offset_x = offset_y = self.padding
        width, height = self.width - offset_x, self.height - offset_y

        font_size = min(self.max_size, self.width * self.percentage)
        font = ImageFont.truetype(FONT_PATH, font_size)

        # Background
        base_draw.rectangle((offset_x, offset_y, width, height), fill=BACKGROUND_COLOR)
        base_draw.text(
            (self.height + self.padding, self.max_size - self.padding),
            text=name,
            fill=TEXT_COLOR,
            font=font,
        )

        # Artists
        artists_text = "\n".join(textwrap.wrap(", ".join(artists), width=35))
        base_draw.text(
            (self.height + self.padding, self.padding * 9),
            text=artists_text,
            fill=TEXT_COLOR,
            font=font,
        )

        # Progress bar
        if duration and end:
            progress = self.get_progress(end, duration)
            base_draw.rectangle((175, 125, 375, 130), fill=LENGTH_BAR_COLOR)
            base_draw.rectangle((175, 125, 175 + int(200 * progress), 130), fill=PROGRESS_BAR_COLOR)

            played = self.track_duration(int(duration.total_seconds() * progress))
            track_duration = self.track_duration(int(duration.total_seconds()))
            progress_text = f"{played} / {track_duration}"
            base_draw.text((175, 130), text=progress_text, fill=TEXT_COLOR, font=font)

        base.paste(album_bytes, (self.padding, self.padding))
        spotify_logo = Image.open(SPOTIFY_LOGO_PATH).resize((48, 48))
        base.paste(spotify_logo, (437, 15), spotify_logo)

        buffer = BytesIO()
        base.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer


def valid_url(url: str) -> bool:
    return re.match(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", url) is not None


async def fetch_album_cover(url: str, session: aiohttp.ClientSession) -> bytes | None:
    if not valid_url(url):
        log.exception("Invalid URL: %s", url)
        return None

    async with session.get(url) as response:
        if response.status != 200:
            log.exception("Failed to fetch album cover: %s", response.status)
            return None

        try:
            return await response.read()
        except Exception:
            log.exception("Failed to fetch album cover: %s", url)
            return None
