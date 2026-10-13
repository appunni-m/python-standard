# Get started

Standard is an alpha Python library published on [PyPI as `standard`](https://pypi.org/project/standard/); its Python package and command are named `std`. Install the public package or install the source checkout as shown below.

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

The current coordinated release is `0.2.3`. The core distribution does not
install optional integration packages unless you select an extra. You can also
install one provider directly with `python -m pip install standard-fastapi`.

## Install from this checkout

Run these commands from the repository root. Create and activate a virtual environment, then install the core package in editable mode:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

On Windows, activate the environment with `.venv\Scripts\activate` instead. Install a local integration project when you need it:

| Need | Install command |
| --- | --- |
| FastAPI | `python -m pip install -e . -e packages/standard-fastapi` |
| AWS | `python -m pip install -e . -e packages/standard-aws` |
| HTTP | `python -m pip install -e . -e packages/standard-http` |
| Redis cache | `python -m pip install -e . -e packages/standard-cache` |
| Relational databases | `python -m pip install -e . -e packages/standard-rdbms` |
| All providers | `python -m pip install -e . -e packages/standard-fastapi -e packages/standard-aws -e packages/standard-http -e packages/standard-cache -e packages/standard-rdbms` |

These commands install this checkout in editable mode. Use them when changing
Standard itself; application projects should normally install the published
distribution and the extras they use.

## Load a configuration file

Create `config/settings.yaml`:

```yaml
database:
  host: localhost
```

Read the nested value:

```python
from std.config import ConfigManager

config = ConfigManager.from_file("config/settings.yaml")
host = config.snapshot.get_path("database.host", "localhost")
print(host)
```

`from_file` accepts one YAML or TOML file, or a directory containing those files. Missing sources raise `MissingConfigSourceError` by default; pass `optional=True` only when a missing source is expected. See the [configuration reference](configuration/index.md) for merge and interpolation rules.

## Use Pydantic Settings

Create `config/app.yaml`:

```yaml
host: localhost
port: 8080
```

Then define a Settings class:

```python
from std.config import YamlSettings


class Settings(YamlSettings):
    std_config_file = "config/app.yaml"
    host: str
    port: int = 8080
```

Define this model in `core/settings.py`, then construct it once from `main.py`:

```python
from app.core.settings import Settings


def main() -> None:
    settings = Settings()
    # Build the application and inject its validated settings here.


if __name__ == "__main__":
    main()
```

`main.py` is the only place that calls `Settings()`. `YamlSettings` reads `settings.yaml` by default; `std_config_file` selects another file. `TomlSettings` works the same way and defaults to `settings.toml`. Both convenience bases use this source priority: constructor values, config file, process environment, dotenv, then file secrets. The first source has the highest priority. A custom `settings_customise_sources` hook can change that order.

## Configure application logging

`std.logging` uses environment-aware defaults and lets explicit settings
override the level and format independently:

```python
from std.logging import LoggingConfig, configure_logging

configure_logging(
    LoggingConfig(),
    environment="production",
    service_name="billing-api",
)
```

Development uses `DEBUG` and readable console output. Tests use `WARNING` and
console output. Staging and production use `INFO` and JSON lines. The default
stream is stdout; JSON records include timestamp, severity, logger, message,
environment, optional service/source fields, exception details, and
structured `extra` fields. See the [logging guide](logging.md) for YAML-backed
settings and custom formats.

## Agent commands

```bash
std guide
std guide --format json
std skill show
std skill install
```

The skill install command writes `.agents/skills/standard-idiomatic-python/SKILL.md` by default. The directory name matches the skill's required Agent Skills metadata. The command refuses to replace an existing file; pass `--force` to replace it or give another destination path. See the [CLI reference](api.md#agent-cli).

**Known issue in the published `0.2.3` package:** its installed skill contains
one stale sentence that describes `std.service` as unreleased, although
`std guide` correctly lists `std.service` as part of core. The source skill in
this repository is corrected; the PyPI copy will update with a future release.

## Current status

| Area | Status |
| --- | --- |
| Project and import names | Distribution: `standard`; Python import: `std`; command: `std` |
| Package layout | Core and CLI are under `src/std/`; FastAPI and AWS sources are under `packages/standard-fastapi/` and `packages/standard-aws/` |
| Python versions | CPython 3.11–3.14 are declared and configured in tox and CI |
| Test and benchmark commands | Unit, parity, Testcontainers consumer, and benchmark workflows are configured; see [testing](testing.md) for local evidence and environment limits |
| Documentation site | Zensical source and a GitHub Pages workflow are configured |
| PyPI | The current coordinated release is `0.2.3`; all six distributions share that version. |
| Hosted docs | Live at [appunni-m.github.io/python-standard](https://appunni-m.github.io/python-standard/); pushes to `main` deploy updates |
| Security reporting | GitHub private vulnerability reporting is enabled; use the **Report a vulnerability** button on the [Security Advisories page](https://github.com/appunni-m/python-standard/security/advisories) |

The repository's [publishing guide](publishing.md) lists all six distributions,
their import paths, and the shared tag release process. The [testing guide](testing.md)
distinguishes source-tree checks from consumer and release-artifact checks.

## Read the docs

- **Known** means supported by source code, project configuration, or a linked source.
- **Proposal** means a design option that has not been agreed.
- **Open** means an external setup task or project decision remains.
- **Measured** means the result has raw benchmark data and a reproducible setup.

Continue with the [configuration reference](configuration/index.md), [API reference](api.md), [testing and benchmarks](testing.md), or [contributing guide](contributing.md).
