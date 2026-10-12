# Get started

Standard is an alpha source checkout. The intended distribution name is `standard`, and the Python package imports as `std`. The current PyPI project page returned 404 during setup, while an indexed page still lists an older unrelated `standard` release. Confirm name ownership through PyPI before publishing or installing this project from the public index.

## Install from this checkout

Run these commands from the repository root. Create and activate a virtual environment, then install the core package in editable mode:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

On Windows, activate the environment with `.venv\Scripts\activate` instead. Add an integration extra when you need it:

| Need | Install command |
| --- | --- |
| FastAPI | `python -m pip install -e '.[fastapi]'` |
| AWS | `python -m pip install -e '.[aws]'` |
| Both | `python -m pip install -e '.[fastapi,aws]'` |

These commands install this checkout. Do not use `pip install standard` or `standard[...]` from PyPI until the requested distribution name is available for this project.

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


settings = Settings()
```

`YamlSettings` reads `settings.yaml` by default; `std_config_file` selects another file. `TomlSettings` works the same way and defaults to `settings.toml`. Both convenience bases use this source priority: constructor values, config file, process environment, dotenv, then file secrets. The first source has the highest priority. A custom `settings_customise_sources` hook can change that order.

## Agent commands

```bash
std guide
std guide --format json
std skill show
std skill install
```

The skill install command writes `.agents/skills/standard-python/SKILL.md` by default. It refuses to replace an existing file; pass `--force` to replace it or give another destination path. See the [CLI reference](api.md#agent-cli).

## Current status

| Area | Status |
| --- | --- |
| Project and import names | Distribution: `standard`; Python import: `std`; command: `std` |
| First release scope | Configuration, collection and file helpers, optional FastAPI and AWS integrations, and agent guidance are implemented under `src/std/` |
| Python versions | CPython 3.11–3.14 are declared and configured in tox and CI |
| Test and benchmark commands | Unit, parity, Testcontainers consumer, and benchmark workflows are configured; see [testing](testing.md) for local evidence and environment limits |
| Documentation site | Zensical source and a GitHub Pages workflow are configured |
| PyPI | Name availability and ownership must be confirmed before public release |
| Hosted docs | Live at [appunni-m.github.io/python-standard](https://appunni-m.github.io/python-standard/); pushes to `main` deploy updates |
| Security reporting | The repository owner still needs to configure a private reporting route |

Before an external release, confirm control of the `standard` distribution name and configure private vulnerability reporting. Do not publish under a substitute distribution name without an explicit project decision.

## Read the docs

- **Known** means supported by source code, project configuration, or a linked source.
- **Proposal** means a design option that has not been agreed.
- **Open** means an external setup task or project decision remains.
- **Measured** means the result has raw benchmark data and a reproducible setup.

Continue with the [configuration reference](configuration/index.md), [API reference](api.md), [testing and benchmarks](testing.md), or [contributing guide](contributing.md).
