from io import BytesIO
from typing import cast
from urllib.parse import urlparse

import discord
from discord.ext import commands

from dynamo import Cog, Context, Dynamo
from dynamo.typedefs import MISSING
from dynamo.utils import spotify
from dynamo.utils.converter import MemberLikeConverter
from dynamo.utils.identicon import as_discord_color, derive_seed, get_colors, get_identicon, seed_from_time


class General(Cog, name="general"):
    """Generic commands"""

    async def generate_identicon(
        self, seed: discord.Member | str | int, pattern_size: int, fg_weight: float, guild: discord.Guild | None
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

        identicon: bytes = await get_identicon(seed_to_use, pattern_size, fg_weight)
        file = discord.File(BytesIO(identicon), filename="identicon.png")
        fg, _ = get_colors(seed_to_use)

        cmd_mention = await self.bot.tree.find_mention_for("identicon", guild=guild)
        prefix = "d!" if guild is None else self.bot.prefixes.get(guild.id, ["d!", "d?"])[0]
        description = f"**Generate this identicon:**\n" f"> {cmd_mention} {name}\n" f"> {prefix}identicon {name}"
        e = discord.Embed(title=name, description=description, color=as_discord_color(fg))
        e.set_image(url="attachment://identicon.png")
        return e, file

    @commands.hybrid_command(name="identicon", aliases=("i", "idt"))
    async def identicon(
        self,
        ctx: Context,
        seed: discord.Member | str | int = commands.param(default=MISSING, converter=MemberLikeConverter),
        pattern_size: commands.Range[int, 1, 32] = commands.param(default=6),
        fg_weight: commands.Range[float, 0, 1] = commands.param(default=0.6),
    ) -> None:
        """Generate an identicon from a user or string

        Parameters
        ----------
        seed: discord.Member | str | int, optional
            The seed to use. Random seed if empty.
        pattern_size: int, optional
            The size of the pattern.
        fg_weight: float, optional
            The weight of the foreground color.
        """
        seed_to_use = seed_from_time() if seed is MISSING else seed
        embed, file = await self.generate_identicon(seed_to_use, pattern_size, fg_weight, ctx.guild)
        await ctx.send(embed=embed, file=file)

    @commands.hybrid_command(name="spotify", aliases=("sp", "applemusic"))
    async def spotify(
        self,
        ctx: Context,
        user: discord.User | discord.Member | str | None = commands.param(default=None, converter=MemberLikeConverter),
    ) -> None:
        """Get the currently playing Spotify track for a user.

        Parameters
        ----------
        user : discord.User |discord.Member | None, optional
            The user to check. If nothing is provided, check author instead.
        """
        if user is None:
            user = ctx.author

        if isinstance(user, str) or user.bot:
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
