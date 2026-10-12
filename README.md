# Standard

**A small Python utility library with predictable behavior and agent-first guidance.**

The project and intended PyPI distribution are named `standard`; the Python import package and command are named `std`. Standard is currently an alpha source checkout. PyPI name ownership is unconfirmed: the project page returned 404 during setup, while an indexed page still lists an older unrelated project. Confirm the name is available and controlled by this project before publishing or recommending a public PyPI install.

The core provides YAML/TOML configuration, Pydantic Settings sources, immutable snapshots, recursive mapping helpers, and atomic text writes. FastAPI and AWS integrations are optional extras.

## Install from this checkout

Run these commands from the repository root. Choose one integration command if you need that extra; each installs this checkout and its dependencies.

| Need | Command | Import path |
| --- | --- | --- |
| Core only | `python -m pip install -e .` | `std` |
| FastAPI | `python -m pip install -e '.[fastapi]'` | `std.fastapi` |
| AWS | `python -m pip install -e '.[aws]'` | `std.aws` |
| Both integrations | `python -m pip install -e '.[fastapi,aws]'` | `std.fastapi`, `std.aws` |

The intended published install forms are `standard`, `standard[fastapi]`, and `standard[aws]`. They are not available for this project until the existing PyPI name is resolved.

## First use

Create `config/settings.yaml`:

```yaml
database:
  host: localhost
```

Then load a value from it:

```python
from std.config import ConfigManager

config = ConfigManager.from_file("config/settings.yaml")
host = config.snapshot.get_path("database.host", "localhost")
```

For Pydantic Settings, create `config/app.yaml`:

```yaml
host: localhost
port: 8080
```

```python
from std.config import YamlSettings


class Settings(YamlSettings):
    std_config_file = "config/app.yaml"
    host: str
    port: int = 8080


settings = Settings()
```

By default, Pydantic Settings resolves values in this order: constructor values, Standard config files, process environment, dotenv, and file secrets. Callers can change the order through Pydantic's `settings_customise_sources` hook.

## Agent guidance

```bash
std guide
std skill show
std skill install
```

`std guide` summarizes the library for coding agents. `std skill show` prints the packaged idiomatic-Python skill. `std skill install` writes it to `.agents/skills/standard-python/SKILL.md` and refuses to overwrite an existing file unless you pass `--force`.

The source repository contains the development checks, end-to-end tests, and full documentation site. The published distribution is intended to contain only the working library, its CLI, and the required package metadata, README, and license.
