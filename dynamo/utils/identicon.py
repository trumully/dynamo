from __future__ import annotations

import io
import math
import random
from dataclasses import dataclass, field
from functools import cached_property

import numpy as np
from PIL import Image

# 765 * 0.4
COLOR_THRESHOLD = 306


def color_distance(a: RGB, /, b: RGB) -> float:
    """Measure distance between two colors

    See:
        https://www.compuphase.com/cmetric.htm

    Args:
        a (RGB): The first color
        b (RGB): The second color

    Returns:
        float: The distance between the two colors
    """
    mean = a.red_mean(b)
    diff = a - b

    return math.sqrt((2 + (mean / 256)) * diff.r**2 + 4 * diff.g**2 + (2 + (255 - mean) / 256) * diff.b**2)


def make_color(seed: int) -> RGB:
    random.seed(seed)
    return RGB(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))  # noqa: S311


def get_colors(fg: RGB | None = None, bg: RGB | None = None, *, seed: int) -> tuple[RGB, RGB]:
    fg = fg or make_color(seed)
    bg = bg or make_color(int(str(seed)[::-1]))

    return (fg, bg) if fg != bg else (fg.flip(), bg)


@dataclass
class RGB:
    r: int
    g: int
    b: int

    def __sub__(self, other: RGB) -> RGB:
        return RGB(self.r - other.r, self.g - other.g, self.b - other.b)

    def __eq__(self, other: RGB) -> bool:
        return color_distance(self, other) < COLOR_THRESHOLD

    def red_mean(self, other: RGB) -> int:
        return (self.r + other.r) // 2

    def flip(self) -> RGB:
        return RGB(255 - self.r, 255 - self.g, 255 - self.b)

    def as_tuple(self) -> tuple[int, int, int]:
        return self.r, self.g, self.b


@dataclass
class Identicon:
    size: int
    fg: RGB
    bg: RGB
    fg_weight: float
    seed: int

    rng: np.random.Generator | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(seed=self.seed)

    @cached_property
    def pattern(self) -> np.ndarray:
        colors = np.array((self.fg, self.bg))
        size = (self.size * 2, self.size)
        weight = (self.fg_weight, 1 - self.fg_weight)
        return self.rng.choice(colors, size=size, p=weight)

    @property
    def icon(self) -> np.ndarray:
        return self.reflect(np.array([[c.as_tuple() for c in row] for row in self.pattern]))

    @staticmethod
    def reflect(matrix: np.ndarray) -> np.ndarray:
        return np.hstack((matrix, np.fliplr(matrix)))


def make_identicon(i: Identicon, size: int = 256) -> bytes:
    icon = i.icon

    im = Image.fromarray(icon.astype("uint8"))
    im = im.convert("RGB")
    im = im.resize((size, size), Image.Resampling.NEAREST)

    with io.BytesIO() as buffer:
        im.save(buffer, format="png")
        return buffer.getvalue()
