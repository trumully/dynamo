from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from typing import TYPE_CHECKING, Any, Concatenate, cast

from discord.ext import commands

if TYPE_CHECKING:
    from dynamo.typedefs import BotT, ContextA, Coro


type _ConvertedCommand = "commands.Command[Plugin, ..., Any]"
type _BaseCommand = "Plugin.Command[Plugin, ..., Any]"
type PluginT = Plugin


class Plugin(commands.Cog):
    """Base class defining plugins for Dynamo dev cog."""

    class Command[PluginT: Plugin, **P, T]:
        """
        An intermediary class for Plugin commands.
        Instances of this class are converted to commands.Command or commands.Group instances inside a Plugin.

        Parameters
        ----------
        parent: str | None
            The name of the parent command.
        standalone_ok: bool
            Whether the command can be used without the parent command.
        """

        def __init__(
            self,
            parent: str | None = None,
            standalone_ok: bool = False,
            *args: Any,
            **kwargs: Any,
        ):
            self.parent: str | None = parent
            self.parent_instance: _BaseCommand | None = None
            self.standalone_ok: bool = standalone_ok
            self.kwargs = kwargs
            self.callback: Callable[Concatenate[PluginT, ContextA, P], Coro[T]] | None = None
            self.depth: int = 0
            self.has_children: bool = False

        def __call__(
            self,
            callback: Callable[Concatenate[PluginT, ContextA, P], Coro[T]],
        ) -> Plugin.Command[PluginT, P, T]:
            self.callback = callback
            return self

        def convert(self, association_map: Mapping[_BaseCommand, _ConvertedCommand]) -> commands.Command[PluginT, P, T]:
            """Attempt to convert the command to a commands.Command or commands.Group instance."""
            if self.parent:
                if not self.parent_instance:
                    msg = "Plugin command declared as having a parent was attempted to be converted before its parent."
                    raise RuntimeError(msg) from None

                parent = association_map[self.parent_instance]

                if not isinstance(parent, commands.Group):
                    msg = "Plugin command declared as a parent was associated with a non-group."
                    raise TypeError(msg) from None

                command_type = parent.group if self.has_children else parent.command
            else:
                command_type = commands.group if self.has_children else commands.command

            if not self.callback:
                msg = "Plugin command attempted to be converted without a callback."
                raise RuntimeError(msg) from None

            return cast(commands.Command[PluginT, P, T], command_type(**self.kwargs)(self.callback))

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.bot: BotT = kwargs.pop("bot")

        command_lookup: MutableMapping[str, Plugin.Command[PluginT, ..., Any]] = {}

        for cls in reversed(type(self).__mro__):
            for key, cmd in cls.__dict__.items():
                if isinstance(cmd, Plugin.Command):
                    command_lookup[key] = cmd

        command_set = list(command_lookup.items())

        # Associate commands with their parents
        for key, cmd in command_set:
            cmd.parent_instance = None
            cmd.depth = 0

            if cmd.parent:
                if cmd.standalone_ok:
                    cmd.parent_instance = command_lookup.get(cmd.parent, None)
                else:
                    try:
                        cmd.parent_instance = command_lookup[cmd.parent]
                    except KeyError as exception:
                        msg = f"Couldn't associate plugin command {key} with parent {cmd.parent}."
                        raise RuntimeError(msg) from exception

            if cmd.callback is None:
                msg = f"Plugin command {key} has no callback."
                raise RuntimeError(msg) from None

        # Assign depth and has_children
        for _, cmd in command_set:
            parent = cmd.parent_instance
            while parent:
                parent.has_children = True
                cmd.depth += 1
                parent = parent.parent_instance

        command_set.sort(key=lambda c: c[1].depth)
        association_map: MutableMapping[Plugin.Command[PluginT, ..., Any], commands.Command[PluginT, ..., Any]] = {}
        self.plugin_commands: MutableMapping[str, commands.Command[PluginT, ..., Any]] = {}

        for key, cmd in command_set:
            association_map[cmd] = target_cmd = cmd.convert(association_map)
            target_cmd.cog = self
            self.plugin_commands[key] = target_cmd
            setattr(self, key, target_cmd)

        self.__cog_commands__ = [*self.__cog_commands__, *self.plugin_commands.values()]

        super().__init__(*args, **kwargs)

    async def cog_check(self, ctx: ContextA) -> bool:  # pyright: ignore[reportIncompatibleMethodOverride]
        if not await ctx.bot.is_owner(ctx.author):
            msg = "You are not the owner of the bot."
            raise commands.NotOwner(msg)

        return True
