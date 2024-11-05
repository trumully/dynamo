import copy
from typing import Any

import discord

from dynamo.typedefs import ContextT


async def copy_context_with(
    ctx: ContextT,
    *,
    author: discord.Member | discord.User | None = None,
    channel: discord.TextChannel | None = None,
    **kwargs: Any,
) -> ContextT:
    alt_message: discord.Message = copy.copy(ctx.message)
    alt_message._update(kwargs)  # type: ignore

    if author is not None:
        alt_message.author = author

    if channel is not None:
        alt_message.channel = channel

    return await ctx.bot.get_context(alt_message, cls=type(ctx))
