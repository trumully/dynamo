import enum
import importlib.resources
from pathlib import Path

import platformdirs
from base2048 import decode, encode
from msgspec import msgpack

platformdir = platformdirs.PlatformDirs("dynamo", "trumully", roaming=False)


class PathMode(enum.IntEnum):
    FILE = 0o600
    DIR = 0o700


def _resolve_path_with_links(path: Path, mode: PathMode) -> Path:
    try:
        return path.resolve(strict=True)
    except FileNotFoundError:
        path = resolve_folder_with_links(path.parent) / path.name
        path.mkdir(mode.value) if mode == PathMode.DIR else path.touch(mode.value)
        return path.resolve(strict=True)


def resolve_folder_with_links(folder: Path) -> Path:
    return _resolve_path_with_links(folder, PathMode.DIR)


def resolve_file_with_links(file: Path) -> Path:
    return _resolve_path_with_links(file, PathMode.FILE)


ROOT = Path(str(importlib.resources.files("dynamo"))).parent.parent


def b2048_pack(obj: object, /) -> str:
    return encode(msgpack.encode(obj))


def b2048_unpack[T](packed: str, _type: type[T], /) -> T:
    return msgpack.decode(decode(packed), type=_type)
