"""User beware!

This extension allows for execution of arbitrary code. Safety is not guaranteed.
Limited to authorized users only.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

import discord
from base2048 import decode
from discord import app_commands
from msgspec import msgpack

from dynamo.typedefs import BotExports, RawSubmittable
from dynamo.utils.check import is_in_team
from dynamo.utils.format import Codeblock
from dynamo.utils.helper import b2048_pack
from dynamo.utils.scripting import MAX_OUTPUT_LENGTH_CHARS, ExecutionError, execute_script

if TYPE_CHECKING:
    from dynamo.bot import Interaction

log = logging.getLogger(__name__)


class ExecModal(discord.ui.Modal):
    script: discord.ui.TextInput[ExecModal] = discord.ui.TextInput(
        label="Python Script",
        style=discord.TextStyle.paragraph,
        min_length=1,
        max_length=1000,
        placeholder='print("Hello, world!")',
    )

    dependencies: discord.ui.TextInput[ExecModal] = discord.ui.TextInput(
        label="Dependencies (optional)",
        style=discord.TextStyle.short,
        required=False,
        placeholder="requests, rich",
    )

    def __init__(
        self,
        *,
        title: str = "Execute Python Code",
        timeout: float | None = 300,
        author_id: int,
        salt: int,
    ) -> None:
        _id = b2048_pack((author_id, salt))
        custom_id = f"m:exec:{_id}"
        super().__init__(title=title, timeout=timeout, custom_id=custom_id)

    @staticmethod
    async def raw_submit(itx: Interaction, data: str) -> None:
        assert itx.data

        try:
            packed = decode(data)
            user_id, itx_id = msgpack.decode(packed, type=tuple[int, int])
        except Exception:
            log.exception("Failed to decode interaction data: %s")
            await itx.response.send_message("❌ Invalid interaction data", ephemeral=True)
            return

        log.debug("exec script itx id %d (User ID: %d)", itx_id, user_id)

        await itx.response.defer(ephemeral=True)
        raw: Any | list[Any] | None = itx.data.get("components", None)
        if not raw:
            return

        components = []
        for row in raw:
            if row_components := row.get("components"):
                components.extend(row_components)

        # Get script and dependencies from modal components
        script: str = components[0]["value"]
        dependencies_input: str = components[1]["value"]

        # Extract code from markdown if present
        script = Codeblock.as_raw(script).content

        # Parse dependencies
        deps = [dep.strip() for dep in dependencies_input.split(",") if dep.strip()]
        log.debug("dependencies: %s", deps)

        try:
            stdout, stderr = await execute_script(script, deps)

            # Format response
            response = []
            if stdout:
                response.extend(["**stdout:**", str(Codeblock("ansi", stdout[:MAX_OUTPUT_LENGTH_CHARS]))])
                if len(stdout) > MAX_OUTPUT_LENGTH_CHARS:
                    response.append("*(output truncated)*")
            if stderr:
                response.extend(["**stderr:**", str(Codeblock("ansi", stderr[:MAX_OUTPUT_LENGTH_CHARS]))])
                if len(stderr) > MAX_OUTPUT_LENGTH_CHARS:
                    response.append("*(error output truncated)*")

            await itx.followup.send("\n".join(response) or "✅ Script executed with no output", ephemeral=True)

        except ExecutionError as e:
            await itx.followup.send(f"❌ Execution failed: {e!s}", ephemeral=True)
        except Exception as e:  # noqa: BLE001
            await itx.followup.send(f"❌ An unexpected error occurred: {e!s}", ephemeral=True)


@app_commands.command()
@is_in_team()
async def execute(itx: Interaction) -> None:
    """Open the code execution modal."""
    assert itx.user.id in await itx.client.cachefetch_priority_ids()  # type: ignore[call-arg]
    await itx.response.send_modal(ExecModal(author_id=itx.user.id, salt=itx.id))


exports = BotExports(
    commands=[execute],
    raw_modal_submits={"exec": cast(type[RawSubmittable], ExecModal)},
)
