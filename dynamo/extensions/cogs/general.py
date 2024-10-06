from io import BytesIO
from typing import cast
from urllib.parse import urlparse

import discord
from discord.ext import commands

from dynamo._types import MISSING
from dynamo.core import Cog, Dynamo
from dynamo.utils import spotify
from dynamo.utils.context import Context
from dynamo.utils.converter import MemberLikeConverter
from dynamo.utils.identicon import derive_seed, get_colors, get_identicon, seed_from_time


class General(Cog):
    """Generic commands"""

    async def generate_identicon(
        self, seed: discord.Member | str | int, guild: discord.Guild | None
    ) -> tuple[discord.Embed, discord.File]:
        """|coro|

        Generate an identicon from a seed

        Parameters
        ----------
        seed : discord.Member | str | int
            The seed to use
        guild : discord.Guild | None
            The contextual guild

        Returns
        -------
        tuple[discord.Embed, discord.File]
            The embed and file to send
        """
        seed_to_use: discord.Member | str | int = seed
        if isinstance(seed_to_use, str) and (parsed := urlparse(seed_to_use)).scheme and parsed.netloc:
            seed_to_use = (parsed.netloc + parsed.path).replace("/", "-")

        name = seed_to_use if (isinstance(seed_to_use, str | int)) else seed_to_use.display_name

        seed_to_use = derive_seed(name)

        identicon: bytes = await get_identicon(seed_to_use)
        file = discord.File(BytesIO(identicon), filename="identicon.png")
        fg, _ = get_colors(seed_to_use)

        cmd_mention = await self.bot.tree.find_mention_for("identicon", guild=guild)
        prefix = "d!" if guild is None else self.bot.prefixes.get(guild.id, ["d!", "d?"])[0]
        description = f"**Generate this identicon:**\n" f"> {cmd_mention} {name}\n" f"> {prefix}identicon {name}"
        e = discord.Embed(title=name, description=description, color=fg.as_discord_color())
        e.set_image(url="attachment://identicon.png")
        return e, file

    @commands.hybrid_command(name="identicon", aliases=("i", "idt"))
    async def identicon(
        self,
        ctx: Context,
        seed: discord.Member | str | int = commands.param(default=MISSING, converter=MemberLikeConverter),
    ) -> None:
        """Generate an identicon from a user or string

        Parameters
        ----------
        seed: discord.Member | str | int, optional
            The seed to use. Random seed if empty.
        """
        embed, file = await self.generate_identicon(seed_from_time() if seed is MISSING else seed, ctx.guild)
        await ctx.send(embed=embed, file=file)

    @commands.hybrid_command(name="spotify", aliases=("sp", "applemusic"))
    async def spotify(
        self,
        ctx: Context,
        user: discord.User | discord.Member | None = commands.param(default=None, converter=MemberLikeConverter),
    ) -> None:
        """Get the currently playing Spotify track for a user.

        Parameters
        ----------
        user : discord.User |discord.Member | None, optional
            The user to check. If nothing is provided, check author instead.
        """
        if user is None:
            user = ctx.author

        if user.bot:
            return

        activities = cast(discord.Member, user).activities
        activity: discord.Spotify | None = next((a for a in activities if isinstance(a, discord.Spotify)), None)

        if activity is None:
            await ctx.send(f"{user!s} is not listening to Spotify.")
            return

        album_cover: bytes | None = await spotify.fetch_album_cover(activity.album_cover_url, self.bot.session)
        if album_cover is None:
            await ctx.send("Failed to fetch album cover.")
            return

        buffer, ext = await spotify.draw(activity, album_cover)
        embed, file = spotify.make_embed(user, activity, buffer, self.bot.app_emojis.get("spotify", "🎧"), ext=ext)

        await ctx.send(embed=embed, file=file)


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(General(bot))


async def teardown(bot: Dynamo) -> None:
    await bot.remove_cog(General.__name__)
