from dynamo.extensions.plugins import Plugin
from dynamo.typedefs import ContextT


class RootCommand(Plugin):
    @Plugin.Command(name="dynamo", invoke_without_command=True, ignore_extra=False)
    async def dynamo(self, ctx: ContextT) -> None:
        """All dev commands are registered here."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
