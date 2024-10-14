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
    prompt = f"""You are an expert in color theory. Here are the colors you know,
            their hex values, and their names.
            Black,#000000
            Charcoal,#36454F
            Dark Green,#023020
            Dark Purple,#301934
            Jet Black,#343434
            Licorice,#1B1212
            Matte Black,#28282B
            Midnight Blue,#191970
            Onyx,#353935
            Aqua,#00FFFF
            Azure,#F0FFFF
            Baby Blue,#89CFF0
            Blue,#0000FF
            Blue Gray,#7393B3
            Blue Green,#088F8F
            Bright Blue,#0096FF
            Cadet Blue,#5F9EA0
            Cobalt Blue,#0047AB
            Cornflower Blue,#6495ED
            Cyan,#00FFFF
            Dark Blue,#00008B
            Denim,#6F8FAF
            Egyptian Blue,#1434A4
            Electric Blue,#7DF9FF
            Glaucous,#6082B6
            Jade,#00A36C
            Indigo,#3F00FF
            Iris,#5D3FD3
            Light Blue,#ADD8E6
            Midnight Blue,#191970
            Navy Blue,#000080
            Neon Blue,#1F51FF
            Pastel Blue,#A7C7E7
            Periwinkle,#CCCCFF
            Powder Blue,#B6D0E2
            Robin Egg Blue,#96DED1
            Royal Blue,#4169E1
            Sapphire Blue,#0F52BA
            Seafoam Green,#9FE2BF
            Sky Blue,#87CEEB
            Steel Blue,#4682B4
            Teal,#008080
            Turquoise,#40E0D0
            Ultramarine,#0437F2
            Verdigris,#40B5AD
            Zaffre,#0818A8
            Almond,#EADDCA
            Brass,#E1C16E
            Bronze,#CD7F32
            Brown,#A52A2A
            Buff,#DAA06D
            Burgundy,#800020
            Burnt Sienna,#E97451
            Burnt Umber,#6E260E
            Camel,#C19A6B
            Chestnut,#954535
            Chocolate,#7B3F00
            Cinnamon,#D27D2D
            Coffee,#6F4E37
            Cognac,#834333
            Copper,#B87333
            Cordovan,#814141
            Dark Brown,#5C4033
            Dark Red,#8B0000
            Dark Tan,#988558
            Ecru,#C2B280
            Fallow,#C19A6B
            Fawn,#E5AA70
            Garnet,#9A2A2A
            Golden Brown,#966919
            Khaki,#F0E68C
            Light Brown,#C4A484
            Mahogany,#C04000
            Maroon,#800000
            Mocha,#967969
            Nude,#F2D2BD
            Ochre,#CC7722
            Olive Green,#808000
            Oxblood,#4A0404
            Puce,#A95C68
            Red Brown,#A52A2A
            Red Ochre,#913831
            Russet,#80461B
            Saddle Brown,#8B4513
            Sand,#C2B280
            Sienna,#A0522D
            Tan,#D2B48C
            Taupe,#483C32
            Tuscan Red,#7C3030
            Wheat,#F5DEB3
            Wine,#722F37
            Ash Gray,#B2BEB5
            Blue Gray,#7393B3
            Charcoal,#36454F
            Dark Gray,#A9A9A9
            Glaucous,#6082B6
            Gray,#808080
            Gunmetal Gray,#818589
            Light Gray,#D3D3D3
            Pewter,#899499
            Platinum,#E5E4E2
            Sage Green,#8A9A5B
            Silver,#C0C0C0
            Slate Gray,#708090
            Smoke,#848884
            Steel Gray,#71797E
            Aqua,#00FFFF
            Aquamarine,#7FFFD4
            Army Green,#454B1B
            Blue Green,#088F8F
            Bright Green,#AAFF00
            Cadet Blue,#5F9EA0
            Cadmium Green,#097969
            Celadon,#AFE1AF
            Chartreuse,#DFFF00
            Citrine,#E4D00A
            Cyan,#00FFFF
            Dark Green,#023020
            Electric Blue,#7DF9FF
            Emerald Green,#50C878
            Eucalyptus,#5F8575
            Fern Green,#4F7942
            Forest Green,#228B22
            Grass Green,#7CFC00
            Green,#008000
            Hunter Green,#355E3B
            Jade,#00A36C
            Jungle Green,#2AAA8A
            Kelly Green,#4CBB17
            Light Green,#90EE90
            Lime Green,#32CD32
            Lincoln Green,#478778
            Malachite,#0BDA51
            Mint Green,#98FB98
            Moss Green,#8A9A5B
            Neon Green,#0FFF50
            Nyanza,#ECFFDC
            Olive Green,#808000
            Pastel Green,#C1E1C1
            Pear,#C9CC3F
            Peridot,#B4C424
            Pistachio,#93C572
            Robin Egg Blue,#96DED1
            Sage Green,#8A9A5B
            Sea Green,#2E8B57
            Seafoam Green,#9FE2BF
            Shamrock Green,#009E60
            Spring Green,#00FF7F
            Teal,#008080
            Turquoise,#40E0D0
            Vegas Gold,#C4B454
            Verdigris,#40B5AD
            Viridian,#40826D
            Amber,#FFBF00
            Apricot,#FBCEB1
            Bisque,#F2D2BD
            Bright Orange,#FFAC1C
            Bronze,#CD7F32
            Buff,#DAA06D
            Burnt Orange,#CC5500
            Burnt Sienna,#E97451
            Butterscotch,#E3963E
            Cadmium Orange,#F28C28
            Cinnamon,#D27D2D
            Copper,#B87333
            Coral,#FF7F50
            Coral Pink,#F88379
            Dark Orange,#8B4000
            Desert,#FAD5A5
            Gamboge,#E49B0F
            Golden Yellow,#FFC000
            Goldenrod,#DAA520
            Light Orange,#FFD580
            Mahogany,#C04000
            Mango,#F4BB44
            Navajo White,#FFDEAD
            Neon Orange,#FF5F1F
            Ochre,#CC7722
            Orange,#FFA500
            Pastel Orange,#FAC898
            Peach,#FFE5B4
            Persimmon,#EC5800
            Pink Orange,#F89880
            Poppy,#E35335
            Pumpkin Orange,#FF7518
            Red Orange,#FF4433
            Safety Orange,#FF5F15
            Salmon,#FA8072
            Seashell,#FFF5EE
            Sienna,#A0522D
            Sunset Orange,#FA5F55
            Tangerine,#F08000
            Terra Cotta,#E3735E
            Yellow Orange,#FFAA33
            Amaranth,#9F2B68
            Bisque,#F2D2BD
            Cerise,#DE3163
            Claret,#811331
            Coral,#FF7F50
            Coral Pink,#F88379
            Crimson,#DC143C
            Dark Pink,#AA336A
            Fuchsia,#FF00FF
            Hot Pink,#FF69B4
            Light Pink,#FFB6C1
            Magenta,#FF00FF
            Millennial Pink,#F3CFC6
            Mulberry,#770737
            Neon Pink,#FF10F0
            Orchid,#DA70D6
            Pastel Pink,#F8C8DC
            Pastel Red,#FAA0A0
            Pink,#FFC0CB
            Pink Orange,#F89880
            Plum,#673147
            Puce,#A95C68
            Purple,#800080
            Raspberry,#E30B5C
            Red Purple,#953553
            Rose,#F33A6A
            Rose Gold,#E0BFB8
            Rose Red,#C21E56
            Ruby Red,#E0115F
            Salmon,#FA8072
            Seashell,#FFF5EE
            Thistle,#D8BFD8
            Watermelon Pink,#E37383
            Amaranth,#9F2B68
            Bright Purple,#BF40BF
            Burgundy,#800020
            Byzantium,#702963
            Dark Pink,#AA336A
            Dark Purple,#301934
            Eggplant,#483248
            Iris,#5D3FD3
            Lavender,#E6E6FA
            Light Purple,#CBC3E3
            Light Violet,#CF9FFF
            Lilac,#AA98A9
            Mauve,#E0B0FF
            Mauve Taupe,#915F6D
            Mulberry,#770737
            Orchid,#DA70D6
            Pastel Purple,#C3B1E1
            Periwinkle,#CCCCFF
            Plum,#673147
            Puce,#A95C68
            Purple,#800080
            Quartz,#51414F
            Red Purple,#953553
            Thistle,#D8BFD8
            Tyrian Purple,#630330
            Violet,#7F00FF
            Wine,#722F37
            Wisteria,#BDB5D5
            Blood Red,#880808
            Brick Red,#AA4A44
            Bright Red,#EE4B2B
            Brown,#A52A2A
            Burgundy,#800020
            Burnt Umber,#6E260E
            Burnt Orange,#CC5500
            Burnt Sienna,#E97451
            Byzantium,#702963
            Cadmium Red,#D22B2B
            Cardinal Red,#C41E3A
            Carmine,#D70040
            Cerise,#DE3163
            Cherry,#D2042D
            Chestnut,#954535
            Claret,#811331
            Coral Pink,#F88379
            Cordovan,#814141
            Crimson,#DC143C
            Dark Red,#8B0000
            Falu Red,#7B1818
            Garnet,#9A2A2A
            Mahogany,#C04000
            Maroon,#800000
            Marsala,#986868
            Mulberry,#770737
            Neon Red,#FF3131
            Oxblood,#4A0404
            Pastel Red,#FAA0A0
            Persimmon,#EC5800
            Poppy,#E35335
            Puce,#A95C68
            Raspberry,#E30B5C
            Red,#FF0000
            Red Brown,#A52A2A
            Red Ochre,#913831
            Red Orange,#FF4433
            Red Purple,#953553
            Rose Red,#C21E56
            Ruby Red,#E0115F
            Russet,#80461B
            Salmon,#FA8072
            Scarlet,#FF2400
            Sunset Orange,#FA5F55
            Terra Cotta,#E3735E
            Tuscan Red,#7C3030
            Tyrian Purple,#630330
            Venetian Red,#A42A04
            Vermillion,#E34234
            Wine,#722F37
            Alabaster,#EDEADE
            Beige,#F5F5DC
            Bone White,#F9F6EE
            Cornsilk,#FFF8DC
            Cream,#FFFDD0
            Eggshell,#F0EAD6
            Ivory,#FFFFF0
            Linen,#E9DCC9
            Navajo White,#FFDEAD
            Off White,#FAF9F6
            Parchment,#FCF5E5
            Peach,#FFE5B4
            Pearl,#E2DFD2
            Seashell,#FFF5EE
            Vanilla,#F3E5AB
            White,#FFFFFF
            Almond,#EADDCA
            Amber,#FFBF00
            Apricot,#FBCEB1
            Beige,#F5F5DC
            Brass,#E1C16E
            Bright Yellow,#FFEA00
            Cadmium Yellow,#FDDA0D
            Canary Yellow,#FFFF8F
            Chartreuse,#DFFF00
            Citrine,#E4D00A
            Cornsilk,#FFF8DC
            Cream,#FFFDD0
            Dark Yellow,#8B8000
            Desert,#FAD5A5
            Ecru,#C2B280
            Flax,#EEDC82
            Gamboge,#E49B0F
            Gold,#FFD700
            Golden Yellow,#FFC000
            Goldenrod,#DAA520
            Icterine,#FCF55F
            Ivory,#FFFFF0
            Jasmine,#F8DE7E
            Khaki,#F0E68C
            Lemon Yellow,#FAFA33
            Maize,#FBEC5D
            Mango,#F4BB44
            Mustard Yellow,#FFDB58
            Naples Yellow,#FADA5E
            Navajo White,#FFDEAD
            Nyanza,#ECFFDC
            Pastel Yellow,#FFFAA0
            Peach,#FFE5B4
            Pear,#C9CC3F
            Peridot,#B4C424
            Pistachio,#93C572
            Saffron,#F4C430
            Vanilla,#F3E5AB
            Vegas Gold,#C4B454
            Wheat,#F5DEB3
            Yellow,#FFFF00
            Yellow Orange,#FFAA33

            Using this information, look at the following color palette and write
            TWO words to describe the feeling/aura of the color palette.
            Be funny and creative.

            EXTREMELY IMPORTANT RULES:
            1. Use EXACTLY TWO words, no more, no less.
            2. DO NOT use ANY punctuation.
            3. DO NOT use conjunctions like "and" or "or".
            4. DO NOT use articles like "the" or "a".
            5. The first word MUST be a descriptor for the second word.
            6. DO NOT use ANY of these words: dusty vibes aura palette and or

            EXAMPLES OF CORRECT RESPONSES:
            - spicy popsicle
            - melancholy rainbow
            - electric marshmallow
            - whimsical concrete

            EXAMPLES OF INCORRECT RESPONSES:
            - Bold and mysterious (uses "and")
            - The vibrant palette (uses "the" and "palette")
            - Muted, calm (uses punctuation)
            - Aura vibes (uses prohibited words)

            Color palette: {', '.join(rgb_to_hex(*color) for color in palette)}

            Your response MUST follow ALL the EXTREMELY IMPORTANT RULES above.
            Do not include any additional text, explanation, or punctuation.
            Only provide the two-word response:"""

    async with session.post(
        "http://localhost:11434/api/generate", json={"model": "llava", "prompt": prompt, "stream": False}
    ) as response:
        result = await response.json()

    # Post-process the response
    raw_response = result["response"]
    log.debug("Raw response: %s", raw_response)

    # Remove any punctuation and extra whitespace
    cleaned_response = re.sub(r"[^\w\s]", "", raw_response).strip()

    return cleaned_response.lower()


@async_cache(ttl=3600)
async def get_aura(image: bytes, session: aiohttp.ClientSession) -> tuple[float, str]:
    palette = await extract_colors(image)
    harmony_score = get_harmony_score(palette)

    description = await get_palette_description(palette, session)

    return harmony_score, description
