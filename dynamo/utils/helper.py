import hashlib
import re
from pathlib import Path

import platformdirs

platformdir = platformdirs.PlatformDirs("dynamo", "trumully", roaming=False)


def valid_url(url: str) -> bool:
    return re.match(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*(),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", url) is not None


def resolve_path_with_links(path: Path, /, folder: bool = False) -> Path:
    """Resolve a path with links

    Parameters
    ----------
    path : Path
        The path to resolve.
    folder : bool, optional
        Whether to create a folder if the path does not exist, by default False.

    Returns
    -------
    Path
        The resolved path.
    """
    try:
        return path.resolve(strict=True)
    except FileNotFoundError:
        path = resolve_path_with_links(path.parent, folder=True) / path.name
        # 0o700: read/write/traversable
        # 0o600: read/write
        path.mkdir(mode=0o700) if folder else path.touch(mode=0o600)
        return path.resolve(strict=True)


ROOT = resolve_path_with_links(Path(__file__).parent.parent.parent, folder=True)


def valid_token(token: str) -> bool:
    """Validate a discord bot token

    Parameters
    ----------
    token : str
        The token to validate.

    Returns
    -------
    bool
        Whether the token is valid.

    Notes
    -----
    A discord bot token is a string that matches the following pattern:
    >>> "[M|N|O]XXXXXXXXXXXXXXXXXXXXXXX[XX].XXXXXX.XXXXXXXXXXXXXXXXXXXXXXXXXXX"
    """
    # refs:
    # https://discord.com/developers/docs/reference#authentication
    # https://github.com/Yelp/detect-secrets/blob/master/detect_secrets/plugins/discord.py
    # https://github.com/Yelp/detect-secrets/issues/627
    pattern = re.compile(r"[MNO][a-zA-Z\d_-]{23,25}\.[a-zA-Z\d_-]{6}\.[a-zA-Z\d_-]{27}")
    return bool(pattern.match(token))


def derive_seed(precursor: int | str) -> int:
    """Generate a seed from integer, integer-like (i.e discord snowflake) or string

    Parameters
    ----------
    precursor : int | str | None, optional
        The precursor to generate the seed from.

    Returns
    -------
    int
        The generated seed.
    """
    if isinstance(precursor, int):
        precursor = str(precursor)
    hashed = int.from_bytes(precursor.encode() + hashlib.sha256(precursor.encode()).digest(), byteorder="big")
    return hashed  # noqa: RET504  needs to be assigned as a var to work properly


def get_cog(name: str) -> str:
    return f"dynamo.extensions.cogs.{name.lower()}"
