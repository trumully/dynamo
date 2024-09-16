import asyncio
import sys


def get_event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if sys.platform in ("win32", "cygwin", "cli"):
        try:
            import winloop
        except ImportError:
            return asyncio.WindowsSelectorEventLoopPolicy()
        else:
            return winloop.EventLoopPolicy()

    else:
        try:
            import uvloop  # type: ignore
        except ImportError:
            pass
        else:
            return uvloop.EventLoopPolicy()  # type: ignore

    return asyncio.DefaultEventLoopPolicy()
