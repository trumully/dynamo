from pathlib import Path

import platformdirs

platformdir = platformdirs.PlatformDirs("dynamo", "trumully", roaming=False)


def resolve_path_with_links(path: Path, folder: bool = False) -> Path:
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
