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

- Python >=3.13
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### Clone the repository

```shell
git clone https://github.com/trumully/dynamo.git
```

### Install and run

Don't forget to set up your `.secrets.toml` file (see the `secrets-example.toml`)

```shell
cd dynamo
uv sync
uv run dynamo
```

## Debug mode

```shell
uv run dynamo --debug
```
