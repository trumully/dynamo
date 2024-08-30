import asyncio
import contextlib
import logging
from logging.handlers import RotatingFileHandler

import click
import discord
import toml

from dynamo.bot import Dynamo

try:
    import winloop
except ImportError:
    pass
else:
    asyncio.set_event_loop_policy(winloop.EventLoopPolicy())


def get_version() -> str:
    with open("pyproject.toml") as f:
        data = toml.load(f)
    return data["tool"]["poetry"]["version"]


class RemoveNoise(logging.Filter):
    def __init__(self):
        super().__init__(name="discord.state")

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelname == "WARNING" and "referencing an unknown" in record.msg:
            return False
        return True


@contextlib.contextmanager
def setup_logging():
    log = logging.getLogger()

    try:
        discord.utils.setup_logging()
        # __enter__
        max_bytes = 32 * 1024 * 1024  # 32 MiB
        logging.getLogger("discord").setLevel(logging.INFO)
        logging.getLogger("discord.http").setLevel(logging.WARNING)
        logging.getLogger("discord.state").addFilter(RemoveNoise())

        log.setLevel(logging.INFO)
        handler = RotatingFileHandler(
            filename="dynamo.log",
            encoding="utf-8",
            mode="w",
            maxBytes=max_bytes,
            backupCount=5,
        )
        dt_fmt = "%Y-%m-%d %H:%M:%S"
        fmt = logging.Formatter(
            "[{asctime}] [{levelname:<7}] {name}: {message}", dt_fmt, style="{"
        )
        handler.setFormatter(fmt)
        log.addHandler(handler)

        yield
    finally:
        # __exit__
        handlers = log.handlers[:]
        for hdlr in handlers:
            hdlr.close()
            log.removeHandler(hdlr)


async def run_bot() -> None:
    async with Dynamo() as bot:
        await bot.start()


@click.group(invoke_without_command=True, options_metavar="[options]")
@click.version_option(
    version=get_version(),
    prog_name="dynamo",
    message=click.style("%(version)s", bold=True, fg="bright_cyan"),
)
@click.pass_context
def main(ctx) -> None:
    """Launch the bot"""
    if ctx.invoked_subcommand is None:
        with setup_logging():
            asyncio.run(run_bot())


if __name__ == "__main__":
    main()
