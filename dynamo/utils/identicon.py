from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, field
from io import BytesIO
from typing import Annotated, Self

import numpy as np
from PIL import Image

from dynamo.utils.cache import future_lru_cache

# 0.0 = same color
COLOR_THRESHOLD = 0.4

ArrayRGB = Annotated[np.ndarray, tuple[int, int, int]]


def _clamp(value: int, upper: int) -> int:
    return max(0, min(value, upper))


@dataclass
class RGB:
    r: int
    g: int
    b: int

    def __post_init__(self) -> None:
        """Clamp the RGB values to the range [0, 255]"""
        self.r = _clamp(self.r, 255)
        self.g = _clamp(self.g, 255)
        self.b = _clamp(self.b, 255)

    def difference(self, other: RGB) -> tuple[int, int, int]:
        return self.r - other.r, self.g - other.g, self.b - other.b

    def is_similar(self, other: RGB) -> bool:
        """Check if two colors are similar based on perceived color distance

        Parameters
        ----------
        other : RGB
            The color to compare to

        Returns
        -------
        bool
            Whether the two colors are similar
        """
        return self.perceived_distance(other) <= COLOR_THRESHOLD and self.euclidean_distance(other) <= COLOR_THRESHOLD

    def euclidean_distance(self, other: RGB) -> float:
        return euclidean_distance_to_max(self, other)

    def perceived_distance(self, other: RGB) -> float:
        return perceived_distance_to_max(self, other)

    def flip(self) -> Self:
        self.r = _clamp(255 - self.r, 255)
        self.g = _clamp(255 - self.g, 255)
        self.b = _clamp(255 - self.b, 255)
        return self

    def as_tuple(self) -> tuple[int, int, int]:
        return self.r, self.g, self.b


def perceived_color_distance(x: RGB, y: RGB) -> float:
    """Measure perceived distance between two colors

    .. [1] https://www.compuphase.com/cmetric.htm
    .. [2] https://stackoverflow.com/questions/8863810/python-find-similar-colors-best-way

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
    red_mean = (x.r + y.r) / 2
    r, g, b = x.difference(y)

    return math.sqrt((512 + red_mean) / 256 * r**2 + 4 * g**2 + (767 - red_mean) / 256 * b**2)


def euclidean_color_distance(x: RGB, y: RGB) -> float:
    """Measure euclidean distance between two colors


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

    See
    ---
        :func:`perceived_color_distance`
    """
    r, g, b = x.difference(y)
    return math.sqrt(r**2 + g**2 + b**2)


BLACK: RGB = RGB(0, 0, 0)
WHITE: RGB = RGB(255, 255, 255)
MAX_PERCEIVED_DISTANCE: float = perceived_color_distance(WHITE, BLACK)
MAX_EUCLIDEAN_DISTANCE: float = euclidean_color_distance(WHITE, BLACK)


def perceived_distance_to_max(x: RGB, y: RGB) -> float:
    return perceived_color_distance(x, y) / MAX_PERCEIVED_DISTANCE


def euclidean_distance_to_max(x: RGB, y: RGB) -> float:
    return euclidean_color_distance(x, y) / MAX_EUCLIDEAN_DISTANCE


def make_color(rng: np.random.Generator) -> RGB:
    """Make a color from a given seed

    Parameters
    ----------
    rng : np.random.Generator
        The random number generator to use

    Returns
    -------
    RGB
        The color generated from the seed
    """
    colors: tuple[int, ...] = tuple(int(x) for x in rng.integers(low=0, high=256, size=3))
    return RGB(*colors)


def get_colors(seed: int) -> tuple[RGB, RGB]:
    """Get two colors from a seed

    Parameters
    ----------
    seed : int
        The seed to generate the colors from

    Returns
    -------
    tuple[RGB, RGB]
        The two colors generated from the seed
    """
    rng = np.random.default_rng(seed=seed)
    fg = make_color(rng)
    bg = make_color(rng)

    while fg.is_similar(bg):
        bg = make_color(rng)

    return fg, bg


@dataclass(slots=True, frozen=True)
class Identicon:
    """An identicon is a visual representation of a random seed."""

    size: int
    fg: RGB
    bg: RGB
    fg_weight: float
    seed: int

    rng: np.random.Generator = field(default_factory=np.random.default_rng, init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "rng", np.random.default_rng(seed=self.seed))

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

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Identicon) and self.__hash__() == other.__hash__()

    def __hash__(self) -> int:
        return hash(frozenset((self.size, self.fg.as_tuple(), self.bg.as_tuple(), self.fg_weight, self.seed)))


def seed_from_time() -> int:
    """Generate a seed from the current time"""
    return int(str(time.monotonic()).replace(".", ""))


@future_lru_cache(maxsize=20)
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
