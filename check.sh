#!/bin/bash

set -euxo pipefail

uv sync --all-extras --dev
uv run ruff check --config ./pyproject.toml --output-format github
uv run pytest tests --asyncio-mode=strict -n logical
