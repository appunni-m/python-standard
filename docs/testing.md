# Testing and benchmarks

## Install the test environment

```bash
make install
make check
```

`make install` installs the core and all five local add-on projects in editable mode, plus the test and docs tools. The test requirements pin `pydantic-settings-extra-sources==0.1.0` for live configuration parity checks. It is not a runtime dependency.

`make check` runs tox's supported Python environments (`py311` through `py314`) and the formatting, lint, strict type, and docs-build environments. Tox skips interpreters that are not installed locally; CI selects each Python environment explicitly so every supported version is exercised. Run one Python environment with `tox run -e py312`, or the non-matrix checks with `tox run -e lint,type,docs`.

The package metadata keeps each runtime integration independent. The Testcontainers suite builds the core and all five add-on wheels, then resolves the core, each single extra, and the combined extras in clean Python containers. It checks that unselected integrations stay absent:

| Install target | Checkout equivalent | Expected optional packages |
| --- | --- | --- |
| `standard` | `.` | None |
| `standard[fastapi]` | `-e . -e packages/standard-fastapi` | `standard-fastapi` and FastAPI |
| `standard[aws]` | `-e . -e packages/standard-aws` | `standard-aws` and boto3 |
| `standard[http]` | `-e . -e packages/standard-http` | `standard-http` and HTTPX |
| `standard[cache]` | `-e . -e packages/standard-cache` | `standard-cache` and Redis |
| `standard[rdbms]` | `-e . -e packages/standard-rdbms` | `standard-rdbms`, SQLAlchemy, and async drivers |
| `standard[fastapi,aws,http,cache,rdbms]` | Core plus all five local add-on projects | All add-on distributions and their dependencies |

The latest coordinated release is `v0.2.3`; all six distributions use version
`0.2.3`. The repository's Testcontainers suite validates built wheels and
clean consumer installs from the current source. The independent example in
[`sample-projects/standard-fastapi-consumer`](https://github.com/appunni-m/python-standard/tree/main/sample-projects/standard-fastapi-consumer)
adds an application-level check of the public API and project conventions.
These checks establish only the behaviors and environments they exercise; they
do not prove every possible application setup.

On 2026-10-13, I downloaded the six published `0.2.3` wheels and installed
them into isolated CPython 3.12 virtual environments. Core-only, each single
extra, and all extras together passed `pip check`. Core-only did not expose
provider namespaces; each single extra exposed only its selected namespace;
the combined install exposed all five. `std --version` reported `std 0.2.3`,
and `std guide --format json` returned schema version `1`. This smoke check
covers package metadata, imports, and CLI startup, not external service
behavior; the Testcontainers suite covers service-backed scenarios.

## Layers

| Layer | What it proves | Likely tools |
| --- | --- | --- |
| Unit | Parsing, merge, interpolation, immutable snapshots, reload, sources, helpers, CLI, and redaction. | pytest |
| Integration | FastAPI dependency, AWS source, HTTP request/auth, and Redis command behavior with injected or local clients. | pytest, optional extras |
| Container end-to-end | Built wheel install, mounted YAML/TOML consumer, Redis behavior, relational database transactions, and LocalStack AWS operations. | [Testcontainers for Python](https://testcontainers-python.readthedocs.io/en/latest/) |
| Compatibility | YAML and TOML values, interpolation, YAML directory merge, and source precedence compared with the live reference package. | `tests/parity/` |
| Performance | Load, lookup, directory merge, reload, and peak memory with correctness checked first. | `benchmarks/configuration.py` |

## Container scenario

`tests/integration/test_consumer_container.py` builds six wheels, installs the core alone, each single extra, and all five extras into separate `python:3.12-slim` containers, mounts YAML and TOML files, injects an environment value for YAML interpolation, and exercises both Pydantic Settings adapters plus installed provider APIs. Other container tests cover Redis, SQLite lifecycle behavior, PostgreSQL, MySQL, and LocalStack.

The E2E workspace is created inside the repository so Docker VMs that share the checkout can read the bind-mounted wheel and settings files; pytest removes it after the session. The E2E tox environment passes through `STD_REQUIRE_DOCKER` and the Testcontainers runtime overrides. GitHub Actions runs the suite with the default Ryuk cleanup helper.

The E2E test requires a working Docker socket. Locally, run `make test-e2e` and ensure Docker is running. If Rancher Desktop cannot start Ryuk, this local command disables only Ryuk; each tested container is still stopped by its context manager:

```bash
STD_REQUIRE_DOCKER=1 \
TESTCONTAINERS_RYUK_DISABLED=true \
TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock \
tox run -e e2e
```

## Verification status and release gates

On 2026-10-13, `make check` passed on Linux with CPython 3.12.11: 248 tests
passed, 11 E2E tests were deselected, coverage was 94%, and Ruff, strict mypy,
and the clean docs build passed. Tox skipped CPython 3.11, 3.13, and 3.14
because those interpreters were not installed locally. `make test-e2e` then
passed all 11 Testcontainers cases in 109.95 seconds. These results apply to
the current checkout and environment; they do not claim cross-platform or
all-interpreter coverage.

CI is configured for CPython 3.11–3.14, lint, strict typing, documentation
build, and Testcontainers end-to-end checks. The release workflow requires a
successful `main` CI run for the exact tagged commit before it publishes all
six distributions. For hosted evidence tied to a specific revision, inspect
the [CI workflow runs](https://github.com/appunni-m/python-standard/actions/workflows/ci.yml)
and [release workflow runs](https://github.com/appunni-m/python-standard/actions/workflows/release.yml).
Workflow configuration describes intended checks; a passing run is the
evidence for a particular commit.

The configured release checks cover:

- Unit and contract cases for missing sources, directory order, empty defaults, JSON-looking strings, interpolation cycles, YAML aliases, and secret redaction.
- A live parity case for ordinary reference behavior outside the fixes recorded in the [configuration contract](configuration/index.md).
- A Testcontainers consumer scenario that uses the same public API installed users call.
- Ruff formatting, lint and public docstring checks, strict mypy, coverage, and a clean documentation build.
- Benchmark correctness checks before timing and retention of the raw measurement file.

## Benchmark command

```bash
make bench
```

The benchmark emits JSON to `benchmarks/results/` and prints environment identity. It does not claim a 100× improvement; compare the recorded workload and measurements before making any performance statement.
