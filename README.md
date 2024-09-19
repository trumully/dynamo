# Dynamo
Personal use bot.

## Setup
### Prerequisites
`poetry` is required to set up Dynamo. Find installation instructions [here](https://python-poetry.org/docs/)
### Installing
#### Clone the repository:
```shell
git clone https://github.com/trumully/dynamo.git
```
#### Install and run:
```shell
cd dynamo
poetry install
poetry run dynamo setup
poetry run dynamo
```

## Development
### Install dev dependencies
```shell
poetry install --with=dev
```

### Run bot in debug mode
```shell
poetry run dynamo --debug
```

### Run tests
> [!NOTE]
> Running tests from the CLI is recommended

#### CLI (recommended)
```shell
poetry run pytest tests --asyncio-mode=strict -n logical
```
#### VSCode
1. Open VSCode debugger `Ctrl+Shift+D`
2. Run `Dynamo Tests` preset

**or**

1. Open Command Palette `Ctrl+Shift+P`
2. Search and run: `Tests: Run All Tests`
