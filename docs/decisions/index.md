# Decisions and open questions

Behavior and project choices recorded below as **Decided** are the working contract.

## Decided

| Decision | Choice |
| --- | --- |
| Project display name | Standard |
| Python import package | `std` |
| Command line interface | `std`, with agent usage guidance and an idiomatic Python skill |
| Initial core capability | YAML/TOML and environment-based configuration management |
| Configuration behavior target | Match the documented and observed behavior of `pydantic-settings-extra-sources` 0.1.0, with edge cases fixed |
| Config file priority | By default, init kwargs > config files > process environment > dotenv > file secrets; caller-customizable |
| Directory merge | Sort files by normalized relative path; recursively merge mappings, append lists, and let later scalar or type conflicts replace earlier values |
| Missing sources | Fail clearly by default; allow optional sources only when explicitly configured |
| YAML roots | Empty YAML is `{}`; reject a non-mapping root |
| Interpolation | Support `${NAME}` and `${NAME:-default}` recursively in string values; an empty-but-set variable wins; detect cycles; `$$` escapes a literal dollar sign |
| Interpolation type conversion | JSON-decode only when one whole scalar is supplied by an interpolation; preserve ordinary strings and mixed literal text, and keep non-JSON substitutions as strings |
| Error handling | Use consistent source-aware public errors without exposing source or environment values |
| Optional integration style | Keep heavier integrations optional; intended install forms are `standard[fastapi]` and `standard[aws]` |
| Documentation hosting target | GitHub Pages, through GitHub Actions |
| Distribution name | `standard`; the product remains Standard, the import package is `std`, and the CLI is `std`. PyPI's current `standard` project is unrelated; resolve ownership before publishing. |
| Python support | CPython 3.11–3.14 |
| License | MIT |
| Base runtime dependencies | PyYAML 6.x and pydantic-settings 2.x; TOML uses `tomllib` |
| First-release module scope | `std.config`, `std.collections`, `std.files`, optional `std.fastapi` and `std.aws`, plus `std` CLI guidance |
| Config snapshot | Immutable `ConfigSnapshot`; `ConfigManager.reload()` publishes atomically only after a complete successful load |
| Optional dependencies | `[fastapi]` installs FastAPI integration; `[aws]` installs boto3 integration; neither enters the base install |

## Remaining external setup

PyPI lists an unrelated [`standard` distribution](https://pypi.org/project/standard/). The requested name cannot be published by this project until it is transferred. Do not substitute a different distribution identifier without user approval.

GitHub Pages is enabled for the repository and the documentation site is live at [appunni-m.github.io/python-standard](https://appunni-m.github.io/python-standard/). A private security reporting contact still needs to be configured by the repository owner before accepting reports.
