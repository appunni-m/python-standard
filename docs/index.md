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

The source package, extras, CLI, tests, benchmark runner, and documentation workflow are implemented. The benchmark records measured results without claiming the original 100× aspiration. PyPI name availability is unconfirmed: the current project page returned 404 during setup, while an indexed PyPI page still lists an older unrelated project. Verify ownership before public installation or release. The documentation site is live at [appunni-m.github.io/python-standard](https://appunni-m.github.io/python-standard/); pushes to `main` publish updates through GitHub Actions.

Keep configuration errors and source precedence explicit, keep optional integrations out of the core install, and measure equivalent work before making performance claims.
