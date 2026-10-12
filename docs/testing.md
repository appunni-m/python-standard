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

The published [`standard` project](https://pypi.org/project/standard/) is at version 0.1.1. On 2026-10-12, fresh CPython 3.12 virtual environments installed the base package, each existing extra, and both extras from PyPI; imports for `std`, `std.fastapi`, and `std.aws` passed. The combined environment also passed `pip check` and the `std` CLI/skill commands. This verifies the published 0.1.1 artifact, where FastAPI and AWS are bundled. The repository's 0.2.0 split and its five add-on distributions have not been published.

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

As of 2026-10-12, hosted [CI run 38226724973](https://github.com/appunni-m/python-standard/actions/runs/38226724973) passed the quality job, the Testcontainers consumer job, and the CPython 3.11–3.14 matrix on main commit `ef584957`. The standard `v0.1.1` release workflow completed successfully in [run 38249688229](https://github.com/appunni-m/python-standard/actions/runs/38249688229), verifying the OIDC publisher for `standard`. The new provider workflows are present in this working tree but have not run; their PyPI projects and publishers are not verified. The documentation site built and deployed in [run 38226724951](https://github.com/appunni-m/python-standard/actions/runs/38226724951). Hosted results predate the current source edits.

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
