"""User beware!

This extension allows for execution of arbitrary code. Safety is not guaranteed.
Limited to authorized users only.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shlex
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

import discord
from base2048 import decode
from discord import app_commands
from msgspec import msgpack

from dynamo.types import BotExports, RawSubmittable
from dynamo.utils.format import code_block
from dynamo.utils.helper import b2048_pack

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dynamo.bot import Interaction

log = logging.getLogger(__name__)


def write_dependency_header(dependencies: Sequence[str]) -> str:
    """Write dependency header for an arbitrary script with proper formatting.

    >>> write_dependency_header(["requests<3", "rich"])
    # /// script
    # dependencies = [
    #   "requests<3",
    #   "rich",
    # ]
    # ///
    """
    formatted_deps = (
        f'# "{dependencies}",\n'
        if isinstance(dependencies, str)  # single dependency, dont iterate the string
        else "".join(f'#   "{dep}",\n' for dep in dependencies)
    )

    return f"# /// script\n# dependencies = [\n{formatted_deps}# ]\n# ///"


# Replace with your Discord user ID
EXECUTION_TIMEOUT: Final[int] = 30
MAX_OUTPUT_LENGTH: Final[int] = 1000


class ExecutionError(Exception):
    """Raised when code execution fails."""


async def execute_command(args: Sequence[str]) -> tuple[str, str]:
    """Execute a command asynchronously with timeout protection.

    Returns:
        Tuple of (stdout, stderr)
    """
    args = tuple(args)
    log.debug("$ %s", shlex.join(args))

    try:
        # Create process with limited environment
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=Path.cwd(),
            env={
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUNBUFFERED": "1",
                # Restrict environment variables
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "PYTHONPATH": "",
                # Add memory limit via Python interpreter
                "PYTHONMALLOC": "malloc",  # Use system allocator
                "PYTHONMEMLIMIT": str(512 * 1024 * 1024),  # 512MB limit
            },
            limit=512 * 1024 * 1024,  # subprocess memory limit (512MB)
        )

        async with asyncio.timeout(EXECUTION_TIMEOUT):
            stdout_bytes, stderr_bytes = await process.communicate()

        log.debug("Return code %d", process.returncode)

        # Explicitly decode bytes to str with error handling
        stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

        if process.returncode != 0:
            msg = f"Command failed with exit code {process.returncode}"
            raise ExecutionError(msg)

    except TimeoutError as exc:
        msg = f"Command timed out after {EXECUTION_TIMEOUT} seconds"
        raise ExecutionError(msg) from exc

    return stdout, stderr


async def execute_script(script: str, dependencies: Sequence[str]) -> tuple[str, str]:
    """Execute a Python script with safety checks."""
    # Add sandbox wrapper
    if not script.strip():
        msg = "Script cannot be empty"
        raise ExecutionError(msg)

    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".py", delete=False) as temp_file:
        if dependencies:
            temp_file.write(write_dependency_header(dependencies))
        temp_file.write(script)
        temp_file.flush()

        try:
            return await execute_command(["uv", "run", temp_file.name])
        finally:
            with contextlib.suppress(OSError):
                Path(temp_file.name).unlink()


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
        self, *, title: str = "Execute Python Code", timeout: float | None = 300, author_id: int, salt: int
    ) -> None:
        _id = b2048_pack((author_id, salt))
        custom_id = f"m:exec:{_id}"
        super().__init__(title=title, timeout=timeout, custom_id=custom_id)

    @staticmethod
    async def raw_submit(itx: Interaction, data: str) -> None:  # noqa: C901
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
        if script.startswith("```py"):
            script = script[5:-3] if script.endswith("```") else script[5:]
        elif script.startswith("```python"):
            script = script[9:-3] if script.endswith("```") else script[9:]

        # Parse dependencies
        deps = [dep.strip() for dep in dependencies_input.split(",") if dep.strip()]
        log.debug("dependencies: %s", deps)

        try:
            stdout, stderr = await execute_script(script, deps)

            # Format response
            response = []
            if stdout:
                response.extend(["**stdout:**", code_block(stdout[:MAX_OUTPUT_LENGTH], "ansi")])
                if len(stdout) > MAX_OUTPUT_LENGTH:
                    response.append("*(output truncated)*")
            if stderr:
                response.extend(["**stderr:**", code_block(stderr[:MAX_OUTPUT_LENGTH], "ansi")])
                if len(stderr) > MAX_OUTPUT_LENGTH:
                    response.append("*(error output truncated)*")

            await itx.followup.send("\n".join(response) or "✅ Script executed with no output", ephemeral=True)

        except ExecutionError as e:
            await itx.followup.send(f"❌ Execution failed: {e!s}", ephemeral=True)
        except Exception as e:  # noqa: BLE001
            await itx.followup.send(f"❌ An unexpected error occurred: {e!s}", ephemeral=True)


@app_commands.command()
@app_commands.check(lambda itx: itx.user.id == itx.client.owner_id)
async def execute(itx: Interaction) -> None:
    """Open the code execution modal."""
    assert itx.user.id == itx.client.owner_id, "Nope."
    await itx.response.send_modal(ExecModal(author_id=itx.user.id, salt=itx.id))


exports = BotExports([execute], {"exec": cast(type[RawSubmittable], ExecModal)})
