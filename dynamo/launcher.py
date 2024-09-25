import asyncio
import logging
import logging.handlers
import os
import signal
import socket
import ssl
from importlib import metadata
from typing import Any

import aiohttp
import base2048
import click
import pygit2
import truststore

from dynamo._evt_policy import get_event_loop_policy
from dynamo.core import Dynamo, setup_logging
from dynamo.utils.format import plural
from dynamo.utils.helper import platformdir, resolve_path_with_links, valid_token

log = logging.getLogger(__name__)


def run_bot() -> None:
    loop = asyncio.new_event_loop()
    loop.set_task_factory(asyncio.eager_task_factory)
    policy = get_event_loop_policy()
    asyncio.set_event_loop_policy(policy)
    asyncio.set_event_loop(loop)

    # https://github.com/aio-libs/aiohttp/issues/8599
    # https://github.com/mikeshardmind/salamander-reloaded
    connector = aiohttp.TCPConnector(
        happy_eyeballs_delay=None,
        family=socket.AddressFamily.AF_INET,
        ttl_dns_cache=60,
        loop=loop,
        ssl=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
    )
    session = aiohttp.ClientSession(connector=connector)
    bot = Dynamo(connector=connector, session=session)

    async def entrypoint() -> None:
        try:
            if not (token := _get_token()):
                return
            async with bot:
                await bot.start(token)
        finally:
            if not bot.is_closed():
                await bot.close()

    try:
        loop.add_signal_handler(signal.SIGINT, lambda: loop.stop())
        loop.add_signal_handler(signal.SIGTERM, lambda: loop.stop())
    except NotImplementedError:
        pass

    def stop_when_done(fut: asyncio.Future[None]) -> None:
        loop.stop()

    fut = asyncio.ensure_future(entrypoint(), loop=loop)
    try:
        fut.add_done_callback(stop_when_done)
        loop.run_forever()
    except KeyboardInterrupt:
        log.info("Shutdown via keyboard interrupt")
    finally:
        log.info("Shutting down")
        fut.remove_done_callback(stop_when_done)
        if not bot.is_closed():
            _close_task = loop.create_task(bot.close())  # noqa: RUF006
        loop.run_until_complete(asyncio.sleep(0.001))

        tasks: set[asyncio.Task[Any]] = {t for t in asyncio.all_tasks(loop) if not t.done()}

        async def limited_finalization() -> None:
            _done, pending = await asyncio.wait(tasks, timeout=0.1)
            if not pending:
                log.debug("Clean shutdown accomplished.")
                return

            for task in tasks:
                task.cancel()

            _done, pending = await asyncio.wait(tasks, timeout=0.1)

            for task in pending:
                name = task.get_name()
                coro = task.get_coro()
                log.warning("Task %s wrapping coro %r did not exit properly", name, coro)

        if tasks:
            loop.run_until_complete(limited_finalization())
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(loop.shutdown_default_executor())

        for task in tasks:
            try:
                if (exc := task.exception()) is not None:
                    loop.call_exception_handler(
                        {
                            "message": "Unhandled exception in task during shutdown.",
                            "exception": exc,
                            "task": task,
                        }
                    )
            except (asyncio.InvalidStateError, asyncio.CancelledError):
                pass

        asyncio.set_event_loop(None)
        loop.close()

        if not fut.cancelled():
            try:
                fut.result()
            except KeyboardInterrupt:
                pass


def _load_token() -> str | None:
    token_file_path = resolve_path_with_links(platformdir.user_config_path / "dynamo.token")
    with token_file_path.open(mode="r", encoding="utf-8") as fp:
        data = fp.read()
        return base2048.decode(data).decode("utf-8") if data else None


def _store_token(token: str, /) -> None:
    token_file_path = resolve_path_with_links(platformdir.user_config_path / "dynamo.token")
    with token_file_path.open(mode="w", encoding="utf-8") as fp:
        fp.write(base2048.encode(token.encode()))


def _get_token() -> str | None:
    if not (token := _load_token()):
        log.critical("\nToken not found. Please run `dynamo setup` before starting the bot.\n")
        return None
    return token


def check_for_updates() -> tuple[int, int]:
    try:
        repo = pygit2.Repository(".")
        repo.remotes["origin"].fetch()
        local_branch = repo.head.shorthand
        local_commit = repo.revparse_single(local_branch).short_id
        remote_commit = repo.revparse_single(f"origin/{local_branch}").short_id

        ahead, behind = repo.ahead_behind(local_commit, remote_commit)
    except (pygit2.GitError, KeyError):
        return 0, 0
    return ahead, behind


def propagate_updates() -> None:
    ahead, behind = check_for_updates()
    if behind:
        click.echo(click.style(f"You are {plural(behind):commit} behind the remote branch.", fg="yellow", bold=True))
    elif ahead:
        click.echo(click.style(f"You are {plural(ahead):commit} ahead of the remote branch.", fg="cyan", bold=True))
    else:
        click.echo(click.style("You are up to date with the remote branch.", fg="green"))


@click.group(invoke_without_command=True, options_metavar="[options]")
@click.version_option(
    metadata.version("dynamo"),
    "-v",
    "--version",
    package_name="Dynamo",
    prog_name="dynamo",
    message=click.style("%(prog)s", fg="yellow") + click.style(" %(version)s", fg="bright_cyan"),
)
@click.option("--debug", "-d", is_flag=True, help="Set log level to debug")
@click.pass_context
def main(ctx: click.Context, debug: bool) -> None:
    """Launch the bot"""
    propagate_updates()
    os.umask(0o077)
    if ctx.invoked_subcommand is None:
        log_level = logging.DEBUG if debug else logging.INFO
        if log_level == logging.DEBUG:
            click.echo("Running in DEBUG mode", err=True)
        with setup_logging(log_level=log_level):
            run_bot()


@main.command(name="help")
@click.pass_context
def dynamo_help(ctx: click.Context) -> None:
    """Show this message and exit."""
    if ctx.parent is not None:
        click.echo(ctx.parent.get_help())


@main.command()
def setup() -> None:
    """Set the bot's token"""
    if not valid_token(token := click.prompt("Enter your bot token", hide_input=True, type=str)):
        text = "\N{WARNING SIGN} WARNING: That token doesn't look right. Double check before starting the bot."
        msg = click.style(text, bold=True, fg="yellow")
        click.echo(msg, err=True)
    _store_token(token)


@main.command()
def config() -> None:
    """Get the path to the bot's config directory"""
    click.echo(platformdir.user_config_path)


if __name__ == "__main__":
    main()
