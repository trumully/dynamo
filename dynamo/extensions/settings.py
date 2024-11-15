import apsw
import pytz
from discord.app_commands import Choice, Group, Range

from dynamo.bot import Interaction
from dynamo.types import BotExports
from dynamo.utils.cache import LRU, Trie

settings_group = Group(name="settings", description="Configure your settings")

_user_tz_lru: LRU[int, str] = LRU(128)


def get_timezone_from_user(conn: apsw.Connection, user_id: int) -> str:
    if (_tz := _user_tz_lru.get(user_id, None)) is not None:
        return _tz

    cursor = conn.cursor()
    # the update here is required for this to return
    # even when it already exists, but this is "free" still.
    row = cursor.execute(
        """
        INSERT INTO discord_users (user_id)
        VALUES (?)
        ON CONFLICT (user_id)
        DO UPDATE SET user_tz=user_tz
        RETURNING user_tz
        """,
        (user_id,),
    ).fetchone()
    assert row is not None
    return str(row[0])


@settings_group.command(name="timezone", description="Set your timezone")
async def set_timezone(itx: Interaction, timezone: Range[str, 1, 70]) -> None:
    send = itx.response.send_message

    # This is valid for but will be pointless for a user.
    if timezone == "local":
        await send(f"Invalid time zone: {timezone}", ephemeral=True)
        return

    try:
        pytz.timezone(timezone)
    except pytz.UnknownTimeZoneError:
        await send(f"Invalid time zone: {timezone}", ephemeral=True)
    else:
        conn: apsw.Connection = itx.client.conn
        cursor = conn.cursor()
        await itx.response.defer(ephemeral=True)
        cursor.execute(
            """
            INSERT INTO discord_users (user_id, user_tz) VALUES(?, ?)
            ON CONFLICT (user_id) DO UPDATE SET user_tz=excluded.user_tz
            """,
            (itx.user.id, timezone),
        )
        _user_tz_lru[itx.user.id] = timezone
        await itx.followup.send(f"Timezone set to {timezone}", ephemeral=True)


_timezone_trie: Trie = Trie()


def closest_zones(current: str) -> list[str]:
    if closest := _timezone_trie.search(current):
        return closest

    common_zones = pytz.common_timezones_set

    current_insensitive = current.casefold()
    zone_matches = {z for z in common_zones if z.casefold().startswith(current_insensitive)}
    return [*sorted(zone_matches)][:25] if len(zone_matches) > 25 else list(zone_matches)


@set_timezone.autocomplete("timezone")
async def autocomplete_timezone(itx: Interaction, current: str) -> list[Choice[str]]:
    return [Choice(name=z, value=z) for z in closest_zones(current)]


exports = BotExports([settings_group])
