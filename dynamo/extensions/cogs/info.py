import datetime
import itertools
import os
import platform
import time
from importlib import metadata

import discord
import psutil
import pygit2
from discord.ext import commands

from dynamo import Cog, Context, Dynamo
from dynamo.utils.converter import MemberLikeConverter
from dynamo.utils.time_utils import format_relative, human_timedelta

PYTHON = "https://s3.dualstack.us-east-2.amazonaws.com/pythondotorg-assets/media/community/logos/python-logo-only.png"


def format_commit(commit: pygit2.Commit) -> str:
    """A formatted commit message [`hash`](url) message (offset)"""
    short, *_ = commit.message.partition("\n")
    commit_tz = datetime.timezone(datetime.timedelta(minutes=commit.commit_time_offset))
    commit_time = datetime.datetime.fromtimestamp(commit.commit_time, commit_tz).astimezone(commit_tz)

    offset = format_relative(dt=commit_time)
    return f"[`{commit.short_id}`](https://github.com/trumully/dynamo/commit/{commit.id}) {short} ({offset})"


def get_latest_commits(count: int = 3) -> str:
    """Get (count) latest commits from the git repository"""
    repo = pygit2.repository.Repository(".git")
    commits = list(itertools.islice(repo.walk(repo.head.target, pygit2.enums.SortMode.TOPOLOGICAL), count))  # type: ignore
    return "\n".join(format_commit(c) for c in commits)


def embed_from_user(user: discord.Member | discord.User) -> discord.Embed:
    embed = discord.Embed(color=user.color)
    avatar = user.display_avatar.with_static_format("png")
    embed.set_footer(text=f"ID: {user.id}")
    embed.set_author(name=str(user))
    embed.set_image(url=avatar.url)
    embed.timestamp = discord.utils.utcnow()
    return embed


class Info(Cog, name="info"):
    """Statistics commands"""

    def __init__(self, bot: Dynamo) -> None:
        super().__init__(bot)

        self.process = psutil.Process(os.getpid())

    @commands.hybrid_command(name="ping")
    async def ping(self, ctx: Context) -> None:
        """Get the bot's latency"""
        before = time.monotonic()
        before_ws = int(round(self.bot.latency * 1000, 1))
        message = await ctx.send("\N{TABLE TENNIS PADDLE AND BALL} Pong")
        ping = (time.monotonic() - before) * 1000
        await message.edit(content=f"\N{TABLE TENNIS PADDLE AND BALL} WS: `{before_ws}ms`\t|\tREST: `{int(ping)}ms`")

    @commands.hybrid_command(name="about")
    async def about(self, ctx: Context) -> None:
        """Get information about the bot"""

        bot_name = self.bot.user.display_name
        revision = get_latest_commits()
        avatar_url = self.bot.user.display_avatar.with_static_format("png")

        embed = discord.Embed(description=f"Latest changes:\n{revision}")
        embed.title = f"About {bot_name}"
        embed.color = discord.Color.dark_embed()
        embed.set_author(name=bot_name, icon_url=avatar_url)

        memory_usage = self.process.memory_full_info().rss / (1024**2)
        cpu_usage = self.process.cpu_percent()
        embed.add_field(name="Process", value=f"{memory_usage:.2f} MiB\n{cpu_usage:.2f}% CPU")

        embed.add_field(name="Uptime", value=human_timedelta(dt=self.bot.uptime, brief=True, suffix=False))
        versions = f"Python {platform.python_version()} | discord.py v{metadata.version("discord.py")}"
        embed.set_footer(text=versions, icon_url=PYTHON)

        embed.timestamp = discord.utils.utcnow()

        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="avatar")
    async def avatar(
        self,
        ctx: Context,
        user: discord.Member | discord.User | None = commands.param(default=None, converter=MemberLikeConverter),
    ) -> None:
        """Get the avatar of a user

        Parameters
        ----------
        user: discord.Member | discord.User | None
            The user to get the avatar of
        """
        await ctx.send(embed=embed_from_user(ctx.author if user is None else user), ephemeral=True)


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Info(bot))


async def teardown(bot: Dynamo) -> None:
    await bot.remove_cog(Info.__name__)
