import itertools
import logging
import operator
import re

import aiohttp
import numpy as np
from dynamo_utils.task_cache import lru_task_cache

from dynamo.utils.color import RGB, color_palette_from_image, filter_similar_colors

log = logging.getLogger(__name__)


def get_harmony_score(colors: list[tuple[RGB, float]]) -> float:
    """Calculate aesthetic score based on pleasing color relationships and color harmony."""
    if len(colors) < 2:  # noqa: PLR2004
        return 5.0

    rgb_colors, prominences = zip(*colors, strict=False)

    def detect_color_theme() -> float:
        """Detect if colors follow a specific harmony pattern."""
        # Convert colors to HSV for easier theme detection
        hsv_colors = list(itertools.starmap(RGB.as_hsv, rgb_colors))

        # Check for common color schemes
        scores: list[tuple[str, float]] = []

        # Monochromatic: similar hue, varying saturation/value
        hue_variance: float = float(np.std([h for h, *_ in hsv_colors]))
        hue_diffs = [
            abs(hsv_colors[i][0] - hsv_colors[j][0])
            for i, j in itertools.combinations(range(len(hsv_colors)), 2)
        ]
        scores.extend([
            ("monochromatic", 1.0 - min(hue_variance / 30, 1.0)),
            ("analogous", sum(1.0 for diff in hue_diffs if diff <= 30) / len(hue_diffs)),  # noqa: PLR2004
            (
                "complementary",
                sum(1.0 for diff in hue_diffs if 150 <= diff <= 210) / len(hue_diffs),  # noqa: PLR2004
            ),
            (
                "split-complementary",
                sum(
                    1.0
                    for diff in hue_diffs
                    if 150 <= diff <= 210 or 120 <= diff <= 150 or 210 <= diff <= 240  # noqa: PLR2004
                )
                / len(hue_diffs),
            ),
            (
                "triadic",
                sum(1.0 for diff in hue_diffs if 105 <= diff <= 135) / len(hue_diffs),  # noqa: PLR2004
            ),
        ])

        # Get the best matching theme and its score
        best_theme, best_score = max(scores, key=operator.itemgetter(1))
        log.debug("Color theme detected: %s (score: %.2f)", best_theme, best_score)

        return best_score

    # Calculate base metrics
    all_pairs: list[tuple[tuple[int, RGB], tuple[int, RGB]]] = list(
        itertools.combinations(enumerate(rgb_colors), 2)  # type: ignore[reportUnknownArgumentType]
    )
    distances: list[float] = []
    weights: list[float] = []

    for (i1, c1), (i2, c2) in all_pairs:
        distances.append(c1.perceived_distance_from(c2))
        weights.append(prominences[i1] * prominences[i2])

    avg_distance = sum(d * w for d, w in zip(distances, weights, strict=False)) / sum(
        weights
    )

    # Calculate component scores
    visual_interest = min(len(colors) / 4, 1.0)  # Ideal: 3-4 distinct colors
    contrast_score = min(avg_distance * 1.2, 1.0)  # Clear distinction between colors

    # Balance scoring
    balance_score = 1.0 - min(np.std(prominences) * 2, 0.8)  # type: ignore[reportArgumentType]

    # Dominant color impact
    focal_score = min(max(prominences) * 1.5, 1.0)

    # Theme coherence
    theme_score = detect_color_theme()

    # Combined scoring with theme consideration
    combined_score = (
        visual_interest * 0.2  # Multiple distinct colors
        + contrast_score * 0.2  # Clear color separation
        + balance_score * 0.2  # Good distribution
        + focal_score * 0.15  # Strong focal point
        + theme_score * 0.25  # Color theme coherence
    ) * 10

    log.debug(
        "Colors: %d | Interest: %.2f | Contrast: %.2f | Balance: %.2f | Focal: %.2f | Theme: %.2f | Combined: %.2f",
        len(colors),
        visual_interest,
        contrast_score,
        balance_score,
        focal_score,
        theme_score,
        combined_score,
    )

    return float(max(1, min(10, round(combined_score, 1))))


async def extract_colors(image: bytes) -> list[tuple[RGB, float]]:
    palette = await color_palette_from_image(image)
    return filter_similar_colors(palette)


async def get_palette_description(
    palette: list[tuple[RGB, float]], session: aiohttp.ClientSession
) -> str:
    sorted_palette = sorted(palette, key=operator.itemgetter(1), reverse=True)
    color_info = [
        f"{RGB.as_hex(*color)} ({prominence:.1%})"
        for color, prominence in sorted_palette[:6]  # Show top 6 colors
    ]

    # Calculate primary color relationships
    dominant_color = sorted_palette[0][0]
    secondary_color = sorted_palette[1][0]
    tertiary_color = sorted_palette[2][0] if len(sorted_palette) > 2 else None  # noqa: PLR2004

    prompt = f"""You are an expert in color theory.
    Analyze this hex color palette and generate a brief, evocative description that captures its emotional impact.

    [COLOR PALETTE INFORMATION]
    Color Distribution (hex, prominence):
    - Dominant: {color_info[0]}
    - Secondary: {color_info[1]}
    - Supporting: {", ".join(color_info[2:])}

    Color Relationship Analysis:
    - Primary Contrast: {dominant_color.perceived_distance_from(secondary_color):.2f}
    {f"- Secondary Contrast: {secondary_color.perceived_distance_from(tertiary_color):.2f}" if tertiary_color else ""}

    Complex Color Combinations:
    - Triadic combinations suggest balance and richness
    - Split-complementary suggests dynamic tension with harmony
    - Double complementary suggests high energy and complexity
    - Analogous groups with an accent suggest focused energy
    - Multiple saturated colors with varying prominence suggest depth

    [OUTPUT RULES]
    1. OUTPUT FORMAT: [quality] [dynamic] [essence]
        - quality: strong emotional or sensory adjective
        - dynamic: active or flowing word (tensions, echoes, whispers, pulses)
        - essence: core emotional or atmospheric impact
    2. TOTAL LENGTH: exactly 3 words
    3. FORMATTING: all lowercase, no punctuation
    4. WORD CHOICE:
        - Use unexpected but fitting emotional descriptors
        - Avoid cliché or obvious terms
        - Consider the overall mood created by color relationships
        - Draw from any emotional or sensory experience
        - Be creative but authentic to the palette's feeling

    [VALID EXAMPLES]
    untamed storm beckons
    silent thunder awakens
    feral dreams unfold
    velvet shadows dance
    starlit secrets whisper

    [INVALID EXAMPLES]
    soft and gentle (wrong format)
    the mystic garden (wrong format)
    flowing (too short)
    dramatically intense power (too long)
    bold dynamic energy (too generic)

    Respond with exactly three evocative words following the format above:"""

    async with session.post(
        "http://localhost:11434/api/generate",
        json={"model": "mistral", "prompt": prompt, "stream": False},
    ) as response:
        result = await response.json()

    raw_response = result["response"]
    return re.sub(r"[^\w\s]", "", raw_response).strip().lower()


@lru_task_cache(maxsize=128, ttl=3600)
async def get_aura(
    avatar: bytes, banner: bytes | None, session: aiohttp.ClientSession
) -> tuple[float, str]:
    """Analyze the aura of a user's avatar and banner."""
    # Extract colors with prominence
    avatar_colors = await color_palette_from_image(avatar, iterations=100)
    log.debug("Initial avatar colors: %d", len(avatar_colors))

    if banner:
        banner_colors = await color_palette_from_image(banner, iterations=100)
        log.debug("Initial banner colors: %d", len(banner_colors))
        # Weight banner colors less than avatar colors
        banner_colors = [(color, prominence * 0.9) for color, prominence in banner_colors]
        combined_colors = avatar_colors + banner_colors
        palette = filter_similar_colors(combined_colors)
    else:
        palette = filter_similar_colors(avatar_colors)

    log.debug("Final filtered colors: %d", len(palette))
    log.debug(
        "Color prominences: %s",
        [f"{RGB.as_hex(*color)}:{prominence:.2%}" for color, prominence in palette],
    )

    harmony_score = get_harmony_score(palette)
    try:
        description = await get_palette_description(palette, session)
    except aiohttp.ClientConnectionError:
        log.warning("Ollama is not running")
        description = "No description provided"

    return harmony_score, description
