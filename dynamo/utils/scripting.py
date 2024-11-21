import asyncio
import contextlib
import logging
import shlex
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

log = logging.getLogger(__name__)

type CommandOutput = tuple[str, str]  # (stdout, stderr)

EXECUTION_TIMEOUT_SECONDS: Final[int] = 30
MAX_OUTPUT_LENGTH_CHARS: Final[int] = 1000
MEMORY_LIMIT_BYTES: Final[int] = 512 * 1024 * 1024  # 512MB


def write_dependency_header(dependencies: Sequence[str]) -> str:
    """Write dependency header for an arbitrary script with proper formatting.

    >>> write_dependency_header(["requests<3", "rich"])
    ... # /// script
    ... # dependencies = [
    ... #   "requests<3",
    ... #   "rich",
    ... # ]
    ... # ///
    """
    formatted_deps = (
        f'# "{dependencies}",\n'
        if isinstance(dependencies, str)  # single dependency, dont iterate the string
        else "".join(f'#   "{dep}",\n' for dep in dependencies)
    )

    return f"# /// script\n# dependencies = [\n{formatted_deps}# ]\n# ///"


@dataclass(frozen=True)
class ExecutionEnvironment:
    """Immutable configuration for script execution environment."""

    encoding: str = "utf-8"
    path: str = "/usr/local/bin:/usr/bin:/bin"
    memory_limit: int = MEMORY_LIMIT_BYTES

    def to_env_dict(self) -> dict[str, str]:
        """Convert settings to environment variables dictionary."""
        return {
            "PYTHONIOENCODING": self.encoding,
            "PYTHONUNBUFFERED": "1",
            "PATH": self.path,
            "PYTHONPATH": "",
            "PYTHONMALLOC": "malloc",
            "PYTHONMEMLIMIT": str(self.memory_limit),
        }


class ExecutionError(Exception):
    """Raised when code execution fails."""


async def execute_command(args: Sequence[str], env: ExecutionEnvironment | None = None) -> CommandOutput:
    """Execute a command asynchronously with timeout protection.

    Args:
        args: Command and its arguments
        env: Optional custom execution environment

    Returns:
        Tuple of (stdout, stderr)

    Raises:
        ExecutionError: If command fails or times out
    """
    args = tuple(args)
    env = env or ExecutionEnvironment()
    log.debug("$ %s", shlex.join(args))

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=Path.cwd(),
            env=env.to_env_dict(),
            limit=env.memory_limit,
        )

        async with asyncio.timeout(EXECUTION_TIMEOUT_SECONDS):
            stdout_bytes, stderr_bytes = await process.communicate()

        log.debug("Return code %d", process.returncode)

        # Explicitly decode bytes to str with error handling
        stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

        if process.returncode != 0:
            msg = f"Command failed with exit code {process.returncode}"
            raise ExecutionError(msg)

    except TimeoutError as exc:
        msg = f"Command timed out after {EXECUTION_TIMEOUT_SECONDS} seconds"
        raise ExecutionError(msg) from exc

    return stdout, stderr


async def execute_script(script: str, dependencies: Sequence[str]) -> CommandOutput:
    """Execute a Python script with safety checks.

    Args:
        script: Python code to execute
        dependencies: List of package dependencies

    Returns:
        Tuple of (stdout, stderr)

    Raises:
        ExecutionError: If script is empty or execution fails
    """
    script = script.strip()
    if not script:
        msg = "Script cannot be empty"
        raise ExecutionError(msg)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", encoding="utf-8", delete=False) as temp_file:
        temp_file.write(write_dependency_header(dependencies) + script if dependencies else script)
        temp_path = Path(temp_file.name)

    try:
        return await execute_command(["uv", "run", str(temp_path)])
    finally:
        with contextlib.suppress(OSError):
            temp_path.unlink()
