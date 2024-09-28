from typing import Any

import discord


class Emojis(dict[str, str]):
    def __init__(self, emojis: list[discord.Emoji], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        for emoji in emojis:
            self[emoji.name] = f"<{"a" if emoji.animated else ""}:{emoji.name}:{emoji.id}>"
