from __future__ import annotations

import operator
from contextlib import contextmanager
from io import BytesIO
from typing import TYPE_CHECKING, NamedTuple

import discord
import numpy as np
import numpy.typing as npt
from PIL import Image

from dynamo.utils.wrappers import executor_function

if TYPE_CHECKING:
    from collections.abc import Generator

# 0.0 = same color | 1.0 = different color
COLOR_THRESHOLD = 0.3

# Maximum distances (derived from distance between black and white)
MAX_PERCEIVED_DISTANCE = 764.83
MAX_EUCLIDEAN_DISTANCE = 441.67


class RGB(NamedTuple):
    r: int
    g: int
    b: int

    def is_similar_to(self, other: RGB, *, threshold: float = COLOR_THRESHOLD, epsilon: float = 1e-4) -> bool:
        # Calculate both distance metrics
        p_distance = self.perceived_distance_from(other)
        e_distance = self.euclidean_distance_from(other)

        # Adjust threshold based on color intensity
        intensity_a = sum(self) / 765  # 765 = 255 * 3
        intensity_b = sum(other) / 765
        intensity_diff = abs(intensity_a - intensity_b)

        # Make threshold more permissive for colors with very different intensities
        adjusted_threshold = threshold * (1 + intensity_diff)

        return p_distance <= adjusted_threshold + epsilon and e_distance <= adjusted_threshold + epsilon

    def difference_of(self, other: RGB) -> RGB:
        return RGB(*tuple(a - b for a, b in zip(self, other, strict=False)))

    def perceived_distance_from(self, other: RGB) -> float:
        """Gets the perceived distance between two colors.

        See
        ---
            https://www.compuphase.com/cmetric.htm

        Note:
        ----
        Equation in this func is equivalent to:
            `ΔC = √((2 + r̄/256) * ΔR² + 4 * ΔG² + (2 + (255 - r̄)/256) * ΔB²)`
        """
        r_mean = (self.r + other.r) >> 1
        r, g, b = self.difference_of(other)
        distance: float = ((((512 + r_mean) * r * r) >> 8) + 4 * g * g + (((767 - r_mean) * b * b) >> 8)) ** 0.5
        return distance / MAX_PERCEIVED_DISTANCE

    def euclidean_distance_from(self, other: RGB) -> float:
        distance: float = (sum(x * x for x in self.difference_of(other))) ** 0.5
        return distance / MAX_EUCLIDEAN_DISTANCE

    def as_discord_color(self) -> discord.Color:
        return discord.Color.from_rgb(*self)

    @classmethod
    def as_hex(cls: type[RGB], r: int, g: int, b: int) -> str:
        return f"#{r:02x}{g:02x}{b:02x}"

    @classmethod
    def from_hex(cls: type[RGB], hexadecimal: str) -> RGB:
        return RGB(*tuple(int(hexadecimal[i : i + 2], 16) for i in (0, 2, 4)))

    @classmethod
    def as_hsv(cls: type[RGB], r: int, g: int, b: int) -> tuple[float, float, float]:
        r_: float = r / 255
        g_: float = g / 255
        b_: float = b / 255

        cmax = max(r_, g_, b_)
        cmin = min(r_, g_, b_)
        diff = cmax - cmin

        # Calculate hue
        h: float = 0

        if cmax == r_:
            h = (60 * ((g_ - b_) / diff) + 360) % 360
        elif cmax == g_:
            h = (60 * ((b_ - r_) / diff) + 120) % 360
        else:
            h = (60 * ((r_ - g_) / diff) + 240) % 360

        # Calculate saturation
        s = 0 if cmax == 0 else (diff / cmax) * 100

        # Calculate value
        v = cmax * 100

        return h, s, v


@contextmanager
def open_image_bytes(image: bytes) -> Generator[Image.Image]:
    buffer = BytesIO(image)
    buffer.seek(0)
    try:
        yield Image.open(buffer).convert("RGBA")
    finally:
        buffer.close()


PROMINENCE_THRESHOLD = 0.01
UNCHANGED_COUNT_THRESHOLD = 3
PIXEL_COUNT_THRESHOLD = 10000


@executor_function
def color_palette_from_image(image: bytes, n: int = 20, *, iterations: int = 50) -> list[tuple[RGB, float]]:
    """Extract a color palette from an image using K-means clustering, returning colors and their prominence."""
    with open_image_bytes(image) as img:
        # Convert to RGBA to handle transparency
        img.convert("RGBA").thumbnail((150, 150), Image.Resampling.LANCZOS)
        pixels = np.asarray(img, dtype=np.float32)
        valid_pixels = pixels[pixels[..., 3] > 0, :3]

        if len(valid_pixels) == 0:
            return []  # Return empty list if image is fully transparent

    rng = np.random.default_rng(seed=0)
    if len(valid_pixels) > PIXEL_COUNT_THRESHOLD:
        indices = rng.choice(len(valid_pixels), size=PIXEL_COUNT_THRESHOLD, replace=False)
        valid_pixels = valid_pixels[indices]

    # K-means++ initialization
    centroids = valid_pixels[rng.choice(len(valid_pixels), 1)]
    for _ in range(1, n):
        probabilities = ((valid_pixels[:, np.newaxis] - centroids) ** 2).sum(axis=2).min(axis=1)
        probabilities /= probabilities.sum()
        next_centroid = valid_pixels[rng.choice(len(valid_pixels), 1, p=probabilities)]
        centroids = np.vstack([centroids, next_centroid])

    prev_assignments: npt.ArrayLike = []
    unchanged_count = 0

    for _ in range(iterations):
        pixel_assignments: npt.NDArray[np.int32] = np.argmin(
            ((valid_pixels[:, np.newaxis] - centroids) ** 2).sum(axis=2),
            axis=1,
        )

        if np.array_equal(prev_assignments, pixel_assignments):
            unchanged_count += 1
            if unchanged_count >= UNCHANGED_COUNT_THRESHOLD:
                break
        else:
            unchanged_count = 0

        prev_assignments = pixel_assignments

        for i in range(n):
            mask = pixel_assignments == i
            if np.any(mask):
                centroids[i] = valid_pixels[mask].mean(axis=0)

    # Calculate color prominence
    final_distances = ((valid_pixels[:, np.newaxis] - centroids) ** 2).sum(axis=2)
    final_assignments = np.argmin(final_distances, axis=1)

    color_counts = np.bincount(final_assignments, minlength=n)

    colors_by_prominence = (
        (color, prominence)
        for color, prominence in zip(centroids, color_counts / len(valid_pixels), strict=False)
        if prominence >= PROMINENCE_THRESHOLD
    )

    return [(RGB(*color.astype(int)), float(prominence)) for color, prominence in colors_by_prominence]


MAX_FILTERED = 10


def filter_similar_colors(
    colors: list[tuple[RGB, float]],
    similarity_threshold: float = 0.15,
    min_prominence: float = 0.02,
) -> list[tuple[RGB, float]]:
    """Filter out colors that are too similar to more prominent colors.

    Args:
        colors: List of (RGB, prominence) tuples
        similarity_threshold: Colors closer than this are considered similar (higher = more colors)
        min_prominence: Colors less prominent than this are filtered out
    """
    # Sort by prominence
    sorted_colors = sorted(colors, key=operator.itemgetter(1), reverse=True)
    filtered: list[tuple[RGB, float]] = []

    for color, prominence in sorted_colors:
        if prominence < min_prominence:
            continue

        # Check if this color is too similar to any already-kept colors
        is_unique = True
        for existing_color, _ in filtered:
            if color.perceived_distance_from(existing_color) < similarity_threshold:
                is_unique = False
                break

        if is_unique:
            filtered.append((color, prominence))

        if len(filtered) >= MAX_FILTERED:
            break

    return filtered
