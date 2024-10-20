import itertools
import logging
import re

import aiohttp

from dynamo.utils.cache import async_cache
from dynamo.utils.color import RGB, color_palette_from_image, filter_similar_colors, perceived_distance, rgb_to_hex

log = logging.getLogger(__name__)


def get_harmony_score(colors: list[RGB]) -> float:
    if len(colors) < 2:
        return 5.0  # Neutral score for insufficient colors

    all_pairs = list(itertools.combinations(colors, 2))
    distances = [perceived_distance(a, b) for a, b in all_pairs]

    avg_distance = sum(distances) / len(distances)

    # Calculate diversity score based on number of colors
    max_colors = 10  # Assuming this is the maximum we want
    diversity_score = min(len(colors) / max_colors, 1.0)

    # Calculate harmony score based on average distance
    # We want a bell curve where 0.5 is the ideal average distance
    harmony_score = 1 - abs(avg_distance - 0.5) * 2

    # Combine scores
    combined_score = (harmony_score * 0.7 + diversity_score * 0.3) * 10

    log.debug(
        "Colors: %s, Avg Distance: %s, Harmony: %s, Diversity: %s",
        len(colors),
        avg_distance,
        harmony_score,
        diversity_score,
    )

    return max(1, min(10, round(combined_score, 1)))


async def extract_colors(image: bytes) -> list[RGB]:
    palette = await color_palette_from_image(image)
    return filter_similar_colors(palette)


async def get_palette_description(palette: list[RGB], session: aiohttp.ClientSession) -> str:
    prompt = f"""You are an expert in color theory. Analyze the given COLOR PALETTE and generate
        TWO words to encapsulate its essence/mood. Aim for originality and wit in your response.

        [COLOR PALETTE]
        {'\n'.join(rgb_to_hex(*color) for color in palette)}
        [END COLOR PALETTE]

        [MANDATORY GUIDELINES]
        1. Provide EXACTLY TWO words, no deviation allowed.
        2. Structure as: [descriptive adjective] [evocative noun].
        3. Use only lowercase letters.
        4. Exclude ALL punctuation marks.
        5. Omit conjunctions, articles, and prepositions.
        6. Ensure both words are distinct and meaningful.
        7. Avoid these specific words: dusty, vibes, aura, palette, mix, blend, harmony, twilight.
        8. Do not use color names directly (e.g., "blue", "red", etc.).
        9. Focus on the mood, feeling, or association evoked by the colors, not the colors themselves.
        10. If you cannot follow ALL guidelines, respond with "INVALID REQUEST".
        [END MANDATORY GUIDELINES]

        Examples of correct responses:
        - ethereal dreamscape
        - nostalgic reverie
        - bold revelation
        - serene whisper
        - electric pulse

        Examples of incorrect responses:
        - vibrant mix (uses "mix", which is forbidden)
        - the colorful palette (uses article and directly references colors/palette)
        - sunset and ocean (uses conjunction "and")
        - Bright Hues (uses capital letters)
        - energetic (only one word)
        - lively, dynamic atmosphere (more than two words, uses punctuation)

        Adhere strictly to ALL MANDATORY GUIDELINES listed above.
        Provide ONLY the two-word response without any additional text:"""

    async with session.post(
        "http://localhost:11434/api/generate",
        json={"model": "mistral", "prompt": prompt, "stream": False},
    ) as response:
        result = await response.json()

    raw_response = result["response"]
    return re.sub(r"[^\w\s]", "", raw_response).strip().lower()


@async_cache(ttl=3600)
async def get_aura(avatar: bytes, banner: bytes | None, session: aiohttp.ClientSession) -> tuple[float, str]:
    """Analyze the aura of a user's avatar and banner."""
    palette = await extract_colors(avatar)
    if banner:
        palette.extend(await extract_colors(banner))
    palette = filter_similar_colors(palette)

    harmony_score = get_harmony_score(palette)

    description = await get_palette_description(palette, session)

    return harmony_score, description
