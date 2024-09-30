from io import BytesIO
from urllib.parse import urlparse

import discord
from discord.ext import commands

from dynamo.core import Dynamo, DynamoCog
from dynamo.utils import spotify
from dynamo.utils.context import Context
from dynamo.utils.converter import SeedConverter
from dynamo.utils.identicon import Identicon, derive_seed, get_colors, get_identicon, seed_from_time


class General(DynamoCog):
    """Generic commands"""

    def __init__(self, bot: Dynamo) -> None:
        super().__init__(bot)

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
        seed_to_use: discord.Member | str | int = seed if seed else seed_from_time()
        if isinstance(seed_to_use, str) and (parsed := urlparse(seed_to_use)).scheme and parsed.netloc:
            seed_to_use = (parsed.netloc + parsed.path).replace("/", "-")

        display_name = seed_to_use if (isinstance(seed_to_use, str | int)) else seed_to_use.display_name

        seed_to_use = derive_seed(display_name)
        fg, bg = get_colors(seed=seed_to_use)

        identicon: bytes = await get_identicon(Identicon(5, fg, bg, 0.4, seed_to_use))
        file = discord.File(BytesIO(identicon), filename="identicon.png")

        cmd_mention = await self.bot.tree.find_mention_for("identicon", guild=guild)
        prefix = "d!" if guild is None else self.bot.prefixes.get(guild.id, ["d!", "d?"])[0]
        description = (
            f"**Generate this identicon:**\n" f"> {cmd_mention} {display_name}\n" f"> {prefix}identicon {display_name}"
        )
        e = discord.Embed(title=display_name, description=description, color=fg.as_discord_color())
        e.set_image(url="attachment://identicon.png")
        return e, file

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx: Context) -> None:
        """Get the bot's latency"""
        await ctx.send(f"\N{TABLE TENNIS PADDLE AND BALL} {round(self.bot.latency * 1000)}ms")

    @commands.hybrid_command(name="identicon", aliases=("i", "idt"))
    async def identicon(
        self,
        ctx: Context,
        seed: discord.Member | str | int = commands.param(converter=SeedConverter, default=""),
    ) -> None:
        """Generate an identicon from a user or string

        Parameters
        ----------
        seed: discord.Member | str | int, optional
            The seed to use. Random seed if empty.
        """
        embed, file = await self.generate_identicon(seed, ctx.guild)
        await ctx.send(embed=embed, file=file)

    @commands.hybrid_command(name="spotify", aliases=("sp", "applemusic"))
    async def spotify(
        self,
        ctx: Context,
        user: discord.User | discord.Member | None = commands.param(default=None, converter=commands.MemberConverter),
    ) -> None:
        """Get the currently playing Spotify track for a user.

        Parameters
        ----------
        user : discord.Member | discord.User | None, optional
            The user to check. If nothing is provided, check author instead.
        """
        if user is None:
            user = ctx.author

        if user.bot:
            return

        activities = getattr(user, "activities", [])
        activity: discord.Spotify | None = next(filter(lambda a: isinstance(a, discord.Spotify), activities), None)

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
