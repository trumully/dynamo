from io import BytesIO
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.app_commands import Range
from discord.app_commands.transformers import Transform

import dynamo.utils.identicon as idt
from dynamo.bot import Interaction
from dynamo.types import BotExports
from dynamo.utils.color import RGB
from dynamo.utils.transformer import StringMemberTransformer

type Seed = discord.User | discord.Member | str | int


def _clean_seed(seed: Seed) -> str | int:
    if isinstance(seed, discord.User | discord.Member):
        return seed.id

    if str(seed).isdigit():
        return int(seed)

    if (parsed := urlparse(str(seed))) and parsed.netloc:
        return (parsed.netloc + parsed.path).replace("/", "-")

    return seed


async def _generate_identicon(seed: Seed, pattern_size: int, weight: float) -> tuple[discord.Embed, discord.File]:
    clean_seed = _clean_seed(seed)

    name = seed.display_name if isinstance(seed, discord.Member | discord.User) else clean_seed
    derived_seed = idt.derive_seed(clean_seed)

    identicon: bytes = await idt.get_identicon(derived_seed, pattern_size, weight)
    file = discord.File(BytesIO(identicon), filename="identicon.png")
    primary, secondary = idt.get_colors(derived_seed)

    p_hex, s_hex = RGB.as_hex(*primary), RGB.as_hex(*secondary)
    description = f"Pattern size: {pattern_size}\nSecondary color weight: {weight:.2f}\nColors: `{p_hex}` | `{s_hex}`"
    embed = discord.Embed(title=name, description=description, color=primary.as_discord_color())
    embed.set_image(url="attachment://identicon.png")
    return embed, file


@app_commands.command(name="identicon")
@app_commands.describe(
    seed="The seed to generate an identicon for",
    pattern_size="The size of the pattern to generate",
    secondary_color_weight="The weight of the secondary color",
    ephemeral="Attempt to send output as an ephemeral/temporary response",
)
async def get_identicon(
    itx: Interaction,
    seed: Transform[discord.Member | discord.User | str, StringMemberTransformer] | None = None,
    pattern_size: Range[int, 1, 32] = 6,
    secondary_color_weight: Range[float, 0, 1] = 0.6,
    ephemeral: bool = False,  # noqa: FBT001 FBT002
) -> None:
    """Get an identicon generated with a seed."""
    final_seed = seed or itx.id

    embed, file = await _generate_identicon(final_seed, pattern_size, secondary_color_weight)
    await itx.response.send_message(embed=embed, file=file, ephemeral=ephemeral)


@app_commands.context_menu(name="Identicon")
async def identicon_context_menu(itx: Interaction, user: discord.Member | discord.User) -> None:
    embed, file = await _generate_identicon(user, 6, 0.6)
    await itx.response.send_message(embed=embed, file=file, ephemeral=True)


exports = BotExports(
    commands=[get_identicon, identicon_context_menu],
)
