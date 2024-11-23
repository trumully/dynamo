import argparse
import os

from dynamo.config import config
from dynamo.runner import run_bot


def main() -> None:
    """Launch the bot."""
    os.umask(0o077)

    parser = argparse.ArgumentParser(description="Launch Dynamo")
    parser.add_argument(
        "--with-token",
        "-t",
        help="Run bot with token superseding current configuration",
        default=config.token,
        dest="token",
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Enable debug logging",
        dest="debug",
    )
    args = parser.parse_args()

    config.update({"token": args.token})

    run_bot(debug=args.debug)


if __name__ == "__main__":
    main()
