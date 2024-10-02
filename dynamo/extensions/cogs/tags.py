from __future__ import annotations

from itertools import chain

import discord
from base2048 import decode, encode
from discord import app_commands
from discord.app_commands import Choice, Range
from discord.ext import commands
from msgspec import msgpack

from dynamo.core import Dynamo, DynamoCog
from dynamo.core.bot import Interaction


def b2048_pack(obj: object, /) -> str:
    return encode(msgpack.encode(obj))


def b2048_unpack[T](packed: str, _type: type[T], /) -> T:
    return msgpack.decode(decode(packed), type=_type)


class TagModal(discord.ui.Modal):
    tag: discord.ui.TextInput[TagModal] = discord.ui.TextInput(
        label="Tag",
        style=discord.TextStyle.paragraph,
        min_length=1,
        max_length=1000,
    )

    def __init__(
        self, *, title: str = "Add tag", timeout: float | None = 300, custom_id: str = "", tag_name: str, author_id: int
    ) -> None:
        discord_safe = b2048_pack((author_id, tag_name))
        custom_id = f"m:tag:{discord_safe}"
        super().__init__(title=title, timeout=10, custom_id=custom_id)

    @staticmethod
    async def raw_submit(itx: Interaction, data: str) -> None:
        cursor = itx.client.conn.cursor()
        packed = decode(data)
        author_id, tag_name = msgpack.decode(packed, type=tuple[int, str])

        assert itx.data

        if not (raw := itx.data.get("components", None)):
            return

        component = raw[0]
        if not (modal_components := component.get("components")):
            return
        content = modal_components[0]["value"]

        await itx.response.defer(ephemeral=True)
        cursor.execute(
            """
            INSERT INTO discord_users (user_id, last_interaction)
            VALUES (:author_id, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id)
            DO UPDATE SET last_interaction=excluded.last_interaction;

            INSERT INTO user_tags (user_id, tag_name, content)
            VALUES (:author_id, :tag_name, :content)
            ON CONFLICT (user_id, tag_name)
            DO UPDATE SET content=excluded.content;
            """,
            {"author_id": author_id, "tag_name": tag_name, "content": content},
        )

        await itx.followup.send(content="Tag added", ephemeral=True)


class Tags(commands.GroupCog, DynamoCog, group_name="tag"):
    """Store and recall content"""

    def __init__(self, bot: Dynamo) -> None:
        self._cache: dict[tuple[int, str], list[Choice[str]]] = {}
        super().__init__(bot, raw_modal_submits={"tag": TagModal})

    @app_commands.command(name="create")
    async def tag_create(self, itx: Interaction, name: Range[str, 1, 20]) -> None:
        """Create a tag

        Parameters
        ----------
        name : Range[str, 1, 20]
            Name of the tag
        """
        modal = TagModal(tag_name=name, author_id=itx.user.id)
        await itx.response.send_modal(modal)

    @app_commands.command(name="get")
    async def tag_get(self, itx: Interaction, name: Range[str, 1, 20]) -> None:
        """Get a tag

        Parameters
        ----------
        name : Range[str, 1, 20]
            Name of the tag
        """
        cursor = itx.client.conn.cursor()
        row = cursor.execute(
            """
            SELECT content FROM user_tags
            WHERE user_id = ? AND tag_name = ? LIMIT 1;
            """,
            (itx.user.id, name),
        ).fetchone()

        if row is None:
            await itx.response.send_message("Tag not found", ephemeral=True)
        else:
            (content,) = row
            await itx.response.send_message(content, ephemeral=True)

    @app_commands.command(name="delete")
    async def tag_delete(self, itx: Interaction, name: Range[str, 1, 20]) -> None:
        """Delete a tag

        Parameters
        ----------
        name : Range[str, 1, 20]
            Name of the tag
        """
        cursor = itx.client.conn.cursor()
        row = cursor.execute(
            """
            DELETE FROM user_tags
            WHERE user_id = ? AND tag_name = ?
            RETURNING tag_name;
            """,
            (itx.user.id, name),
        ).fetchall()
        msg = "Deleted tag" if row else "Tag not found"
        await itx.followup.send(msg, ephemeral=True)

    @tag_get.autocomplete("name")
    @tag_delete.autocomplete("name")
    async def tag_autocomplete(self, itx: Interaction, current: str) -> list[Choice[str]]:
        key = (itx.user.id, current)
        if (val := self._cache.get(key, None)) is not None:
            return val

        cursor = itx.client.conn.cursor()
        it = chain.from_iterable(
            cursor.execute(
                """
            SELECT tag_name
            FROM user_tags
            WHERE user_id = ? AND tag_name LIKE ? || '%' LIMIT 25
            """,
                key,
            )
        )
        self._cache[key] = r = [Choice(name=c, value=c) for c in it]
        return r


async def setup(bot: Dynamo) -> None:
    await bot.add_cog(Tags(bot))


async def teardown(bot: Dynamo) -> None:
    await bot.remove_cog(Tags.__name__)
