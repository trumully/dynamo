from __future__ import annotations

from dynaconf import Dynaconf, Validator


def valid_token(token: str) -> bool:
    """Validate a discord bot token.

    A discord bot token is a string that matches the following pattern:
    >>> "[M|N|O]XXXXXXXXXXXXXXXXXXXXXXX[XX].XXXXXX.XXXXXXXXXXXXXXXXXXXXXXXXXXX"

    See
    ---
    - https://discord.com/developers/docs/reference#authentication
    """
    import re

    pattern = re.compile(r"[MNO][a-zA-Z\d_-]{23,25}\.[a-zA-Z\d_-]{6}\.[a-zA-Z\d_-]{27}")
    return bool(pattern.match(token))


config = Dynaconf(
    envvar_prefix="DYNAMO",
    settings_files=[".secrets.toml"],
    validators=[Validator("token", must_exist=True, is_type_of=str, condition=valid_token)],
)


config.validators.validate()


def get_token() -> str:
    if not valid_token(config.token):
        msg = "An invalid token was provided. Please check your .secrets.toml file or if you provided a correct token with --token."
        raise RuntimeError(msg) from None

    return str(config.token)
