import inspect

from dynamo.extensions.plugins import Plugin
from dynamo.extensions.plugins.management import ManagementPlugin
from dynamo.extensions.plugins.root import RootCommand
from dynamo.typedefs import BotT

STANDARD_PLUGINS = (ManagementPlugin, RootCommand)
OPTIONAL_PLUGINS: list[type[Plugin]] = []


class Dev(*OPTIONAL_PLUGINS, *STANDARD_PLUGINS):  # pyright: ignore[reportUntypedBaseClass]
    """Base class for all dev commands."""


async def async_setup(bot: BotT):
    await bot.add_cog(Dev(bot=bot))


def setup(bot: BotT):
    if inspect.iscoroutinefunction(bot.add_cog):
        return async_setup(bot)
    bot.add_cog(Dev(bot=bot))  # noqa: RET503  # pyright: ignore[reportUnusedCoroutine]
