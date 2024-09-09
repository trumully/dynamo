# Dynamo
Personal use bot.

## Setup
### Prerequisites
`poetry` is required to set up Dynamo. Find installation instructions [here](https://python-poetry.org/docs/)
### Installing
#### Clone the repository:
```shell
git clone https://github.com/trumully/Dynamo
```
#### Install and run:
```shell
poetry install
poetry run dynamo setup
poetry run dynamo
```

## Development
### Install dev dependencies
```shell
poetry install --with=dev
```
### Run tests
#### CLI
```shell
poetry run pytest tests --asyncio-mode=strict
```
#### VSCode
1. Open VSCode debugger `Ctrl+Shift+D`
2. Run `Dynamo Tests` preset

**or**

1. Open Command Palette `Ctrl+Shift+P`
2. Search and run: `Tests: Run All Tests`
