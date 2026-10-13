# Fresh consumer evaluation

## Scope

This report evaluates the sample as a first-time consumer of the published
`standard==0.2.4` package and its FastAPI integration. It exercises settings,
YAML environment expansion, logging profiles, feature module layout, thin
routes, dependency injection, background service lifecycle, health checks, and
project checks.

The evaluation was run on Linux with CPython 3.12.11. It does not verify every
API or supported Python version, container-backed integrations, production
persistence, deployment behavior, or universal correctness. The order
repository is intentionally process-local.

## Consumer workflow

From this directory, create a virtual environment and install the dependency
declared by the sample project. Standard and its FastAPI integration resolve
from PyPI; the sample application itself is installed editable:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
std --version
std guide
std guide --format json
std skill install
python -m pip check
make check
```

The sample pins `standard[fastapi]==0.2.4`. The installed skill comes from the
same published core package.

## Standard APIs and conventions exercised

- `std.config.YamlSettings` and `YamlSettingsSource` provide typed YAML-backed
  settings. The `Settings` aggregate keeps only that source, so environment
  values enter through declared `${NAME}` placeholders.
- `std.logging.LoggingConfig`, `LoggingEnvironment`, and
  `configure_logging()` set the application profile and service name in the
  composition root.
- `std.fastapi.APIConfig` and `FastAPISetup.create_fastapi_app()` build the app
  and register the injected background service with the ASGI lifespan.
- `std.fastapi.settings_dependency()` injects the settings object constructed
  by `main.py`.
- `std.fastapi.LoggingMiddleware` adds request timing and logs transport
  metadata without client addresses.
- `std.fastapi.create_health_endpoint()` registers an async application check.
- `std.service.BackgroundService` and `ServiceState` implement and verify the
  worker lifecycle.

The sample follows the requested composition pattern: `main.py` constructs
`Settings()` on each startup path, configures logging, assembles the repository,
order service, worker, API setup, and routers, and constructs the settings
dependency. It stores the one settings instance on `app.state`. Feature-local
orders files contain the config, domain model, API schemas, repository,
application service, background worker, and routes. Routes validate transport
data, call the injected service, and translate an expected amount-limit error;
they contain no repository operations.

YAML tests prove `APP_NAME` and `APP_ENV` interpolation, including the `test`
logging profile. A direct Pydantic `APPLICATION__NAME` environment variable is
ignored because the settings source list is restricted to YAML. The integration
test opens the ASGI lifespan, verifies the worker moves from `RUNNING` to
`STOPPED`, waits for queued work, and observes the order move from `queued` to
`processed`.

## Findings

1. **Use the dependency object returned by the helper directly.** The API
   reference and integration README now show
   `Annotated[Settings, settings_dependency(Settings)]`. Wrapping the returned
   `Depends` object in another `Depends` raised `TypeError: Depends(...) is not
   a callable object` with FastAPI 0.143.0.
2. **Map the test environment explicitly.** The logging API has a `test`
   profile, while `std.fastapi.Environment` has only `DEV`, `STAGE`, and
   `PROD`. The sample maps `test` to `DEV` for `APIConfig`, and passes `test`
   directly to `configure_logging()` so the warning-level test profile stays
   active. The API reference documents this mapping.
3. **The packaged skill regression is fixed in 0.2.4.** The published `0.2.3`
   artifact listed `std.service` as core in `std guide` but its installed skill
   called it unreleased. The `0.2.4` wheel corrects that guidance. A clean
   install of `standard[fastapi]==0.2.4` reported `std 0.2.4`; the JSON guide
   listed `std.service` as `core`, and `std skill install` produced a skill
   containing `std.service` without the stale `unreleased source` claim.
4. **Static typing cannot infer YAML-populated required settings.** A
   `Settings()` call is valid at runtime because `YamlSettingsSource` provides
   the required fields, but mypy sees the generated settings constructor
   signature. The sample uses a narrow `type: ignore[call-arg]` with an inline
   reason in `main.py`.
5. **Keep dependency construction visible in the composition root.** The
   settings dependency factory is constructed in `main.py` and passed to the
   application router factory. Route modules only declare injection.

An initial synchronous health callback returned successfully but the process
did not leave `asyncio.run()` promptly on the tested runtime. Switching the
sample's in-memory check to an async callback made the test process exit
cleanly. The cause was not isolated to one library layer, so this remains a
bounded observation rather than a general health API claim.

## Verification evidence

The sample was installed in a fresh temporary virtual environment from its
declared `standard[fastapi]==0.2.4` dependency. Neither Standard package was
installed from this repository; both resolved from PyPI. The runtime was
CPython 3.12.11 with `standard==0.2.4`, `standard-fastapi==0.2.4`, FastAPI
0.143.0, pydantic-settings 2.15.0, Pydantic 2.14.1, and PyYAML 6.0.3.
Development tools were pytest 9.1.1, HTTPX 0.28.1, mypy 1.20.2, Ruff 0.17.0,
and uvicorn 0.54.0.

All listed commands completed successfully. `std --version` printed
`std 0.2.4`; machine-readable guide output reported schema version 1,
`std.service` as `core`, and `std.fastapi` as `extra:fastapi`. The published
skill was installed in a clean directory and checked for the corrected service
guidance. `pip check` reported no broken requirements. `make check` ran four
tests (all passed), Ruff formatting (`20 files already formatted`), Ruff lint
(`All checks passed!`), and strict mypy (`Success: no issues found in 18 source
files`).

These checks cover one Python/runtime combination and an in-memory repository.
They do not exercise Docker/Testcontainers, AWS, production persistence,
deployment, every supported Python minor, all Standard APIs, or universal
correctness. The repository's separate Testcontainers suite covers clean wheel
installs and service-backed scenarios; see the [testing guide](../../docs/testing.md)
for its scope and hosted CI evidence.
