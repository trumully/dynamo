import asyncio
import sys


def get_event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    policy = asyncio.DefaultEventLoopPolicy

    if sys.platform in ("win32", "cygwin", "cli"):
        try:
            import winloop
        except ImportError:
            policy = asyncio.WindowsSelectorEventLoopPolicy
        else:
            policy = winloop.EventLoopPolicy

    else:
        try:
            import uvloop
        except ImportError:
            pass
        else:
            policy = uvloop.EventLoopPolicy

    return policy()
