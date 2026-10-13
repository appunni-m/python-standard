# Fresh consumer evaluation

## Scope

This report evaluates the sample as a first-time consumer of the published
`standard==0.2.3` artifact and its FastAPI integration. The sample exercises
settings loading, YAML environment expansion, logging profiles, feature module
layout, thin routes, dependency injection, background service lifecycle,
health checks, and ordinary project checks.

It does not verify every API, every supported Python version, container-backed
integrations, production persistence, deployment behavior, or universal
correctness. The order repository is intentionally process-local.

## Consumer workflow

From this directory, the consumer install uses the dependency declared by the
sample project rather than a repository source path:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
std --version
std guide
std guide --format json
std skill install
```

The sample pins `standard[fastapi]==0.2.3`. The generated skill is the copy
provided by that installed artifact.

## Standard public APIs used

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

## Consumer conventions exercised

- `main.py` constructs `Settings()` on each startup path, configures logging,
  assembles the repository, order service, worker, API setup, and routers, and
  constructs the settings dependency and passes it into the application router.
  It stores the one settings instance on `app.state` for that dependency.
- `core/settings.py` aggregates `ApplicationSettings` and `OrdersSettings`
  from their owning feature modules instead of duplicating their fields.
- The orders feature co-locates its config, domain model, API schemas,
  repository, application service, background worker, and routes.
- Routes validate transport data, call the injected service, and translate an
  expected amount-limit error. They contain no repository operations.
- YAML tests prove `APP_NAME` and `APP_ENV` interpolation, including the
  `test` logging profile. A direct Pydantic `APPLICATION__NAME` environment
  variable is ignored because the settings source list is restricted to YAML.
- The integration test opens the ASGI lifespan, verifies the worker moves from
  `RUNNING` to `STOPPED`, waits for queued work, and observes the order move
  from `queued` to `processed`.

## Observed friction and recommendations

1. **Settings dependency example double-wraps `Depends`.** The API example
   reviewed at the start of this evaluation showed
   `settings_dep = settings_dependency(Settings)` followed by
   `Depends(settings_dep)`. On the tested FastAPI version, that raises
   `TypeError: Depends(...) is not a callable object` because the helper already
   returns a `Depends` instance. Using that returned object directly as
   `Annotated[Settings, settings_dependency(Settings)]` registers and resolves
   correctly. The current checkout's API reference and integration README now
   show the direct form; the published docs URL could not be fetched from this
   environment, so its publication status remains unverified.
2. **The deployment and logging environment enums differ.** The logging API
   has a `test` profile, while `std.fastapi.Environment` has only `DEV`,
   `STAGE`, and `PROD`. The sample maps `test` to `DEV` for `APIConfig`, and
   passes `test` directly to `configure_logging()` so the warning-level test
   profile remains active. This mapping is now documented beside the
   `APIConfig` contract in the API reference.
3. **The packaged skill contradicts the installed guide.** With the published
   `standard==0.2.3` artifact, `std guide --format json` lists `std.service` as
   a core module and `std guide` says it provides lifecycle management. The
   skill created by `std skill install` from that same artifact says
   `std.service` is part of the unreleased source. The installed skill was kept
   intact as evidence. Reconcile the packaged skill with the guide before the
   next release; the working-tree skill has since been corrected, but that
   correction is not in the tested artifact.
4. **Static typing cannot infer YAML-populated required settings.** A
   `Settings()` call is valid at runtime because `YamlSettingsSource` provides
   the required fields, but mypy sees the generated settings constructor
   signature. The sample uses a narrow `type: ignore[call-arg]` with an inline
   reason in `main.py`.
5. **Keep dependency construction visible in the composition root.** The
   settings dependency factory is constructed in `main.py` and passed to the
   application router factory. This keeps settings construction and the
   dependency graph together while route modules only declare injection.

During initial exploration, a synchronous health callback returned successfully
but the process did not leave `asyncio.run()` promptly on this Python/runtime
combination. Switching the sample's in-memory check to an async callback made
the test process exit cleanly. The cause was not isolated to one library layer,
so this is recorded as a bounded observation rather than a general health API
claim.

## Verification evidence

The sample project was installed in its own virtual environment with its
declared dependency `standard[fastapi]==0.2.3`; neither core nor integration was
installed from a repository path. Both imports resolve from that environment's
`site-packages`. The checked runtime was CPython 3.12.11 with `standard==0.2.3`,
`standard-fastapi==0.2.3`, FastAPI 0.143.0, pydantic-settings 2.15.0, Pydantic
2.14.1, and PyYAML 6.0.3. Development tools were pytest 9.1.1, HTTPX 0.28.1,
mypy 1.20.2, Ruff 0.17.0, and uvicorn 0.54.0. This is one Python/runtime
combination; it does not establish the full supported-version matrix.

### Commands

Run from `sample-projects/standard-fastapi-consumer`:

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

All commands completed successfully. `std --version` printed `std 0.2.3`;
machine-readable guide output reported schema version 1, `std.service` as
`core`, and `std.fastapi` as `extra:fastapi`. `pip check` reported no broken
requirements. `make check` ran four tests (all passed), Ruff formatting
(`20 files already formatted`), Ruff lint (`All checks passed!`), and strict
mypy (`Success: no issues found in 18 source files`). The final `make check`
was run after removing one unused import caught by Ruff. An earlier probe also
showed the direct `Depends(settings_dependency(Settings))` form raises the
TypeError described above under FastAPI 0.143.0.

The checks cover the sample on CPython 3.12.11 with an in-memory repository.
They do not exercise Docker/Testcontainers, AWS, production persistence,
deployment, every supported Python minor, all documented Standard APIs, or
universal correctness. A public documentation URL emitted by `std guide` was
not independently fetchable in this environment; the double-wrapped
dependency example was observed during the documentation review and then
verified against the installed runtime, while this report preserves the exact
runtime result rather than treating it as a universal behavior claim.
