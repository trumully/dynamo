from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import discord
from base2048 import decode
from discord import app_commands
from discord.app_commands import Choice, Group, Range
from msgspec import msgpack

from dynamo.typedefs import BotExports, RawSubmittable
from dynamo.utils.datastructures import LRU, Trie
from dynamo.utils.helper import b2048_pack

if TYPE_CHECKING:
    from apsw import Connection

    from dynamo.bot import Interaction

_tags_trie: LRU[int, Trie] = LRU(128)


def _get_trie_matches(conn: Connection, user_id: int) -> Trie:
    cursor = conn.cursor()
    rows = cursor.execute(
        """
        SELECT tag_name
        FROM user_tags
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchall()
    trie = Trie()
    for (tag_name,) in rows:
        trie.insert(str(tag_name))
    return trie


class TagModal(discord.ui.Modal):
    tag: discord.ui.TextInput[TagModal] = discord.ui.TextInput(
        label="Tag",
        style=discord.TextStyle.paragraph,
        min_length=1,
        max_length=1000,
    )

    def __init__(
        self,
        *,
        title: str = "Add tag",
        timeout: float | None = 300,
        custom_id: str = "",
        tag_name: str,
        author_id: int,
    ) -> None:
        discord_safe = b2048_pack((author_id, tag_name))
        custom_id = f"m:tag:{discord_safe}"
        super().__init__(title=title, timeout=timeout, custom_id=custom_id)

    @staticmethod
    async def raw_submit(itx: Interaction, data: str) -> None:
        cursor = itx.client.conn.cursor()
        packed = decode(data)
        author_id, tag_name = msgpack.decode(packed, type=tuple[int, str])

        assert itx.data

        raw: Any | list[Any] | None = itx.data.get("components", None)

        if not raw:
            return

        component = raw[0]
        if not (modal_components := component.get("components")):
            return
        content = modal_components[0]["value"]

        await itx.response.defer(ephemeral=True)
        cursor.execute(
            """
            INSERT INTO user_tags (user_id, tag_name, content)
            VALUES (:author_id, :tag_name, :content)
            ON CONFLICT (user_id, tag_name)
            DO UPDATE SET content=excluded.content;
            """,
            {"author_id": author_id, "tag_name": tag_name, "content": content},
        )
        _tags_trie[author_id] = _get_trie_matches(itx.client.conn, author_id)
        await itx.followup.send(content="Tag added", ephemeral=True)


tag_group = Group(name="tag", description="Tag related commands")


@tag_group.command(name="create")
@app_commands.describe(name="The name of the tag to create")
async def tag_create(itx: Interaction, name: Range[str, 1, 20]) -> None:
    """Create a tag."""
    modal = TagModal(tag_name=name, author_id=itx.user.id)
    await itx.response.send_modal(modal)


@tag_group.command(name="get")
@app_commands.describe(name="The name of the tag to get")
async def tag_get(itx: Interaction, name: Range[str, 1, 20]) -> None:
    """Get a tag."""
    conn: Connection = itx.client.conn
    cursor = conn.cursor()
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


@tag_group.command(name="delete")
@app_commands.describe(name="The name of the tag to delete")
async def tag_delete(itx: Interaction, name: Range[str, 1, 20]) -> None:
    """Delete a tag."""
    await itx.response.defer(ephemeral=True)
    conn: Connection = itx.client.conn
    cursor = conn.cursor()
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
    if row:
        _tags_trie.remove(itx.user.id)


def get_user_tags(conn: Connection, user_id: int, current: str) -> list[str]:
    try:
        tags = _tags_trie.get(user_id)
    except KeyError:
        results = _get_trie_matches(conn, user_id).search(current)
    else:
        results = tags.search(current)
    return sorted(results)[:25] if len(results) > 25 else list(results)  # noqa: PLR2004


@tag_get.autocomplete("name")
@tag_delete.autocomplete("name")
async def tag_autocomplete(itx: Interaction, current: str) -> list[Choice[str]]:
    matches = get_user_tags(itx.client.conn, itx.user.id, current)
    return [Choice(name=match, value=match) for match in matches]


exports = BotExports(
    commands=[tag_group],
    raw_modal_submits={"tag": cast("type[RawSubmittable]", TagModal)},
)
