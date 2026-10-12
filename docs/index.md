# Standard

## Small Python utilities with predictable behavior

The intended distribution is `standard`, it imports as `std`, and it provides the `std` command. Its first release includes YAML/TOML configuration, Pydantic Settings integration, focused collection and file helpers, optional FastAPI and AWS integrations, and coding-agent guidance.

### Choose a path

| If you want to… | Start with… |
| --- | --- |
| Install Standard or run the first example | [Get started](get-started.md) |
| Load YAML/TOML and configure Pydantic Settings | [Configuration reference](configuration/index.md) |
| Find public helpers and integrations | [API reference](api.md) |
| Compare configuration tools | [Research notes](configuration/research.md) |
| Run tests or reproduce measurements | [Testing and benchmarks](testing.md) |
| Contribute | [Contributing](contributing.md) |

### Current release foundation

The `standard` distribution is published on PyPI, and fresh installs of the core package and each extra have been verified. Version 0.1.0 still contains outdated name-availability guidance in its CLI text; the repository correction is prepared as 0.1.1. The GitHub Release workflow has no runs or tags yet, so automated publishing remains unverified. The benchmark records measured results without claiming the original 100× aspiration. The documentation site is live at [appunni-m.github.io/python-standard](https://appunni-m.github.io/python-standard/); pushes to `main` publish updates through GitHub Actions.

Keep configuration errors and source precedence explicit, keep optional integrations out of the core install, and measure equivalent work before making performance claims.
