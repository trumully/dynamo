from collections.abc import Callable

from discord import app_commands

from dynamo.bot import Interaction


def is_in_team[T]() -> Callable[[T], T]:
    async def predicate(interaction: Interaction) -> bool:
        return interaction.user.id in await interaction.client.cachefetch_priority_ids()

    return app_commands.check(predicate)
