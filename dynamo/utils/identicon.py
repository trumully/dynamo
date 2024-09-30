from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from io import BytesIO

import discord
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from dynamo.utils.cache import async_cache

# 0.0 = same color | 1.0 = different color
COLOR_THRESHOLD = 0.4


def derive_seed(precursor: str | int) -> int:
    """Generate a seed from a string or int"""
    encoded_precursor = str(precursor).encode()
    hashed = int.from_bytes(encoded_precursor + hashlib.sha256(encoded_precursor).digest(), byteorder="big")
    return hashed  # noqa: RET504  needs to be assigned as a var to work properly


# Maximum distances (derived from distance between black and white)
MAX_PERCEIVED_DISTANCE = 764.83
MAX_EUCLIDEAN_DISTANCE = 441.67


@dataclass(slots=True)
class RGB:
    r: int
    g: int
    b: int

    def __post_init__(self) -> None:
        self.r, self.g, self.b = (max(0, min(x, 255)) for x in (self.r, self.g, self.b))

    def difference(self, other: RGB) -> tuple[int, int, int]:
        return (self.r - other.r, self.g - other.g, self.b - other.b)

    def is_similar(self, other: RGB) -> bool:
        return self.perceived_distance(other) <= COLOR_THRESHOLD and self.euclidean_distance(other) <= COLOR_THRESHOLD

    def euclidean_distance(self, other: RGB) -> float:
        """Gets the euclidean distance between two colors"""
        r, g, b = self.difference(other)
        distance = ((r * r) + (g * g) + (b * b)) ** 0.5
        return distance / MAX_EUCLIDEAN_DISTANCE

    def perceived_distance(self, other: RGB) -> float:
        """Gets the perceived distance between two colors

        See
        ---
        - https://www.compuphase.com/cmetric.htm
        """
        r_mean = (self.r + other.r) >> 1
        r, g, b = self.difference(other)
        # ΔC = √((2 + r̄/256) * ΔR² + 4 * ΔG² + (2 + (255 - r̄)/256) * ΔB²)
        distance = ((((512 + r_mean) * r * r) >> 8) + 4 * g * g + (((767 - r_mean) * b * b) >> 8)) ** 0.5
        return distance / MAX_PERCEIVED_DISTANCE

    def as_tuple(self) -> tuple[int, int, int]:
        return self.r, self.g, self.b

    def as_discord_color(self) -> discord.Color:
        return discord.Color.from_rgb(*self.as_tuple())


def make_color(rng: np.random.Generator) -> RGB:
    return RGB(*map(int, rng.integers(low=0, high=256, size=3, dtype=int)))


def get_colors(seed: int) -> tuple[RGB, RGB]:
    """Get two colors from a seed"""
    rng = np.random.default_rng(seed=seed)
    fg, bg = make_color(rng), make_color(rng)

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

    @property
    def icon(self) -> NDArray[np.int_]:
        rng = np.random.default_rng(seed=self.seed)
        pattern = rng.choice(
            [self.fg.as_tuple(), self.bg.as_tuple()],
            size=(self.size * 2, self.size),
            p=[self.fg_weight, 1 - self.fg_weight],
        )
        return np.hstack((pattern, np.fliplr(pattern)))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Identicon) and hash(self) == hash(other)

    def __hash__(self) -> int:
        return hash(frozenset((self.size, self.fg.as_tuple(), self.bg.as_tuple(), self.fg_weight, self.seed)))


def seed_from_time() -> int:
    """Generate a seed from the current time"""
    return int(str(time.monotonic()).replace(".", ""))


@async_cache
async def get_identicon(idt: Identicon, size: int = 256) -> bytes:
    """|coro|

    Get an identicon as bytes
    """

    def _buffer(idt: Identicon, size: int) -> bytes:
        buffer = BytesIO()
        Image.fromarray(idt.icon.astype("uint8")).convert("RGB").resize((size, size), Image.Resampling.NEAREST).save(
            buffer, format="png"
        )
        buffer.seek(0)
        return buffer.getvalue()

    result: bytes = await asyncio.to_thread(_buffer, idt, size)
    return result
