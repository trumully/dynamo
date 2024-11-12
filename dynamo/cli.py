import base2048

from dynamo.utils.helper import platformdir, resolve_path_with_links


def load_token() -> str | None:
    token_file_path = resolve_path_with_links(platformdir.user_config_path / "dynamo.token")
    with token_file_path.open(mode="r", encoding="utf-8") as fp:
        data = fp.read()
        return base2048.decode(data).decode("utf-8") if data else None


def store_token(token: str, /) -> None:
    token_file_path = resolve_path_with_links(platformdir.user_config_path / "dynamo.token")
    with token_file_path.open(mode="w", encoding="utf-8") as fp:
        fp.write(base2048.encode(token.encode()))


def get_token() -> str:
    if not (token := load_token()):
        msg = "Token not found. Please run `dynamo setup` before starting the bot."
        raise RuntimeError(msg) from None
    return token
