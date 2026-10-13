# API reference

## Public modules

| Module or command | Availability | Purpose |
| --- | --- | --- |
| `std.__version__` | Core | Installed distribution version string |
| `std.config` | Core | YAML/TOML loading, Pydantic Settings sources, and immutable snapshots |
| `std.collections` | Core | Nested mapping merge and path helpers |
| `std.files` | Core | Atomic text-file replacement |
| `std.logging` | Core | Environment-aware standard logging presets and structured JSON output |
| `std.service` | Core | Async service lifecycle and managed background tasks |
| `std` command | Core | Agent guidance and the packaged Python skill |
| `std.fastapi` | `standard-fastapi` or `standard[fastapi]` | App setup, lifecycle, token auth, health checks, request logging, and Pydantic Settings dependencies |
| `std.aws` | `standard-aws` or `standard[aws]` | AWS Secrets Manager loader and Pydantic source |
| `std.http` | `standard-http` or `standard[http]` | Async HTTPX client, retries, response models, and authentication |
| `std.cache` | `standard-cache` or `standard[cache]` | Redis client, sync/async cache decorators, and distributed locks |
| `std.rdbms` | `standard-rdbms` or `standard[rdbms]` | Async SQLAlchemy database managers for SQLite, PostgreSQL, and MySQL |

The current coordinated release is `0.2.3`; each integration has its own
distribution and matching convenience extra. Install `standard` for core APIs,
then select only the provider packages your application uses. From a checkout,
install core plus the relevant `packages/standard-*` project in editable mode.
See [current release status](index.md#current-release) and
[publishing](publishing.md) for distribution links and release details. The focused guides cover
[HTTP](http.md), [Redis cache](cache.md), and
[relational databases](rdbms.md).

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
- `ConfigSnapshot.revision` starts at `1` and increments after each successful reload.
- `ConfigSnapshot.sources` is a tuple of the source file paths used to build that snapshot. Directory inputs expand to their matched YAML/TOML files in merge order.
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

Define the application's settings aggregate in `core/settings.py`:

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

## Logging

`std.logging.LoggingEnvironment`, `LoggingLevel`, and `LoggingFormat` describe
the supported values. `LoggingConfig` validates environment-independent
formatter, stream, color, source, and named-logger options. Its `format` field
accepts `auto`, `console`, `json`, or `custom`; custom formatting requires a
formatter string and supports the standard `%`, `{`, and `$` styles.

`configure_logging(config=None, *, environment="development", service_name=None)`
configures the process root logger. Environment defaults are `DEBUG` plus
console in development, `WARNING` plus console for tests, and `INFO` plus JSON
for staging and production. Explicit `level` and `format` settings override
those defaults independently. Logs go to stdout by default; the config can
select stderr. Existing loggers stay enabled. See the [logging guide](logging.md)
for YAML, JSON fields, overrides, and security considerations.

## Services

`std.service.Service` provides serialized asynchronous `start()` and `stop()`
transitions, a `ServiceState`, health checks, and async context-manager support.
Implement `_start()` and `_stop()` to acquire and release resources. Repeated
starts while running and stops while idle or stopped are safe. If startup
fails, the service enters `failed`; call `stop()` to release partially acquired
resources before retrying.

`BackgroundService` extends `Service` and runs its `run()` coroutine in a
managed task. The coroutine can wait on `stop_event` to exit gracefully.
Shutdown waits for `shutdown_timeout`, cancels a worker that does not exit,
then waits once more for cancellation cleanup. Unexpected exit sets
`state == ServiceState.FAILED`; `failure` exposes its cause and `wait()` raises
`BackgroundServiceError` chained from that cause. A failed service can still be
stopped to release its resources.

```python
import asyncio

from std.service import BackgroundService


class QueueWorker(BackgroundService):
    async def run(self) -> None:
        while not self.stop_event.is_set():
            await asyncio.sleep(0.1)  # Replace with a queue receive operation.


async def main() -> None:
    worker = QueueWorker("queue-worker")
    await worker.start()
    await worker.stop()


asyncio.run(main())
```

## Optional integrations

### FastAPI

Install `standard-fastapi` directly or with the `standard[fastapi]` extra. From a source checkout, install `packages/standard-fastapi` in editable mode.

In `main.py`, construct that settings model once and inject it into the FastAPI application:

```python
from typing import Annotated

from fastapi import FastAPI
from app.core.settings import Settings
from std.fastapi import settings_dependency


def create_app() -> FastAPI:
    # main.py is the composition root; construct and validate settings once.
    settings = Settings()
    app = FastAPI()
    app.state.settings = settings
    settings_dep = settings_dependency(Settings)

    @app.get("/health")
    async def health(settings: Annotated[Settings, settings_dep]) -> dict[str, str]:
        return {"service": settings.service_name}

    return app
```

Call `create_app()` once when loading the application. Keep all `Settings()`
construction in `main.py`; route modules and dependencies receive the
validated instance rather than constructing another one. The
[sample consumer](https://github.com/appunni-m/python-standard/tree/main/sample-projects/standard-fastapi-consumer)
exercises this startup flow end to end.

`settings_dependency(settings_type)` requires a `BaseSettings` subclass and
returns a FastAPI `Depends` object that retrieves the matching instance from
`request.app.state.settings`. Add that object directly as `Annotated` metadata;
do not wrap it in another `Depends(...)`. Construct settings and the dependency
in `main.py`, store the settings instance before serving requests, and pass the
dependency into feature routers as needed. The helper never constructs or
reloads settings. An absent or wrong-typed value returns HTTP 500 with a
configuration message. Use `app.dependency_overrides` when tests need a
replacement.

`APIConfig` validates app metadata, deployment environment, server options, and
CORS policy. `FastAPISetup(api_config, log_config=None, setup_handler=None,
*, services=())` creates the app, configures logging when requested, installs
CORS, and wires a `LifecycleManager` into the ASGI lifespan. The `host`,
`port`, `workers`, `reload`, and `enabled` fields are available to the server
entry point; the setup helper does not launch Uvicorn.

`APIConfig.env` accepts `dev`, `stage`, or `prod`. `std.logging` also has a
`test` profile. In tests, pass `LoggingEnvironment.TEST` to
`configure_logging()` to keep warning-level console output, and map `test` to
`Environment.DEV` when building `APIConfig`; the FastAPI environment enum does
not accept `test`.

`LifecycleManager` starts injected services in order and stops them in reverse
order. It calls cleanup for the service whose startup failed, continues
cleaning earlier services, and preserves the startup exception. Shutdown
attempts every cleanup hook and raises an `ExceptionGroup` if multiple hooks
fail. The ASGI server owns process signal handling.

`AppTokenConfig` stores a configurable header, unique application tokens, an
enabled flag, and exact or wildcard excluded paths. Token values are omitted
from the model representation. `AppTokenAuth` can be used as a FastAPI
dependency and returns the matching application name; missing or invalid
tokens raise HTTP 401. `apply_token_auth_middleware` protects requests before
route dispatch and puts the authenticated name in `request.state.app_name`.
Both auth helpers skip excluded paths. `setup_token_auth` returns the
dependency; `setup_app_token_auth` is its alias. `add_api_key_security_scheme`
adds the configured header to generated OpenAPI.

`HealthCheck` accepts sync or async functions. Synchronous checks run through
the event loop's executor, check failures produce sanitized details containing
the exception type, and any `error`, `unhealthy`, or `down` result makes the
aggregate response unhealthy. `create_health_endpoint` is the app-registration
factory. The endpoint retains HTTP 200 and reports state in its response body.

`LoggingMiddleware` logs method, path, response status, and elapsed time, adds
an `X-Process-Time` response header, and can omit the client address with
`include_client=False`. It never reads request or response bodies. `APIService`
is a small base for registering one route group on an injected FastAPI app.

### AWS Secrets Manager

Install `standard-aws` directly or with the `standard[aws]` convenience extra:

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

`std guide` prints concise usage instructions. `std guide --format json` emits a JSON object with `schema_version: 1`, distribution/import/command names, version and Python requirement, shell-ready install commands, module availability, commands, skill location, documentation URLs, and the text guide. Consumers should check `schema_version` and ignore unrecognized fields.

`std skill show` prints the packaged idiomatic-Python skill. `std skill path` prints its filesystem path when the package was installed on the filesystem; for a non-filesystem package resource, it returns status 1 and directs the caller to `show` or `install`. `std skill install` copies it into the current repository at `.agents/skills/standard-idiomatic-python/SKILL.md` by default. That directory name matches the skill's `name` metadata as required by the [Agent Skills specification](https://agentskills.io/specification). It returns status 2 and refuses to overwrite an existing path unless `--force` is supplied; filesystem failures return status 1.

The supported command-line interface is the installed `std` executable. `std.cli.main` is its implementation entry point, not a separate library API. The root `std` package exposes `__version__`; import public utilities from the documented modules above.
