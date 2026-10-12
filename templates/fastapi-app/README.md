# Standard FastAPI app template

A copyable FastAPI service that keeps each feature's routes, schemas, models,
services, and settings together. Shared startup and infrastructure live in
`core/`, while `main.py` shows the complete dependency graph in one place.

The app uses the published `standard[fastapi]` distribution, `std.config` to
load YAML, and `std.logging` for environment-aware application logging.
`Service` and `BackgroundService` come from the `standard` core package.

See the [HTML preview](preview.html) for a visual map of the modules and startup
flow.

## Start the app

Requirements: Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
uvicorn --factory example_app.main:create_app --reload
```

On Windows PowerShell, activate the environment with
`.venv\Scripts\Activate.ps1`.

Open <http://127.0.0.1:8000/health>. The response contains the configured
application name.

## Organize by module

Start with the feature or Django-style application that owns the change. Keep
that module's HTTP routes, schemas, domain or persistence models, services, and
module-specific settings together. A new feature should not require parallel
folders such as a global `api/`, `services/`, and `models/` tree.

```text
src/example_app/
├── main.py
├── lifecycle.py
├── core/
│   ├── services.py
│   └── settings.py
└── modules/
    ├── application/
    │   └── config.py
    ├── health/
    │   ├── api/routes.py
    │   ├── models.py
    │   ├── schemas.py
    │   └── service.py
    └── heartbeat/
        ├── config.py
        └── service.py
```

The health module's `HealthStatus` is an in-memory domain model, and
`HealthResponse` is the HTTP response schema. The template has no database, so
it does not add an empty ORM model or repository. When a feature gains
persistence, keep its database models and repository in that feature's module.

## Configure the application

Edit `config/settings.yaml`. This is the only path for process environment
values into Pydantic settings: declare each variable as a Standard interpolation
placeholder in YAML. For example, `APP_NAME` fills
`application.name` through `${APP_NAME:-Example API}`. Python modules do not
read `os.environ` or call `os.getenv`.

Each module defines only the settings it owns. `core/settings.py` aggregates
those Pydantic models and chooses `YamlSettingsSource`; it does not redeclare
their fields. Only `main.py` calls `Settings()`, once at application startup.

The application environment controls logging defaults. Development uses
`DEBUG` and readable console output, tests use `WARNING` and console output,
and staging/production use `INFO` and newline-delimited JSON. Explicit YAML
settings can override the level and format independently:

```yaml
application:
  environment: ${APP_ENV:-development}

logging:
  level: ${LOG_LEVEL:-null}
  format: ${LOG_FORMAT:-auto}
  stream: ${LOG_STREAM:-stdout}
  color: ${LOG_COLOR:-auto}
```

Use `format: console`, `format: json`, or `format: custom` to choose a format
directly. Custom format strings, named logger levels, source fields, and
stdout/stderr selection are documented in the
[logging guide](https://appunni-m.github.io/python-standard/logging/).
The JSON formatter carries timestamp, level, logger, message, environment,
service name, optional source/exception fields, and values passed through
`logging`'s `extra` argument. Keep secrets out of messages and context fields.

## Follow the startup path

1. Uvicorn calls `create_app()` in `main.py` when the application loads.
2. `main.py` creates one `Settings` object, configures shared logging,
   constructs services, and injects the health service into its module router.
3. `lifecycle.py` starts the already-constructed background services when the
   ASGI application starts, then stops successful starts in reverse order.
4. Health routes stay thin and delegate behavior to `HealthService`.

The lifecycle registers each `stop()` callback before calling `start()`. If
startup partially allocates a resource and then fails, the service's cleanup
hook still runs; services stop in reverse startup order.

## File map

| Path | Responsibility |
| --- | --- |
| `config/settings.yaml` | Defaults and the declared environment placeholders for all modules. |
| `src/example_app/main.py` | Sole composition root: loads settings, builds shared dependencies, injects them, and creates FastAPI. |
| `src/example_app/core/settings.py` | YAML-backed settings aggregate; references each module's model without defining module fields. |
| `src/example_app/core/services.py` | Exposes the shared lifecycle types from `std.service`. |
| `std.logging` | Shared logging presets, formatters, environment defaults, and typed overrides. |
| `src/example_app/lifecycle.py` | Starts and stops the background services injected by `main.py`. |
| `src/example_app/modules/application/config.py` | Application identity and runtime-environment settings. |
| `src/example_app/modules/health/` | Health controller, response schema, domain model, and service in one feature module. |
| `src/example_app/modules/heartbeat/` | Optional background worker and its settings in one feature module. |
| `tests/unit/modules/` | Unit tests grouped by owning module. |
| `tests/integration/` | ASGI-level integration examples. Add Testcontainers when a real external service is introduced. |

## Development commands

```bash
make lint
make type
make test
```
