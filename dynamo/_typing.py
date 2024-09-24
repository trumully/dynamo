from collections.abc import Callable, Coroutine
from typing import Any, ParamSpec, TypeVar

from discord.ext import commands

P = ParamSpec("P")
T = TypeVar("T")

AsyncCallable = TypeVar("AC", bound=Callable[P, Coroutine[Any, Any, T]])
CogT = TypeVar("CogT", bound=commands.Cog)
CommandT = TypeVar("CommandT", bound=commands.Command[CogT, P, T])
ContextT = TypeVar("ContextT", bound=commands.Context[Any], covariant=True)
