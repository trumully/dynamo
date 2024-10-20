import importlib.resources
import re
from collections.abc import AsyncGenerator, AsyncIterable
from contextlib import aclosing
from pathlib import Path
from typing import cast

import platformdirs

platformdir = platformdirs.PlatformDirs("dynamo", "trumully", roaming=False)


def valid_url(url: str) -> bool:
    return re.match(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", url) is not None


def resolve_path_with_links(path: Path, /, folder: bool = False) -> Path:
    """Resolve a path with links"""
    try:
        return path.resolve(strict=True)
    except FileNotFoundError:
        path = resolve_path_with_links(path.parent, folder=True) / path.name
        # 0o700: read/write/traversable
        # 0o600: read/write
        path.mkdir(mode=0o700) if folder else path.touch(mode=0o600)
        return path.resolve(strict=True)


ROOT = Path(str(importlib.resources.files("dynamo"))).parent.parent


def valid_token(token: str) -> bool:
    """
    Validate a discord bot token

    A discord bot token is a string that matches the following pattern:
    >>> "[M|N|O]XXXXXXXXXXXXXXXXXXXXXXX[XX].XXXXXX.XXXXXXXXXXXXXXXXXXXXXXXXXXX"

    See
    ---
    - https://discord.com/developers/docs/reference#authentication
    """
    pattern = re.compile(r"[MNO][a-zA-Z\d_-]{23,25}\.[a-zA-Z\d_-]{6}\.[a-zA-Z\d_-]{27}")
    return bool(pattern.match(token))


async def process_async_iterable[T](seq: AsyncIterable[T]) -> list[T]:
    """Safely process an async iterable

    See
    ---
    - https://peps.python.org/pep-0533/
    """
    async with aclosing(cast(AsyncGenerator[T], seq)) as gen:
        return [item async for item in gen]
