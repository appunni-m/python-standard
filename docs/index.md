# Standard

## Build Python applications with clear module boundaries

Standard is an alpha Python library for shared application infrastructure and agent guidance. Install the `standard` distribution, import it as `std`, and use the `std` command to discover supported APIs and install the packaged Python skill. The core provides configuration, logging, collections, file helpers, and async service lifecycles. FastAPI, AWS, HTTP, Redis cache, and relational database integrations are separate distributions selected with extras. All six distributions use one version from a shared release tag.

The application pattern keeps settings, routes, schemas, data models, repositories, and services with their feature. `main.py` constructs settings and dependencies once, then injects them into the app and its lifecycle. The [FastAPI template](https://github.com/appunni-m/python-standard/tree/main/templates/fastapi-app) and [sample consumer](https://github.com/appunni-m/python-standard/tree/main/sample-projects/standard-fastapi-consumer) show the pattern in code.

### Choose a path

| If you want to… | Start with… |
| --- | --- |
| Install Standard or run the first example | [Get started](get-started.md) |
| Load YAML/TOML and configure Pydantic Settings | [Configuration reference](configuration/index.md) |
| Configure application logs by environment | [Logging guide](logging.md) |
| Find public helpers and integrations | [API reference](api.md) |
| Inspect a consumer app installed from the published packages | [FastAPI consumer sample](https://github.com/appunni-m/python-standard/tree/main/sample-projects/standard-fastapi-consumer) and its [evaluation report](https://github.com/appunni-m/python-standard/blob/main/sample-projects/standard-fastapi-consumer/EVALUATION.md) |
| Call HTTP services | [HTTP client guide](http.md) |
| Cache data or coordinate work with Redis | [Cache and locks guide](cache.md) |
| Manage async database sessions | [Relational database guide](rdbms.md) |
| Compare configuration tools | [Research notes](configuration/research.md) |
| Understand architecture boundaries and current decisions | [Decisions](decisions/index.md) |
| Run tests or reproduce measurements | [Testing and benchmarks](testing.md) |
| Read release changes | [Changelog](changelog.md) |
| Contribute | [Contributing](contributing.md) |
| Report a bug or ask for help | [GitHub Issues](https://github.com/appunni-m/python-standard/issues) |
| Report a security issue | [Security policy](https://github.com/appunni-m/python-standard/blob/main/SECURITY.md) |

### Current release

The latest coordinated release is `v0.2.3`. It includes `standard` and five provider distributions at the same version. Installing `standard` alone gives you the core modules; install an extra such as `standard[fastapi]` to add an integration. See [publishing](publishing.md) for package links and the tag-based release process. The documentation site is published through [GitHub Pages](https://appunni-m.github.io/python-standard/). Configuration benchmark records are exploratory and do not demonstrate the 100× target.

Keep configuration errors and source precedence explicit, keep optional integrations out of the core install, and measure equivalent work before making performance claims.
