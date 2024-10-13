from __future__ import annotations

import hashlib
import time
from io import BytesIO
from typing import cast

import discord
import numpy as np
from numpy.typing import NDArray
from PIL import Image

from dynamo.utils.cache import async_cache
from dynamo.utils.wrappers import executor_function

# 0.0 = same color | 1.0 = different color
COLOR_THRESHOLD = 0.4

# Maximum distances (derived from distance between black and white)
MAX_PERCEIVED_DISTANCE = 764.83
MAX_EUCLIDEAN_DISTANCE = 441.67

type RGB = tuple[int, int, int]


def derive_seed(precursor: str | int) -> int:
    """Generate a seed from a string or int"""
    encoded_precursor = str(precursor).encode()
    hashed = hashlib.sha256(encoded_precursor).digest()
    return int.from_bytes(hashed[:8], byteorder="big", signed=False)


def clamp_rgb(r: int, g: int, b: int) -> RGB:
    return cast(RGB, tuple(min(max(x, 0), 255) for x in (r, g, b)))


def rgb_difference(color_a: RGB, color_b: RGB) -> RGB:
    return cast(RGB, tuple(a - b for a, b in zip(color_a, color_b, strict=False)))


def color_is_similar(color_a: RGB, color_b: RGB, epsilon: float = 1e-4) -> bool:
    similar_perceived = perceived_distance(color_a, color_b) <= COLOR_THRESHOLD + epsilon
    similar_euclidean = euclidean_distance(color_a, color_b) <= COLOR_THRESHOLD + epsilon
    return similar_perceived and similar_euclidean


def euclidean_distance(color_a: RGB, color_b: RGB) -> float:
    """Gets the euclidean distance between two colors"""
    distance = (sum(x * x for x in rgb_difference(color_a, color_b))) ** 0.5
    return distance / MAX_EUCLIDEAN_DISTANCE


def perceived_distance(color_a: RGB, color_b: RGB) -> float:
    """Gets the perceived distance between two colors

    See
    ---
        https://www.compuphase.com/cmetric.htm

    Note
    ----
    Equation in this func is equivalent to:
        `ΔC = √((2 + r̄/256) * ΔR² + 4 * ΔG² + (2 + (255 - r̄)/256) * ΔB²)`
    """
    r_mean = (color_a[0] + color_b[0]) >> 1
    r, g, b = rgb_difference(color_a, color_b)
    distance = ((((512 + r_mean) * r * r) >> 8) + 4 * g * g + (((767 - r_mean) * b * b) >> 8)) ** 0.5
    return distance / MAX_PERCEIVED_DISTANCE


def as_discord_color(color: RGB) -> discord.Color:
    return discord.Color.from_rgb(*color)


def make_color(rng: np.random.Generator) -> RGB:
    return cast(RGB, tuple(map(int, rng.integers(low=0, high=256, size=3, dtype=int))))


def get_colors(seed: int) -> tuple[RGB, RGB]:
    """Get two colors from a seed"""
    rng = np.random.default_rng(seed=seed)
    fg, bg = make_color(rng), make_color(rng)

    while color_is_similar(fg, bg):
        bg = make_color(rng)

    return fg, bg


def make_identicon(seed: int, pattern_size: int = 6, fg_weight: float = 0.6) -> NDArray[np.int_]:
    """Make an identicon from a seed"""
    rng = np.random.default_rng(seed=seed)
    fg, bg = get_colors(seed)
    pattern = rng.choice([fg, bg], size=(pattern_size * 2, pattern_size), p=[fg_weight, 1 - fg_weight])
    return np.hstack((pattern, np.fliplr(pattern)))


def seed_from_time() -> int:
    """Generate a seed from the current time"""
    return int(str(time.monotonic()).replace(".", ""))


IDENTICON_SIZE = 256


@async_cache
@executor_function
def get_identicon(seed: int, pattern_size: int, fg_weight: float) -> bytes:
    """|coro|

    Get an identicon as bytes
    """

    buffer = BytesIO()
    image = (
        Image.fromarray(make_identicon(seed, pattern_size, fg_weight).astype("uint8"))
        .convert("RGB")
        .resize((IDENTICON_SIZE, IDENTICON_SIZE), Image.Resampling.NEAREST)
    )
    image.save(buffer, format="png")
    buffer.seek(0)
    return buffer.getvalue()
