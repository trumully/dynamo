from collections.abc import Generator
from contextlib import contextmanager
from io import BytesIO
from typing import cast

import numpy as np
from PIL import Image

from dynamo.utils.wrappers import executor_function

# 0.0 = same color | 1.0 = different color
COLOR_THRESHOLD = 0.4

# Maximum distances (derived from distance between black and white)
MAX_PERCEIVED_DISTANCE = 764.83
MAX_EUCLIDEAN_DISTANCE = 441.67

type RGB = tuple[int, int, int]


def rgb_difference(color_a: RGB, color_b: RGB) -> RGB:
    return cast(RGB, tuple(a - b for a, b in zip(color_a, color_b, strict=False)))


def color_is_similar(color_a: RGB, color_b: RGB, *, threshold: float = COLOR_THRESHOLD, epsilon: float = 1e-4) -> bool:
    similar_perceived = perceived_distance(color_a, color_b) <= threshold + epsilon
    similar_euclidean = euclidean_distance(color_a, color_b) <= threshold + epsilon
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


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def hex_to_rgb(hexadecimal: str) -> RGB:
    return cast(RGB, tuple(int(hexadecimal[i : i + 2], 16) for i in (0, 2, 4)))


@contextmanager
def open_image_bytes(image: bytes) -> Generator[Image.Image]:
    buffer = BytesIO(image)
    buffer.seek(0)
    try:
        yield Image.open(buffer).convert("RGB")
    finally:
        buffer.close()


@executor_function
def color_palette_from_image(image: bytes, n: int = 10, *, iterations: int = 100) -> list[RGB]:
    """Extract a color palette from an image using K-means clustering."""
    with open_image_bytes(image) as img:
        img.resize((200, 200))
        pixels = np.array(img).reshape(-1, 3)

    rng = np.random.default_rng(seed=0)
    centroids = pixels[rng.choice(pixels.shape[0], n, replace=False)]

    for _ in range(iterations):
        distances = np.sqrt(((pixels[:, np.newaxis] - centroids) ** 2).sum(axis=2))
        pixel_assignments = np.argmin(distances, axis=1)

        new_centroids = np.array(
            [
                pixels[pixel_assignments == i].mean(axis=0) if np.any(pixel_assignments == i) else centroids[i]
                for i in range(n)
            ]
        )

        if np.allclose(centroids, new_centroids):
            break

        centroids = new_centroids

    return [tuple(centroid.astype(int)) for centroid in centroids]


def filter_similar_colors(palette: list[RGB]) -> list[RGB]:
    """Filter out similar colors from a palette."""
    filtered: list[RGB] = []
    for color in palette:
        if not any(color_is_similar(color, existing, threshold=0.05) for existing in filtered):
            filtered.append(color)
    return filtered[:16]
