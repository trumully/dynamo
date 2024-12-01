from collections.abc import Callable

from discord import app_commands

from dynamo.bot import Interaction

type Check[T] = Callable[[T], T]


def is_in_team[T]() -> Check[T]:
    async def predicate(itx: Interaction) -> bool:
        return itx.user.id in await itx.client.cachefetch_priority_ids()

    return app_commands.check(predicate)


def in_personal_guild[T]() -> Check[T]:
    async def predicate(itx: Interaction) -> bool:
        return itx.guild is not None and itx.guild.id == 696276827341324318  # noqa: PLR2004

    return app_commands.check(predicate)
