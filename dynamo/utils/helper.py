import hashlib
import re
import time
from pathlib import Path

import platformdirs

platformdir = platformdirs.PlatformDirs("dynamo", "trumully", roaming=False)


def resolve_path_with_links(path: Path, /, folder: bool = False) -> Path:
    """Resolve if path exists

    Args:
        path (Path): Path to resolve
        folder (bool, optional): If the path is a folder. Defaults to False.

    Returns:
        Path: Resolved path
    """
    try:
        return path.resolve(strict=True)
    except FileNotFoundError:
        path = resolve_path_with_links(path.parent, folder=True) / path.name
        # 0o700: read/write/traversable
        # 0o600: read/write
        path.mkdir(mode=0o700) if folder else path.touch(mode=0o600)
        return path.resolve(strict=True)


def valid_token(token: str) -> bool:
    """Validate a discord bot token

    Discord Bot Token ([M|N|O]XXXXXXXXXXXXXXXXXXXXXXX[XX].XXXXXX.XXXXXXXXXXXXXXXXXXXXXXXXXXX)

    Args:
        token (str): The token to validate

    Returns:
        bool: True if the token is valid, False otherwise
    """
    # refs:
    # https://github.com/Yelp/detect-secrets/blob/master/detect_secrets/plugins/discord.py
    # https://discord.com/developers/docs/reference#authentication
    # https://github.com/Yelp/detect-secrets/issues/627
    pattern = re.compile(r"[MNO][a-zA-Z\d_-]{23,25}\.[a-zA-Z\d_-]{6}\.[a-zA-Z\d_-]{27}")
    return bool(pattern.match(token))


def generate_seed(seed: int | str | None = None) -> tuple[int, int | str]:
    """Generate a seed from a discord snowflake"""
    if not seed:
        seed = str(time.monotonic()).replace(".", "")
    real_seed = seed
    if isinstance(seed, int):
        seed = str(seed)
    seed = seed.encode()
    hashed = int.from_bytes(seed + hashlib.sha256(seed).digest(), byteorder="big")
    return hashed, real_seed
