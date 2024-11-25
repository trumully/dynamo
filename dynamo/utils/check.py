from collections.abc import Callable

from discord import app_commands

from dynamo.bot import Interaction


def is_in_team[T]() -> Callable[[T], T]:
    async def predicate(interaction: Interaction) -> bool:
        priority_ids: set[int] = await interaction.client.cachefetch_priority_ids()  # type: ignore[call-arg]
        return interaction.user.id in priority_ids

    return app_commands.check(predicate)
