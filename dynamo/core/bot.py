from __future__ import annotations

import logging
import re
from importlib.util import find_spec
from pathlib import Path
from typing import Any, cast

import aiohttp
import apsw
import discord
from discord.ext import commands

from dynamo.core.context import Context
from dynamo.core.tree import Tree
from dynamo.typedefs import RawSubmittable
from dynamo.utils.helper import platformdir, resolve_path_with_links

log = logging.getLogger(__name__)

description = """
Quantum entanglement.
"""

modal_regex = re.compile(r"^m:(.{1,10}):(.*)$", flags=re.DOTALL)
button_regex = re.compile(r"^b:(.{1,10}):(.*)$", flags=re.DOTALL)


def _prefix_callable(bot: Dynamo, msg: discord.Message) -> list[str]:
    user_id = bot.user.id
    base = [f"<@{user_id}> ", f"<@!{user_id}> "]
    if msg.guild is None:
        base.extend(["d!", "d?"])
    else:
        base.extend(bot.prefixes.get(msg.guild.id, ["d!", "d?"]))
    return base


class Emojis(dict[str, str]):
    def __init__(self, emojis: list[discord.Emoji], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        for emoji in emojis:
            self[emoji.name] = f"<{"a" if emoji.animated else ""}:{emoji.name}:{emoji.id}>"


type Interaction = discord.Interaction["Dynamo"]


class Dynamo(commands.AutoShardedBot):
    session: aiohttp.ClientSession
    connector: aiohttp.TCPConnector
    conn: apsw.Connection
    context: Context
    logging_handler: Any
    bot_app_info: discord.AppInfo

    def __init__(self, connector: aiohttp.TCPConnector, conn: apsw.Connection, session: aiohttp.ClientSession) -> None:
        self.session = session
        self.conn = conn
        allowed_mentions = discord.AllowedMentions(roles=False, everyone=False, users=True)
        intents = discord.Intents(guilds=True, members=True, messages=True, message_content=True, presences=True)
        super().__init__(
            connector=connector,
            command_prefix=_prefix_callable,
            description=description,
            pm_help=None,
            help_attrs={"hidden": True},
            chunk_guilds_at_startup=False,
            heartbeat_timeout=150.0,
            allowed_mentions=allowed_mentions,
            intents=intents,
            enable_debug_events=True,
            tree_cls=Tree,
            activity=discord.Activity(name="The Cursed Apple", type=discord.ActivityType.watching),
        )
        self.raw_modal_submits: dict[str, RawSubmittable] = {}
        self.raw_button_submits: dict[str, RawSubmittable] = {}

    async def setup_hook(self) -> None:
        self.prefixes: dict[int, list[str]] = {}

        self.bot_app_info = await self.application_info()
        self.owner_id = self.bot_app_info.owner.id

        self.app_emojis = Emojis(await self.fetch_application_emojis())
        self.extension_files: dict[Path, float] = {}

        self.cog_spec = find_spec("dynamo.extensions.cogs")
        if self.cog_spec is None or self.cog_spec.origin is None:
            log.critical("Failed to find cog spec! Loading without cogs.")
            return

        all_cogs = Path(self.cog_spec.origin).parent
        for cog_path in all_cogs.rglob("**/*.py"):
            if cog_path.is_file() and not cog_path.name.startswith("_"):
                cog_name = self.get_cog_name(cog_path.stem)
                try:
                    await self.load_extension(cog_name)
                except commands.ExtensionError:
                    log.exception("Failed to load cog %s", cog_name)

        tree_path = resolve_path_with_links(platformdir.user_cache_path / "tree.hash")
        tree_hash = await self.tree.get_hash(self.tree)
        with tree_path.open("r+b") as fp:
            if fp.read() == tree_hash:
                return
            log.info("Syncing commands to dev guild (ID: %s)", self.dev_guild.id)
            self.tree.copy_global_to(guild=self.dev_guild)
            await self.tree.sync(guild=self.dev_guild)
            fp.seek(0)
            fp.write(tree_hash)

    def get_cog_name(self, name: str) -> str:
        return name.lower() if self.cog_spec is None else f"{self.cog_spec.name}.{name.lower()}"

    @property
    def owner(self) -> discord.User:
        return self.bot_app_info.owner

    @property
    def user(self) -> discord.ClientUser:
        return cast(discord.ClientUser, super().user)

    @property
    def tree(self) -> Tree:
        return cast(Tree, super().tree)

    @property
    def dev_guild(self) -> discord.Guild:
        return cast(discord.Guild, discord.Object(id=681408104495448088, type=discord.Guild))

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        return await super().start(token, reconnect=reconnect)

    async def close(self) -> None:
        await self.session.close()
        await super().close()

    async def on_ready(self) -> None:
        if not hasattr(self, "uptime"):
            self.uptime = discord.utils.utcnow()

        log.info("Ready: %s (ID: %s)", self.user, self.user.id)

    async def on_interaction(self, interaction: Interaction) -> None:
        for relevant_type, regex, mapping in (
            (discord.InteractionType.modal_submit, modal_regex, self.raw_modal_submits),
            (discord.InteractionType.component, button_regex, self.raw_button_submits),
        ):
            if interaction.type is relevant_type:
                assert interaction.data is not None
                custom_id = interaction.data.get("custom_id", "")
                if match := regex.match(custom_id):
                    modal_name, data = match.groups()
                    if rs := mapping.get(modal_name):
                        await rs.raw_submit(interaction, data)

    async def get_context[ContextT: commands.Context[Any]](
        self,
        origin: discord.Message | discord.Interaction,
        /,
        *,
        cls: type[ContextT] = Context,
    ) -> ContextT:
        return await super().get_context(origin, cls=cls)
