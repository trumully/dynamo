import asyncio
import datetime
import logging
from collections.abc import Generator
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
    album_size: ClassVar[int] = height - (border * 2) + 1  # Fits exactly within the blue box

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

    sliding_speed: ClassVar[int] = 6  # pixels per frame
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

        # Calculate the available width for the title
        available_width = self.width - self.content_start_x - self.logo_size - self.padding * 2 - self.border

        # Spotify logo
        spotify_logo = Image.open(SPOTIFY_LOGO_PATH).resize((self.logo_size, self.logo_size))

        # Check if the title is too long
        title_width = title_font.getbbox(name)[2]
        if title_width > available_width:
            # Generate scrolling frames for the title
            title_frames = list(self._draw_text_scroll(title_font, name, available_width))
            num_frames = len(title_frames)

            frames = []
            for i in range(num_frames):
                frame = base.copy()
                frame_draw = ImageDraw.Draw(frame)

                # Paste the scrolling title
                frame.paste(title_frames[i], (self.content_start_x, self.title_start_y), title_frames[i])

                # Draw static elements
                self._draw_static_elements(frame_draw, frame, artists, artist_font, duration, end, spotify_logo)

                frames.append(frame)

            # Save as animated GIF
            buffer = BytesIO()
            frames[0].save(
                buffer,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=self.frame_duration,
                loop=0,
            )
            buffer.seek(0)
            return buffer, "gif"

        # Draw static image with non-scrolling title
        base_draw.text(
            (self.content_start_x, self.title_start_y),
            text=name,
            fill=TEXT_COLOR,
            font=title_font,
        )

        # Draw static elements
        self._draw_static_elements(base_draw, base, artists, artist_font, duration, end, spotify_logo)

        # Save as static PNG
        buffer = BytesIO()
        base.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer, "png"

    def _draw_static_elements(
        self,
        draw: ImageDraw.Draw,
        image: Image.Image,
        artists: list[str],
        artist_font: ImageFont.FreeTypeFont,
        duration: datetime.timedelta | None,
        end: datetime.datetime | None,
        spotify_logo: Image.Image,
    ) -> None:
        # Draw artist name
        draw.text(
            (self.content_start_x, self.title_start_y + self.title_font_size + 5),
            text=", ".join(artists),
            fill=TEXT_COLOR,
            font=artist_font,
        )

        # Draw progress bar if duration and end are provided
        if duration and end:
            progress = self.get_progress(end, duration)
            self._draw_progress_bar(draw, progress, duration)

        # Draw Spotify logo
        image.paste(spotify_logo, (self.logo_x, self.logo_y), spotify_logo)

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

    def _draw_text_scroll(
        self, font: ImageFont.FreeTypeFont, text: str, width: int
    ) -> Generator[Image.Image, None, None]:
        text_width, text_height = font.getbbox(text)[2:]

        if text_width <= width:
            # If text fits, yield a single frame with the full text
            frame = Image.new("RGBA", (width, text_height))
            frame_draw = ImageDraw.Draw(frame)
            frame_draw.text((0, 0), text, fill=TEXT_COLOR, font=font)
            yield frame
            return

        # Calculate how much text needs to scroll
        overflow_width = text_width - width

        # Number of frames for the pause at the beginning and end
        pause_frames = 30

        # Total frames including pause at start, scrolling, and pause at end
        total_frames = pause_frames * 2 + (overflow_width // self.sliding_speed)

        for i in range(total_frames):
            frame = Image.new("RGBA", (width, text_height))
            frame_draw = ImageDraw.Draw(frame)

            if i < pause_frames:
                # Initial pause: text stays at the beginning
                x_pos = 0
            elif i >= total_frames - pause_frames:
                # End pause: text stays at the end
                x_pos = -overflow_width
            else:
                # Scrolling: text moves from right to left
                x_pos = -((i - pause_frames) * self.sliding_speed)

            frame_draw.text((x_pos, 0), text, fill=TEXT_COLOR, font=font)
            yield frame


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
