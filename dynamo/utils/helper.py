import importlib.resources
import re
from collections.abc import AsyncGenerator, AsyncIterable, Iterable
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


async def process_async_iterable[T](async_iterable: AsyncIterable[T]) -> Iterable[T]:
    """Safely process an async iterable

    See
    ---
    - https://peps.python.org/pep-0533/
    """
    async with aclosing(cast(AsyncGenerator[T], async_iterable)) as gen:
        return [item async for item in gen]
