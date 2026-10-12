# Standard

**A small Python utility library with predictable behavior and agent-first guidance.**

The project and PyPI distribution are named `standard`; the Python import package and command are named `std`. Standard is an alpha Python library published on [PyPI](https://pypi.org/project/standard/). Read the [documentation site](https://appunni-m.github.io/python-standard/) for the full user guide and API reference.

## Documentation map

- [Get started](docs/get-started.md) — installation and first configuration examples.
- [API reference](docs/api.md) — supported modules, classes, and CLI behavior.
- [Architecture decisions](docs/decisions/index.md) — module boundaries, configuration lifecycle, and deferred design questions.
- [Configuration contract](docs/configuration/index.md) — merge, interpolation, source priority, and error behavior.
- [Logging guide](docs/logging.md) — environment defaults, console/JSON formats, and custom options.
- [HTTP client guide](docs/http.md) — async requests, authentication, retries, and response models.
- [Redis cache guide](docs/cache.md) — cache helpers, decorators, and distributed locks.
- [Relational database guide](docs/rdbms.md) — async SQLAlchemy sessions for SQLite, PostgreSQL, and MySQL.
- [Testing and benchmarks](docs/testing.md) — local checks, Testcontainers, parity, and measurement limits.
- [Changelog](docs/changelog.md) — user-visible changes by release.
- [FastAPI app template](templates/fastapi-app/README.md) — a copyable, feature-first layout with co-located module code, YAML settings, startup injection, and lifecycle wiring.
- [Contributing](CONTRIBUTING.md) · [Security policy](SECURITY.md) · [MIT license](LICENSE).

## Install from PyPI

```bash
python -m pip install standard
python -m pip install 'standard[fastapi]'
python -m pip install 'standard[aws]'
python -m pip install 'standard[http]'
python -m pip install 'standard[cache]'
python -m pip install 'standard[rdbms]'
python -m pip install 'standard[fastapi,aws,http,cache,rdbms]'
```

The core provides YAML/TOML configuration, Pydantic Settings sources, immutable snapshots, recursive mapping helpers, atomic text writes, environment-aware logging, async service lifecycle management, and the `std` CLI. FastAPI, AWS, HTTP, cache, and RDBMS are separate integration distributions. The published `standard` 0.1.1 still bundles FastAPI and AWS; the unreleased source splits all integrations and will publish them together at one version from a shared `vX.Y.Z` tag. The extras shown above become installable from PyPI after that coordinated release.

## Install from this checkout

Run these commands from the repository root. The integration source projects are installed alongside core in editable mode.

| Need | Command | Import path |
| --- | --- | --- |
| Core only | `python -m pip install -e .` | `std` |
| FastAPI | `python -m pip install -e . -e packages/standard-fastapi` | `std.fastapi` |
| AWS | `python -m pip install -e . -e packages/standard-aws` | `std.aws` |
| HTTP | `python -m pip install -e . -e packages/standard-http` | `std.http` |
| Redis cache | `python -m pip install -e . -e packages/standard-cache` | `std.cache` |
| Relational databases | `python -m pip install -e . -e packages/standard-rdbms` | `std.rdbms` |
| All providers | `python -m pip install -e . -e packages/standard-fastapi -e packages/standard-aws -e packages/standard-http -e packages/standard-cache -e packages/standard-rdbms` | All provider modules |

The source tree's `standard[fastapi]`, `standard[aws]`, `standard[http]`, `standard[cache]`, and `standard[rdbms]` extras select those standalone distributions. They become installable from PyPI after the matching projects are published; see the [publishing guide](docs/publishing.md).

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

Define a Pydantic Settings model in `core/settings.py`:

```python
from std.config import YamlSettings


class Settings(YamlSettings):
    std_config_file = "config/app.yaml"
    host: str
    port: int = 8080
```

In `main.py`, construct the model once and use it to build the application:

```python
from app.core.settings import Settings


def main() -> None:
    settings = Settings()
    # Build the application and inject its validated settings here.


if __name__ == "__main__":
    main()
```

Call `Settings()` only from the application entry point. By default, Pydantic Settings resolves values in this order: constructor values, Standard config files, process environment, dotenv, and file secrets. Callers can change the order through Pydantic's `settings_customise_sources` hook.

## Agent guidance

```bash
std guide
std guide --format json
std skill show
std skill install
```

`std guide` summarizes the supported library surface for coding agents. `std guide --format json` emits schema-versioned install, module, command, and documentation data. `std skill show` prints the packaged idiomatic-Python skill. `std skill install` writes it to `.agents/skills/standard-idiomatic-python/SKILL.md` and refuses to overwrite an existing file unless you pass `--force`.

The source repository contains the development checks, end-to-end tests, and full documentation site. The published distribution is intended to contain only the working library, its CLI, and the required package metadata, README, and license.
