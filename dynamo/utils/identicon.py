from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, field
from io import BytesIO
from typing import Annotated, Self, TypeVar

import numpy as np
from PIL import Image

from dynamo.utils.cache import async_lru_cache

# 765 * 0.4
COLOR_THRESHOLD = 306


D = TypeVar("D", bound=np.generic)
ArrayRGB = Annotated[np.ndarray[D], tuple[int, int, int]]


def color_distance(x: RGB, /, y: RGB) -> float:
    """Measure distance between two colors

    .. [1] https://www.compuphase.com/cmetric.htm

    Parameters
    ----------
    x : RGB
        The first color
    y : RGB
        The second color

    Returns
    -------
    float
        The distance between the two colors
    """
    mean = red_mean(x, y)
    r, g, b = (x - y).as_tuple()

    return math.sqrt((((512 + mean) * r * r) >> 8) + 4 * g * g + (((767 - mean) * b * b) >> 8))


def make_color(seed: int) -> RGB:
    """Make a color from a given seed

    Parameters
    ----------
    seed : int
        The seed to generate the color from

    Returns
    -------
    RGB
        The color generated from the seed
    """
    rng = np.random.default_rng(seed=seed)
    return RGB(*(int(v) - 1 for v in rng.choice(256, size=3)))


def get_colors(fg: RGB | None = None, bg: RGB | None = None, *, seed: int) -> tuple[RGB, RGB]:
    """Get two colors from a given seed

    Parameters
    ----------
    fg : RGB | None
        The foreground color
    bg : RGB | None
        The background color
    seed : int
        The seed to generate the colors from

    Returns
    -------
    tuple[RGB, RGB]
        The foreground and background colors
    """
    fg = fg or make_color(seed)
    bg = bg or make_color(int(str(seed)[::-1]))

    return (fg, bg) if fg != bg else (fg.flip(), bg)


def red_mean(a: RGB, b: RGB) -> int:
    return (a.r + b.r) // 2


def rgb_as_hex(rgb: RGB) -> str:
    return f"#{rgb.r:02x}{rgb.g:02x}{rgb.b:02x}"


@dataclass(slots=True)
class RGB:
    r: int
    g: int
    b: int

    def __post_init__(self):
        """Clamp the RGB values to the range [0, 255]"""
        self.r = max(0, min(self.r, 255))
        self.g = max(0, min(self.g, 255))
        self.b = max(0, min(self.b, 255))

    def __sub__(self, other: RGB) -> Self:
        """Subtract two colors, clamping the result to [0, 255]"""
        self.r = max(self.r - other.r, 0)
        self.g = max(self.g - other.g, 0)
        self.b = max(self.b - other.b, 0)
        return self

    def __eq__(self, other: RGB) -> bool:
        return color_distance(self, other) <= COLOR_THRESHOLD

    def __ne__(self, other: RGB) -> bool:
        return color_distance(self, other) > COLOR_THRESHOLD

    def flip(self) -> Self:
        self.r = 255 - self.r
        self.g = 255 - self.g
        self.b = 255 - self.b
        return self

    def as_tuple(self) -> tuple[int, int, int]:
        return self.r, self.g, self.b


@dataclass
class Identicon:
    """An identicon is a visual representation of a random seed."""

    size: int
    fg: RGB
    bg: RGB
    fg_weight: float
    seed: int

    rng: np.random.Generator | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(seed=self.seed)

    @property
    def pattern(self) -> ArrayRGB:
        colors = np.array((self.fg, self.bg))
        size = (self.size * 2, self.size)
        weight = (self.fg_weight, 1 - self.fg_weight)
        return self.rng.choice(colors, size=size, p=weight)

    @property
    def icon(self) -> ArrayRGB:
        return self.reflect(np.array([[c.as_tuple() for c in row] for row in self.pattern]))

    @staticmethod
    def reflect(matrix: np.ndarray) -> ArrayRGB:
        return np.hstack((matrix, np.fliplr(matrix)))

    def __eq__(self, other: Identicon) -> bool:
        return self.seed == other.seed

    def __hash__(self) -> int:
        # TODO: This is ok for now but should be more specific if we want user customisable identicons
        return hash(self.seed)


def seed_from_time() -> int:
    """Generate a seed from the current time"""
    return int(str(time.monotonic()).replace(".", ""))


@async_lru_cache()
async def identicon_buffer(idt: Identicon, size: int = 256) -> bytes:
    """Generate a buffer for an identicon

    Parameters
    ----------
    idt : Identicon
        The identicon to generate a buffer for
    size : int, optional
        The size of the buffer to generate, by default 256

    Returns
    -------
    bytes
        The buffer for the identicon
    """

    def _buffer(idt: Identicon, size: int) -> bytes:
        with BytesIO() as buffer:
            im = Image.fromarray(idt.icon.astype("uint8"))
            im = im.convert("RGB")
            im = im.resize((size, size), Image.Resampling.NEAREST)
            im.save(buffer, format="png")
            buffer.seek(0)
            return buffer.getvalue()

    return await asyncio.to_thread(_buffer, idt, size)
