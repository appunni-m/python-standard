# API reference

## Public modules

| Module or command | Availability | Purpose |
| --- | --- | --- |
| `std.config` | Core | YAML/TOML loading, Pydantic Settings sources, and immutable snapshots |
| `std.collections` | Core | Nested mapping merge and path helpers |
| `std.files` | Core | Atomic text-file replacement |
| `std` command | Core | Agent guidance and the packaged Python skill |
| `std.fastapi` | `fastapi` extra | FastAPI dependency for a Pydantic Settings model |
| `std.aws` | `aws` extra | AWS Secrets Manager loader and Pydantic source |

The checkout can install its extras with `python -m pip install -e '.[fastapi]'` or `python -m pip install -e '.[aws]'`. Confirm the current availability and ownership of the public PyPI name `standard` before publishing; see [getting started](get-started.md#current-status).

## Configuration

```python
from std.config import ConfigManager

manager = ConfigManager.from_files("config/base.yaml", "config/local.toml")
snapshot = manager.snapshot
host = snapshot.get_path("database.host", "localhost")
updated = manager.reload()
```

- `ConfigManager.from_file(path, *, optional=False, environ=None)` loads one YAML/TOML file or recursively reads a directory of supported files.
- `ConfigManager.from_files(*paths, optional=False, environ=None)` composes files and directories in argument order. Files discovered inside each directory are sorted by normalized relative POSIX path.
- `ConfigManager.snapshot` returns the current immutable `ConfigSnapshot`.
- `ConfigManager.reload(*, environ=None)` parses a complete candidate and publishes it atomically. It returns the new snapshot; if parsing fails, the previous snapshot remains current. An explicit `environ` mapping applies to that reload only.
- `ConfigSnapshot.get_path(path, default=None)` reads a dotted string or a sequence of string path segments. A missing segment returns `default`.
- `ConfigSnapshot.to_dict()` returns an independent mutable copy. Nested mappings become dictionaries, sequences become lists, and frozen sets become sets.

Paths accept strings or `os.PathLike` values. A missing source raises `MissingConfigSourceError` unless `optional=True`; optional mode skips missing paths. An existing directory with no YAML/TOML files is empty. `from_files()` without paths raises `ValueError`.

The merge rules are: recursively merge mappings, append lists, and replace other conflicts with the later value. YAML and TOML string values support `${NAME}`, `${NAME:-default}`, and `$$` interpolation. An unset required variable or invalid placeholder raises `ConfigInterpolationError`.

### Errors

`ConfigError` is the public base class and exposes optional `source` and `location` attributes. Its subclasses identify the failure:

- `MissingConfigSourceError`: a required file or directory is missing.
- `ConfigFormatError`: a file cannot be read or parsed, its root is not a mapping, or its format is unsupported.
- `ConfigInterpolationError`: a placeholder is malformed, unset, or cyclic.

Errors include the source path and location when available. Interpolation and parser errors do not include configuration or environment values.

### Pydantic Settings

```python
from std.config import YamlSettings


class Settings(YamlSettings):
    std_config_file = "settings.yaml"
    service_name: str
    port: int = 8080
```

`YamlSettings` reads `settings.yaml` by default; `TomlSettings` reads `settings.toml`. Set `std_config_file` to choose another file or directory, and set `std_config_optional = True` only when it is valid for the source to be missing. Both bases order Pydantic sources as init kwargs, config files, process environment, dotenv, and file secrets. The first source has the highest priority.

The source classes are also public:

- `ConfigSettingsSource(settings_cls, *paths, optional=False, allowed_extensions=None)` accepts YAML and TOML by default.
- `YamlSettingsSource(settings_cls, *paths, optional=False)` accepts `.yaml` and `.yml` files.
- `TomlSettingsSource(settings_cls, *paths, optional=False)` accepts `.toml` files.

Each source returns the loaded mapping to Pydantic Settings. Use one in `settings_customise_sources` when a Settings class needs its own file path or source priority.

## Collections and files

- `std.collections.deep_merge(*mappings)` recursively merges mappings, appends lists, replaces other conflicts with later values, and does not mutate the inputs. Values in the result are independent copies. With no inputs, it returns `{}`.
- `std.collections.get_path(mapping, path, default=None)` reads nested mappings. For a dotted string, empty path segments are ignored; a missing segment returns `default`.
- `std.collections.set_path(mapping, path, value)` mutates the supplied dictionary, creating intermediate dictionaries. The path must contain at least one non-empty string segment. It raises `ValueError` for an empty/invalid path and `TypeError` if it must descend through a non-dictionary value.
- `std.files.atomic_write_text(path, text, *, encoding="utf-8", mode=0o600, create_parents=False)` returns the target `Path` after writing a temporary sibling, flushing it, and atomically replacing the destination. Parent directories must already exist unless `create_parents=True`. The default mode is owner-only; set `mode` to choose another permission mode.

## Optional integrations

### FastAPI

Install the `fastapi` extra before importing `std.fastapi`:

```python
from fastapi import FastAPI
from std.config import YamlSettings
from std.fastapi import settings_dependency

app = FastAPI()


class Settings(YamlSettings):
    std_config_file = "settings.yaml"
    service_name: str


@app.get("/health")
def health(settings: Settings = settings_dependency(Settings)):
    return {"service": settings.service_name}
```

`settings_dependency(settings_type)` requires a `BaseSettings` subclass and returns a FastAPI dependency. FastAPI caches the dependency once per request by default. Use `app.dependency_overrides` when tests or the application need a replacement.

### AWS Secrets Manager

Install the `aws` extra before importing `std.aws`:

```python
from std.aws import load_secret

settings_values = load_secret("my-service/settings", region_name="eu-west-1")
```

`load_secret(secret_id, *, region_name=None, client=None)` accepts a non-empty secret ID and returns a dictionary parsed from a JSON object in `SecretString` or UTF-8 `SecretBinary`. It rejects duplicate object keys, non-standard `NaN`/`Infinity` values, and non-object payloads. `ValueError` indicates an empty ID; `AwsSecretError` indicates a retrieval or payload failure. Failure messages do not expose the secret ID or response details. Pass `client` to use an existing or test client; otherwise the integration creates a boto3 Secrets Manager client with the optional region.

`AwsSecretsManagerSettingsSource(settings_cls, secret_id, *, region_name=None, client=None)` loads the secret as a Pydantic Settings source when Pydantic reads it. AWS credentials, region policy, and refresh lifecycle remain with the application.

## Agent CLI

```text
std --version
std guide [--format text|json]
std skill show
std skill path
std skill install [destination] [--force]
```

`std guide` prints concise usage instructions; `--format json` prints a JSON object containing the distribution name, import name, version, and guide. `std skill show` prints the packaged idiomatic-Python skill. `std skill path` prints the path to that resource. `std skill install` copies it into the current repository at `.agents/skills/standard-python/SKILL.md` by default. It returns status 2 and refuses to overwrite an existing file unless `--force` is supplied; filesystem failures return status 1.
