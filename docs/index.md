# Standard

## Small Python utilities with predictable behavior

Standard is a Python utility library published as the `standard` distribution. It imports as `std` and provides the `std` command. The published 0.1.1 package includes YAML/TOML configuration, Pydantic Settings integration, collection and file helpers, FastAPI and AWS integrations, and coding-agent guidance. The repository's 0.2.0 layout separates the FastAPI and AWS modules into their own distributions and adds environment-aware logging; that version has not been published yet.

### Choose a path

| If you want to… | Start with… |
| --- | --- |
| Install Standard or run the first example | [Get started](get-started.md) |
| Load YAML/TOML and configure Pydantic Settings | [Configuration reference](configuration/index.md) |
| Configure application logs by environment | [Logging guide](logging.md) |
| Find public helpers and integrations | [API reference](api.md) |
| Call HTTP services | [HTTP client guide](http.md) |
| Cache data or coordinate work with Redis | [Cache and locks guide](cache.md) |
| Manage async database sessions | [Relational database guide](rdbms.md) |
| Compare configuration tools | [Research notes](configuration/research.md) |
| Understand architecture boundaries and current decisions | [Decisions](decisions/index.md) |
| Run tests or reproduce measurements | [Testing and benchmarks](testing.md) |
| Read release changes | [Changelog](changelog.md) |
| Contribute | [Contributing](contributing.md) |

### Current release status

As of 2026-10-12, PyPI and GitHub have the `standard` 0.1.1 release. Its [release workflow](https://github.com/appunni-m/python-standard/actions/runs/38249688229) completed using Trusted Publishing, and hosted [CI run 38226724973](https://github.com/appunni-m/python-standard/actions/runs/38226724973) and [documentation run 38226724951](https://github.com/appunni-m/python-standard/actions/runs/38226724951) passed on `ef584957`. The repository version is 0.2.0; the split provider distributions are not published and their PyPI publisher setup remains open. The docs site is live at [appunni-m.github.io/python-standard](https://appunni-m.github.io/python-standard/). Benchmark records are exploratory and do not claim the 100× aspiration.

Keep configuration errors and source precedence explicit, keep optional integrations out of the core install, and measure equivalent work before making performance claims.
