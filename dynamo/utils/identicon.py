from __future__ import annotations

import hashlib
from io import BytesIO
from typing import TYPE_CHECKING

import numpy as np
from dynamo_utils.task_cache import lru_task_cache
from PIL import Image

from dynamo.utils.color import RGB
from dynamo.utils.wrappers import executor_function

if TYPE_CHECKING:
    from numpy.typing import NDArray


def derive_seed(precursor: str | int) -> int:
    """Generate a seed from a string or int."""
    encoded_precursor = str(precursor).encode()
    hashed = hashlib.sha256(encoded_precursor).digest()
    return int.from_bytes(hashed[:8], byteorder="big", signed=False)


def make_color(rng: np.random.Generator) -> RGB:
    return RGB(*tuple(map(int, rng.integers(low=0, high=256, size=3, dtype=int))))


def get_colors(seed: int) -> tuple[RGB, RGB]:
    """Get two colors from a seed."""
    rng = np.random.default_rng(seed=seed)
    primary, secondary = make_color(rng), make_color(rng)

    while primary.is_similar_to(secondary):
        secondary = make_color(rng)

    return primary, secondary


def make_identicon(
    seed: int, pattern_size: int = 6, secondary_weight: float = 0.6
) -> NDArray[np.int32]:
    """Make an identicon from a seed."""
    rng = np.random.default_rng(seed=seed)
    primary, secondary = get_colors(seed)
    pattern = rng.choice(
        [primary, secondary],
        size=(pattern_size * 2, pattern_size),
        p=[secondary_weight, 1 - secondary_weight],
    )
    return np.hstack((pattern, np.fliplr(pattern)))


IDENTICON_SIZE = 256


@lru_task_cache
@executor_function
def get_identicon(seed: int, pattern_size: int, secondary_weight: float) -> bytes:
    """Get an identicon as bytes."""
    buffer = BytesIO()
    image = (
        Image.fromarray(
            make_identicon(seed, pattern_size, secondary_weight).astype("uint8")
        )
        .convert("RGB")
        .resize((IDENTICON_SIZE, IDENTICON_SIZE), Image.Resampling.NEAREST)
    )
    image.save(buffer, format="png")
    buffer.seek(0)
    return buffer.getvalue()
