from __future__ import annotations

import importlib
import inspect
import logging
import sys
import traceback
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, cast

import discord

from dynamo.extensions.plugins import Plugin
from dynamo.extensions.plugins.utils.context import copy_context_with
from dynamo.typedefs import ContextT, CoroFunction
from dynamo.utils.format import code_block

if TYPE_CHECKING:
    from dynamo import Dynamo

log = logging.getLogger(__name__)


class DebugPlugin(Plugin):
    """Debug tools for development and troubleshooting."""

    _trace_output: ClassVar[list[str]] = []

    @Plugin.Command(parent="dynamo", name="inspect")
    async def inspect(self, ctx: ContextT, target: str) -> None:
        """Inspect bot internals safely.

        Parameters
        ----------
        target : str
            The object to inspect. Can be:
            - 'cogs': List loaded cogs
            - 'commands': List all commands
            - 'extensions': List loaded extensions
        """
        inspection_methods: Mapping[str, CoroFunction[[], str]] = {
            "cogs": self._inspect_cogs,
            "commands": self._inspect_commands,
            "extensions": self._inspect_extensions,
        }

        if target not in inspection_methods:
            valid_targets = ", ".join(f"`{t}`" for t in inspection_methods)
            await ctx.send(f"Invalid target. Valid targets are: {valid_targets}")
            return

        result = await inspection_methods[target]()
        await ctx.send(code_block(result, line_numbers=True))

    async def _inspect_cogs(self) -> str:
        """Get information about loaded cogs."""
        lines: Sequence[str] = []
        for name, cog in self.bot.cogs.items():
            lines.append(f"Cog: {name}")
            lines.append(f"  Type: {type(cog).__name__}")
            lines.append(f"  Commands: {len(cog.get_commands())}")
            lines.append(f"  Listeners: {len(cog.get_listeners())}")
            lines.append("")
        return "\n".join(lines)

    async def _inspect_commands(self) -> str:
        """Get information about registered commands."""
        lines: Sequence[str] = []
        for cmd in self.bot.walk_commands():
            lines.append(f"Command: {cmd.qualified_name}")
            lines.append(f"  Cog: {cmd.cog_name}")
            lines.append(f"  Enabled: {cmd.enabled}")
            lines.append(f"  Hidden: {cmd.hidden}")
            lines.append("")
        return "\n".join(lines)

    async def _inspect_extensions(self) -> str:
        """Get information about loaded extensions."""
        lines: Sequence[str] = []
        for name, ext in self.bot.extensions.items():
            lines.append(f"Extension: {name}")
            lines.append(f"  Module: {ext.__name__}")
            lines.append(f"  File: {inspect.getfile(ext)}")
            lines.append("")
        return "\n".join(lines)

    @Plugin.Command(parent="dynamo", name="trace")
    async def trace(self, ctx: ContextT, *, command_string: str) -> None:
        """Trace command execution flow.

        Parameters
        ----------
        command_string : str
            The command to trace (including prefix)
        """
        # Create a trace context
        trace_ctx = await copy_context_with(ctx, content=command_string)

        # Set up tracing
        sys.settrace(self._trace_callback)

        try:
            # Execute the command
            await self.bot.invoke(trace_ctx)
        finally:
            # Clean up tracing
            sys.settrace(None)

        # Send collected trace info
        if self._trace_output:
            trace_text = "\n".join(self._trace_output)
            await ctx.send(code_block(trace_text, lang="py"))
        else:
            await ctx.send("No trace output collected.")

    def _trace_callback(self, frame: Any, event: str, arg: Any) -> Any:
        """Callback for system tracer."""
        if event == "call":
            code = frame.f_code
            # Only trace our own code
            if "site-packages" not in code.co_filename:
                self._trace_output.append(f"Calling {code.co_name} in {code.co_filename}:{frame.f_lineno}")
        return self._trace_callback

    @Plugin.Command(parent="dynamo", name="memory")
    async def memory(self, ctx: ContextT) -> None:
        """Show memory usage statistics."""
        psutil = importlib.import_module("psutil")

        process = psutil.Process()
        memory_info = process.memory_info()

        embed = discord.Embed(title="Memory Usage", color=discord.Color.blue())
        embed.add_field(name="RSS", value=f"{memory_info.rss / 1024 / 1024:.2f} MB", inline=True)
        embed.add_field(name="VMS", value=f"{memory_info.vms / 1024 / 1024:.2f} MB", inline=True)

        await ctx.send(embed=embed)

    @Plugin.Command(parent="dynamo", name="objects")
    async def objects(self, ctx: ContextT) -> None:
        """Show counts of tracked Discord objects."""
        stats = {
            "Guilds": len(self.bot.guilds),
            "Users": len(self.bot.users),
            "Text Channels": sum(1 for g in self.bot.guilds for c in g.channels if isinstance(c, discord.TextChannel)),
            "Voice Channels": sum(
                1 for g in self.bot.guilds for c in g.channels if isinstance(c, discord.VoiceChannel)
            ),
            "Emojis": len(self.bot.emojis),
        }

        embed = discord.Embed(title="Discord Object Counts", color=discord.Color.blue())
        for name, count in stats.items():
            embed.add_field(name=name, value=str(count), inline=True)

        await ctx.send(embed=embed)

    @Plugin.Command(parent="dynamo", name="error")
    async def error(self, ctx: ContextT) -> None:
        """Show the last error traceback."""
        bot = cast("Dynamo", ctx.bot)

        if not hasattr(bot, "_last_error"):
            await ctx.send("No errors recorded.")
            return

        error: BaseException | None = bot._last_error  # type: ignore
        if error is None:
            await ctx.send("No errors recorded.")
            return

        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        await ctx.send(code_block(tb, lang="py"))
