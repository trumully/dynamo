import datetime
import itertools
from importlib import metadata

import discord
import psutil
import pygit2
from discord.ext import commands

from dynamo.bot import Dynamo
from dynamo.utils.base_cog import DynamoCog
from dynamo.utils.context import Context
from dynamo.utils.time import format_relative, human_timedelta

PYTHON = "https://s3.dualstack.us-east-2.amazonaws.com/pythondotorg-assets/media/community/logos/python-logo-only.png"


class Stats(DynamoCog):
    """Statistics commands"""

    def __init__(self, bot: Dynamo) -> None:
        super().__init__(bot)

        self.process = psutil.Process()

    def format_commit(self, commit: pygit2.Commit) -> str:
        """Format a commit message

        Parameters
        ----------
        commit : pygit2.Commit
            _description_

        Returns
        -------
        str
            A formatted commit message [`hash`](url) message (offset)
        """
        short, *_ = commit.message.partition("\n")
        sha2_short = commit.short_id
        commit_tz = datetime.timezone(datetime.timedelta(minutes=commit.commit_time_offset))
        commit_time = datetime.datetime.fromtimestamp(commit.commit_time, commit_tz).astimezone(commit_tz)

        offset = format_relative(dt=commit_time)
        return f"[`{sha2_short}`](https://github.com/trumully/dynamo/commit/{commit.id}) {short} ({offset})"

    def get_latest_commits(self, count: int = 3) -> str:
        repo = pygit2.Repository(".git")
        commits = list(itertools.islice(repo.walk(repo.head.target, pygit2.GIT_SORT_TOPOLOGICAL), count))
        return "\n".join(self.format_commit(c) for c in commits)

    @commands.hybrid_command(name="about")
    async def about(self, ctx: Context) -> None:
        """Get information about the bot"""

        bot_name = self.bot.user.display_name
        revision = self.get_latest_commits()
        avatar_url = self.bot.user.display_avatar.with_static_format("png")
        discord_version = metadata.version("discord.py")

        embed = discord.Embed(description=f"Latest changes:\n{revision}")
        embed.title = f"About {bot_name}"
        embed.color = discord.Color.dark_embed()
        embed.set_author(name=bot_name, icon_url=avatar_url)

        memory_usage = self.process.memory_full_info().rss / (1024**2)
        cpu_usage = self.process.cpu_percent() / psutil.cpu_count()
        embed.add_field(name="Process", value=f"{memory_usage:.2f} MiB\n{cpu_usage:.2f}% CPU")

        embed.add_field(name="Uptime", value=human_timedelta(dt=self.bot.uptime, brief=True, suffix=False))
        embed.set_footer(text=f"Made using discord.py v{discord_version}", icon_url=PYTHON)

        embed.timestamp = discord.utils.utcnow()

        await ctx.send(embed=embed)


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Stats(bot))


async def teardown(bot: Dynamo) -> None:
    await bot.remove_cog(Stats.__name__)
