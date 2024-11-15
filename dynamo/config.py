from dynaconf import Dynaconf, Validator


def valid_token(token: str) -> str:
    """
    Validate a discord bot token

    A discord bot token is a string that matches the following pattern:
    >>> "[M|N|O]XXXXXXXXXXXXXXXXXXXXXXX[XX].XXXXXX.XXXXXXXXXXXXXXXXXXXXXXXXXXX"

    See
    ---
    - https://discord.com/developers/docs/reference#authentication
    """
    import re

    pattern = re.compile(r"[MNO][a-zA-Z\d_-]{23,25}\.[a-zA-Z\d_-]{6}\.[a-zA-Z\d_-]{27}")
    if not bool(pattern.match(token)):
        msg = "Invalid token provided"
        raise RuntimeError(msg) from None
    return token


config = Dynaconf(envvar_prefix="DYNAMO", settings_files=["config.yaml"])

config.validators.register(
    Validator("token", must_exist=True, is_type_of=str, cast=valid_token),
)
