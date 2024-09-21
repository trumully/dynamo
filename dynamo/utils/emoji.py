from typing import Any

import discord

emoji_base = "<{}:{}:{}>"


class Emojis(dict[str, discord.Emoji]):
    def __init__(self, emojis: list[discord.Emoji], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        for emoji in emojis:
            self[emoji.name] = emoji_base.format("a" if emoji.animated else "", emoji.name, emoji.id)
