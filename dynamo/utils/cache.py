from __future__ import annotations

import asyncio
import pickle
import time
from enum import Enum, auto
from functools import wraps
from typing import Any, Callable, Coroutine, Hashable, Iterator, MutableMapping, Protocol, TypeVar

from dynamo.utils.helper import platformdir, resolve_path_with_links

R = TypeVar("R")
K = TypeVar("K", bound=Hashable)
V = TypeVar("V")
T = TypeVar("T")


# TODO: alternative to pickle
def cache_bytes(name: str, data: bytes) -> None:
    p = resolve_path_with_links(platformdir.user_cache_path / "identicon" / f"{name}.pkl")
    with p.open("wb") as fp:
        pickle.dump(data, fp)


def get_bytes(name: str) -> bytes | None:
    p = resolve_path_with_links(platformdir.user_cache_path / "identicon" / f"{name}.pkl")
    try:
        with p.open("rb") as fp:
            return pickle.load(fp)  # noqa: S301
    except (FileNotFoundError, EOFError):
        return None


class CacheProtocol(Protocol[R]):
    cache: MutableMapping[str, asyncio.Task[R]]

    def __call__(self, *args: Any, **kwargs: Any) -> asyncio.Task[R]: ...

    def get_key(self, *args: Any, **kwargs: Any) -> str: ...

    def invalidate(self, *args: Any, **kwargs: Any) -> bool: ...

    def invalidate_containing(self, key: str) -> None: ...

    def get_stats(self) -> tuple[int, int]: ...


class LRU(CacheProtocol):
    def __init__(self, maxsize: int = 128) -> None:
        self.maxsize = maxsize
        self.cache: MutableMapping[str, asyncio.Task[R]] = {}
        super().__init__()

    def get(self, key: K, default: T, /) -> V | T:
        if key not in self.cache:
            return default
        self.cache[key] = self.cache.pop(key)
        return self.cache[key]

    def __getitem__(self, key: K, /) -> V:
        self.cache[key] = self.cache.pop(key)
        return self.cache[key]

    def __setitem__(self, key: K, value: V, /) -> None:
        self.cache[key] = value
        if len(self.cache) > self.maxsize:
            self.cache.pop(next(iter(self.cache)))


class TTL(CacheProtocol):
    def __init__(self, seconds: float = 1800) -> None:
        self.ttl = seconds
        self.cache: MutableMapping[str, asyncio.Task[R]] = {}
        super().__init__()

    def __verify_cache_integrity(self) -> None:
        current_time = time.monotonic()
        to_remove = [k for (k, (_, t)) in super().items() if current_time > (t + self.ttl)]
        for k in to_remove:
            del self[k]

    def __contains__(self, key: K, /) -> bool:
        self.__verify_cache_integrity()
        return super().__contains__(key)

    def __getitem__(self, key: K, /) -> V:
        self.__verify_cache_integrity()
        v, _ = super().__getitem__(key)
        return v

    def get(self, key: str, default: T, /) -> Any:
        v = super().get(key, default)
        return default if v is default else v[0]

    def __setitem__(self, key: T, value: V, /) -> None:
        super().__setitem__(key, (value, time.monotonic()))

    def values(self) -> Iterator[V]:
        return map(extract_value, super().values())

    def items(self) -> Iterator[tuple[K, V]]:
        return map(extract_key, super().items())


def extract_value(item: tuple[Any, Any]) -> Any:
    return item[1]


def extract_key(item: tuple[str, tuple[Any, Any]]) -> tuple[str, Any]:
    return (item[0], item[1][0])


class Strategy(Enum):
    LRU = auto()
    RAW = auto()
    TIMED = auto()


def _stats() -> tuple[int, int]:
    return (0, 0)


def cache(
    maxsize: int = 128, strategy: Strategy = Strategy.LRU
) -> Callable[[Callable[..., Coroutine[Any, Any, R]]], CacheProtocol[R]]:
    def decorator(func: Callable[..., Coroutine[Any, Any, R]]) -> CacheProtocol[R]:
        if strategy is Strategy.LRU:
            cache = LRU(maxsize=maxsize)
            stats = cache.get_stats
        elif strategy is Strategy.RAW:
            cache: MutableMapping[str, asyncio.Task[R]] = {}
            stats = _stats
        elif strategy is Strategy.TIMED:
            cache = TTL(maxsize=maxsize)
            stats = _stats

        def make_key(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
            def true_repr(o: Any) -> str:
                if o.__class__.__repr__ is object.__repr__:
                    return f"<{o.__class__.__module__}.{o.__class__.__name__}>"
                return repr(o)

            key = [f"{func.__module__}.{func.__name__}"]
            key.extend(true_repr(o) for o in args)

            return ":".join(key)

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> asyncio.Task[R]:
            key = make_key(args, kwargs)

            try:
                task = cache[key]
            except KeyError:
                cache[key] = task = asyncio.create_task(func(*args, **kwargs))

            return task

        def invalidate(*args: Any, **kwargs: Any) -> bool:
            try:
                del cache[make_key(args, kwargs)]
            except KeyError:
                return False
            return True

        def invalidate_containing(key: str) -> None:
            to_remove = [k for k in cache if key in k]
            for k in to_remove:
                try:
                    del cache[k]
                except KeyError:
                    continue

        wrapper.cache = cache
        wrapper.get_key = lambda *args, **kwargs: make_key(args, kwargs)
        wrapper.invalidate = invalidate
        wrapper.get_stats = stats
        wrapper.invalidate_containing = invalidate_containing
        return wrapper

    return decorator
