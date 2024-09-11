import logging
from io import BytesIO

import discord
from discord.ext import commands

from dynamo.bot import Dynamo
from dynamo.utils.helper import generate_seed
from dynamo.utils.identicon import Identicon, get_colors, identicon_buffer, seed_from_time
from dynamo.utils.time import human_timedelta
from dynamo.utils.transformer import MemberTransformer

log = logging.getLogger(__name__)


def embed_from_user(user: discord.Member | discord.User) -> discord.Embed:
    e = discord.Embed()
    e.set_footer(text=f"ID: {user.id}")
    avatar = user.display_avatar.with_static_format("png")
    e.set_author(name=str(user), icon_url=avatar.url)
    if not user.bot:
        e.add_field(name="Account Created", value=f"`{human_timedelta(dt=user.created_at, suffix=True)}`")
    if not isinstance(user, discord.ClientUser):
        e.add_field(name="Joined Server", value=f"`{human_timedelta(dt=user.joined_at, suffix=True)}`")
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
    async def identicon(self, ctx: commands.Context, seed: MemberTransformer = None) -> None:
        """Generate an identicon from a user or string

        Parameters
        ----------
        seed: str | discord.User | discord.Member
            The seed to use. Random seed if empty.
        """
        if not seed:
            seed = seed_from_time()

        display_name = seed if isinstance(seed, str) else seed.display_name

        fname = seed if isinstance(seed, str) else seed.id
        seed = generate_seed(fname)
        fg, bg = get_colors(seed=seed)

        idt_bytes = await identicon_buffer(Identicon(5, fg, bg, 0.4, seed))
        log.debug("Identicon generated for %s", fname)
        file = discord.File(BytesIO(idt_bytes), filename=f"{fname}.png")

        cmd_mention = await self.bot.tree.find_mention_for("general identicon", guild=ctx.guild)
        prefix = self.bot.prefixes.get(ctx.guild.id, ["d!", "d?"])[0]
        description = f"**Command:**\n{cmd_mention} {display_name}\n{prefix}identicon {display_name}"

        e = discord.Embed(title=display_name, description=description, color=discord.Color.from_rgb(*fg.as_tuple()))
        e.set_image(url=f"attachment://{fname}.png")
        await ctx.send(embed=e, file=file)


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(General(bot))
