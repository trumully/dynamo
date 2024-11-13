from io import BytesIO
from typing import Literal
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.app_commands import Range
from discord.app_commands.transformers import Transform

import dynamo.utils.identicon as idt
from dynamo.bot import Interaction
from dynamo.types import BotExports
from dynamo.utils.transformer import StringOrMemberTransformer


async def _generate_identicon(
    seed: discord.User | discord.Member | str | int, pattern_size: int, foreground_color_weight: float
) -> tuple[discord.Embed, discord.File]:
    sanitised_seed = seed
    if isinstance(sanitised_seed, str):
        if sanitised_seed.isdigit():
            sanitised_seed = int(sanitised_seed)
        elif (parsed := urlparse(sanitised_seed)) and parsed.netloc:
            sanitised_seed = (parsed.netloc + parsed.path).replace("/", "-")

    name = sanitised_seed if isinstance(sanitised_seed, str | int) else sanitised_seed.display_name
    derived_seed = idt.derive_seed(name)

    identicon: bytes = await idt.get_identicon(derived_seed, pattern_size, foreground_color_weight)
    file = discord.File(BytesIO(identicon), filename="identicon.png")
    foreground, _ = idt.get_colors(derived_seed)

    description = f"Pattern size: {pattern_size}\nForeground color weight: {foreground_color_weight:.2f}"
    embed = discord.Embed(title=name, description=description, color=idt.as_discord_color(foreground))
    embed.set_image(url="attachment://identicon.png")
    return embed, file


@app_commands.command(name="identicon")
@app_commands.describe(
    seed="The seed to generate an identicon for",
    pattern_size="The size of the pattern to generate",
    foreground_color_weight="The weight of the foreground color to generate",
    ephemeral="Attempt to send output as an ephemeral/temporary response",
)
async def get_identicon(
    itx: Interaction,
    seed: Transform[discord.Member | discord.User | str, StringOrMemberTransformer] | None = None,
    pattern_size: Range[int, 1, 32] = 6,
    foreground_color_weight: Range[float, 0, 1] = 0.6,
    ephemeral: Literal["True", "False"] = "False",
) -> None:
    """Get an identicon generated with a seed."""
    final_seed = idt.seed_from_time() if seed is None else seed

    embed, file = await _generate_identicon(final_seed, pattern_size, foreground_color_weight)
    await itx.response.send_message(embed=embed, file=file, ephemeral=ephemeral == "True")


exports = BotExports([get_identicon])
