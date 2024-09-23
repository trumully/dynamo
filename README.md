<p align="center">
<a href="" rel="noopener"><img src="assets/images/dynamo.png" alt="Dynamo" height="400"></a>
</p>
<h3 align="center">Dynamo</h3>

<div align="center"></div>

<p align="center">Personal use bot
    <br>
</p>

---

## Setup <a name="setup"></a>
### Prerequisites
* Python >=3.12
* [Poetry](https://python-poetry.org)

### Clone the repository:
```shell
git clone https://github.com/trumully/dynamo.git
```

### Install and run:
```shell
cd dynamo
poetry install
poetry run dynamo setup
poetry run dynamo
```
> [!TIP]
> To stop the bot, press `Ctrl+C` or use the `d!quit` command.

## Development <a name="development"></a>
### Install dev dependencies
```shell
poetry install --with=dev
```

### Debug mode
```shell
poetry run dynamo --debug
```

> [!TIP]
> Run `d!reload <module>` to hot reload a module or `d!reload all` to hot reload all modules and utilities.


### Run tests
```shell
poetry run pytest tests --asyncio-mode=strict -n logical
```
