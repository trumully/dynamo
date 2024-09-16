import logging
from io import BytesIO
from typing import cast
from urllib.parse import urlparse

import discord
from discord.ext import commands

from dynamo.bot import Dynamo
from dynamo.utils.context import Context
from dynamo.utils.converter import MemberTransformer
from dynamo.utils.format import human_join
from dynamo.utils.helper import derive_seed
from dynamo.utils.identicon import Identicon, get_colors, identicon_buffer, seed_from_time
from dynamo.utils.spotify import SpotifyCard, fetch_album_cover
from dynamo.utils.time import human_timedelta

log = logging.getLogger(__name__)


def embed_from_user(user: discord.Member | discord.User | discord.ClientUser) -> discord.Embed:
    e = discord.Embed(color=user.color)
    e.set_footer(text=f"ID: {user.id}")
    avatar = user.display_avatar.with_static_format("png")
    e.set_author(name=str(user), icon_url=avatar.url)
    if not user.bot:
        e.add_field(name="Account Created", value=f"<t:{int(user.created_at.timestamp())}:R>")
    if not isinstance(user, (discord.ClientUser, discord.User)) and user.joined_at:
        e.add_field(name="Joined Server", value=f"<t:{int(user.joined_at.timestamp())}:R>")
    e.set_image(url=avatar.url)
    return e


class General(commands.GroupCog, group_name="general"):
    """Generic commands"""

    def __init__(self, bot: Dynamo) -> None:
        self.bot: Dynamo = bot

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx: commands.Context) -> None:
        """Get the bot's latency"""
        await ctx.send(f"\N{TABLE TENNIS PADDLE AND BALL} {round(self.bot.latency * 1000)}ms")

    @commands.hybrid_command(name="invite")
    async def invite(self, ctx: commands.Context) -> None:
        """Get the invite link for the bot"""
        if (user := self.bot.user) is None:
            return

        await ctx.send(f"[Invite me here!]({discord.utils.oauth_url(user.id)})", ephemeral=True)

    @commands.hybrid_command(name="about")
    async def about(self, ctx: commands.Context) -> None:
        """Get information about the bot"""
        e = embed_from_user(self.bot.user)
        bot_name = self.bot.user.display_name
        e.title = f"About {bot_name}"
        e.description = f"{bot_name} is a bot that does stuff."
        e.add_field(name="Uptime", value=f"`{human_timedelta(dt=self.bot.uptime, suffix=False)}`")
        await ctx.send(embed=e)

    @commands.hybrid_command(name="user")
    async def user(self, ctx: commands.Context, user: discord.Member | discord.User | None = None) -> None:
        """Get information about a user

        Parameters
        ----------
        user: discord.Member | discord.User | None
            The user to check. If nothing is provided, check author instead.
        """
        await ctx.send(embed=embed_from_user(user or ctx.author), ephemeral=True)

    @commands.hybrid_command(name="identicon", aliases=("i", "idt"))
    async def identicon(
        self,
        ctx: commands.Context,
        seed: discord.Member | str = commands.param(converter=MemberTransformer, default=None),
    ) -> None:
        """Generate an identicon from a user or string

        Parameters
        ----------
        seed: MemberTransformer | None
            The seed to use. Random seed if empty.
        """
        seed_to_use: discord.Member | str | int = seed if seed is not None else seed_from_time()
        if isinstance(seed_to_use, str) and (parsed := urlparse(seed_to_use)).scheme and parsed.netloc:
            seed_to_use = (parsed.netloc + parsed.path).replace("/", "-")

        display_name = seed_to_use if (isinstance(seed_to_use, (str, int))) else seed_to_use.display_name

        fname: str | int = seed_to_use if isinstance(seed_to_use, (str, int)) else seed_to_use.id
        seed_to_use = derive_seed(fname)
        fg, bg = get_colors(seed=seed_to_use)

        idt_bytes = await identicon_buffer(Identicon(5, fg, bg, 0.4, seed_to_use))
        log.debug("Identicon generated for %s", fname)
        file = discord.File(BytesIO(idt_bytes), filename=f"{fname}.png")

        cmd_mention = await self.bot.tree.find_mention_for("general identicon", guild=ctx.guild)
        prefix = self.bot.prefixes.get(ctx.guild.id, ["d!", "d?"])[0]  # type: ignore[union-attr]
        description = f"**Command:**\n{cmd_mention} {display_name}\n{prefix}identicon {display_name}"

        e = discord.Embed(title=display_name, description=description, color=discord.Color.from_rgb(*fg.as_tuple()))
        e.set_image(url=f"attachment://{fname}.png")
        await ctx.send(embed=e, file=file)

    @commands.hybrid_command(name="spotify", aliases=("sp", "applemusic"))
    async def spotify(self, ctx: Context, user: discord.Member | discord.User | None = None) -> None:
        """Generate a spotify card for a track"""
        if user is None:
            user = ctx.author

        if user.bot:
            return

        user = cast(discord.Member, user)
        activity: discord.Spotify | None = next((a for a in user.activities if isinstance(a, discord.Spotify)), None)

        if activity is None:
            await ctx.send("User is not listening to Spotify.")
            return

        card = SpotifyCard()
        album_cover: bytes | None = await fetch_album_cover(activity.album_cover_url, self.bot.session)
        if album_cover is None:
            await ctx.send("Failed to fetch album cover.")
            return

        color = activity.color.to_rgb()

        buffer, ext = await card.draw(
            name=activity.title,
            artists=activity.artists,
            color=color,
            album=album_cover,
            duration=activity.duration,
            end=activity.end,
        )
        fname = f"spotify-card.{ext}"

        file = discord.File(buffer, filename=fname)
        track = f"[{activity.title}](<{activity.track_url}>)"
        embed = discord.Embed(
            title="Now Playing",
            description=f"{user.mention} is listening to **{track}** by"
            f" **{human_join(activity.artists, conjunction="and")}**",
            color=activity.color,
        )
        embed.set_footer(text=f"Requested by {ctx.author!s}", icon_url=ctx.author.display_avatar.url)
        embed.set_image(url=f"attachment://{fname}")
        await ctx.send(embed=embed, file=file)


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(General(bot))
