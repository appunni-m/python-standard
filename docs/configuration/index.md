# Configuration manager: behavior contract

This document records the behavior Standard preserves from [`pydantic-settings-extra-sources` 0.1.0](https://pypi.org/project/pydantic-settings-extra-sources/0.1.0/) and the edge cases it handles predictably. The implementation API is documented below.

The component boundaries and reload model are summarized in the [architecture decisions](../decisions/index.md); this page is the detailed behavior contract for configuration.

## The goal

Support the reference package's documented YAML/TOML, directory merge, environment interpolation, and Pydantic Settings integration. Fix ambiguous or unsafe edge cases while keeping configuration reads fast. The latest retained exploratory run, dated 2026-10-12, shows a 5.07×–6.47× descriptive settings-load ratio; it is a historical artifact, not a benchmark of the current checkout. **100× remains a target to investigate.** See the [benchmark results and measurement limits](benchmark-plan.md#results).

## Compatibility baseline

- Read YAML and TOML from one file or a directory of files.
- Interpolate `${NAME}` and `${NAME:-default}` in string values at any nesting depth in mappings and lists.
- Allow JSON values supplied through a whole-value interpolation, including lists, mappings, numbers, booleans, and `null`.
- Merge directory files deterministically: mappings merge recursively, lists append, and later scalar or type conflicts replace earlier values.
- Integrate with Pydantic Settings and preserve the reference default source priority: init kwargs, config files, process environment, dotenv, then file secrets. Pydantic treats the first source as highest priority, so config-file values override direct environment values by default. Callers may customize the source order.

These rules describe compatibility, not an implementation dependency. Standard has its own implementation and public API.

## Edge-case decisions

| Case | Behavior |
| --- | --- |
| File ordering differs across filesystems or nested directories. | Collect matching files first, then sort by normalized relative POSIX path in lexical order before merging. |
| A configured file or directory is missing. | Raise a source-aware missing-source error. A source is optional only when the caller explicitly marks it optional. |
| An existing directory has no matching YAML/TOML files. | Treat it as an empty mapping, matching the reference's empty-source behavior. |
| A YAML file is blank or contains only comments. | Treat it as an empty mapping. |
| YAML has an explicit `null` or another non-mapping top-level value. | Reject it with an error identifying the file and configuration location. TOML roots are mappings by format. |
| `${NAME:-}` uses an empty fallback. | Accept it. An environment variable that exists with an empty value is still set and wins over the fallback; fallback applies only when the variable is unset. |
| An environment value contains another placeholder. | Resolve nested references recursively. Detect direct and indirect cycles and report them as configuration errors instead of looping. |
| A string is not an interpolation. | Preserve its type and contents. Do not JSON-decode ordinary YAML/TOML strings or strings where interpolation is mixed with literal text. |
| One scalar consists of exactly one interpolation. | After resolving the environment value or fallback, decode it as JSON if valid JSON; otherwise keep it as a string. This retains complex-value support without changing unrelated strings such as `"false"` or `"123"`. |
| YAML aliases create a cyclic object graph. | Detect and reject the cycle before recursive interpolation or merge. |
| The same failure occurs in YAML and TOML processing. | Raise the same public error category with source path and configuration location where available. Error messages must not reveal environment or configuration values. |
| Placeholder syntax is malformed or unsupported. | Accept only `${NAME}` and `${NAME:-default}`, with environment names matching `[A-Za-z_][A-Za-z0-9_]*`. Use `$$` to represent a literal dollar sign. Report malformed `${...}` expressions with source context. |

The JSON rule applies to values whose entire scalar is one placeholder, including an empty or non-empty fallback. For example, `items: ${ITEMS}` can produce a list when `ITEMS` contains valid JSON, while `label: "false"` and `path: "${ROOT}/data"` remain strings. JSON that does not parse remains a string.

Interpolation applies to string values, including values nested in lists and mappings; mapping keys are left unchanged. Resolving an environment variable may reveal another placeholder, which is then resolved under the same cycle and syntax rules. This interpolation mechanism reads process environment values directly; Pydantic's regular environment source remains a separate source governed by the source priority above.

## Source merge behavior

Directory files are sorted together by normalized relative path before merging, even when files are in different nested directories. The merge rules are:

- mapping + mapping: merge keys recursively;
- list + list: append the later list;
- any scalar or type conflict: use the later value.

The final value for a field across Pydantic sources follows the source priority above. Directory-file merge order and Pydantic source priority are separate rules: the former composes files inside the config source; the latter resolves that source against init kwargs, environment, dotenv, and secrets.

## Public API and lifecycle

```python
from std.config import ConfigManager

manager = ConfigManager.from_files("config/base.yaml", "config/local.toml")
snapshot = manager.snapshot
host = snapshot.get_path("database.host")

new_snapshot = manager.reload()  # explicit, atomic, and all-or-nothing
```

`ConfigManager.from_files(*sources, optional=False, environ=None)` accepts supported files and directories. `ConfigManager.from_file(path, ...)` is the single-source convenience constructor. The default behavior is to reject missing configured sources; set `optional=True` only when absence is expected. An existing directory without matching files is an empty mapping.

`ConfigSnapshot` is an immutable `Mapping[str, object]`; nested mappings are read-only and sequences are tuples. Use `to_dict()` to obtain an isolated mutable deep copy. `get_path("a.b")` and `get_path(("a", "b"))` read nested values without changing the snapshot. Reload reparses using the current process environment unless an explicit environment mapping was supplied; it leaves the published snapshot unchanged if parsing fails.

For Pydantic Settings, use `YamlSettingsSource` or `TomlSettingsSource` in `settings_customise_sources`. `YamlSettings` and `TomlSettings` are convenience base classes configured with `std_config_file`. The default source order is init kwargs, config files, process environment, dotenv, then secrets. Custom source order remains under the application's control.

## Data path

```text
YAML/TOML files and declared Pydantic sources
                    ↓
       parse and normalize with source context
                    ↓
       interpolate environment string values
                    ↓
       merge directory files deterministically
                    ↓
       resolve Pydantic source priority
                    ↓
          validate the final shape
                    ↓
       publish a read-ready snapshot
```

Parsing, interpolation, merging, and Pydantic validation happen at construction or reload time so repeated reads stay simple. Warm reads use the prepared immutable snapshot.

Environment profiles or selecting a file such as `production.yaml` are not part of the reference baseline. They can be designed as separate additions if a concrete use case requires them.

## Performance contract

Parsing and validation happen at load or explicit reload time. Repeated reads use a prepared immutable snapshot. The benchmark includes the pinned reference source and checks equal output before timing. The 100× aspiration is not a release claim; every result is tied to the recorded input, target, Python, and machine.

## Reference inspection

The exact 0.1.0 release is used as a pinned test and benchmark oracle through the development-only `test` extra. It is not a runtime dependency. The [related-project research](research.md) records observed behavior and source ordering; Standard has an independent implementation with the fixes above.

## Design exit criteria

Unit tests cover the contract above, and live oracle tests compare ordinary
YAML/TOML values, interpolation, YAML directory merging, and source precedence.
The Testcontainers consumer scenario builds the core and five provider wheels,
then installs core alone, each integration extra, and all extras; it mounts
YAML and TOML and exercises both Pydantic Settings adapters. CI configuration
also includes the supported Python matrix, strict typing, lint, and docs build.
Check the [CI workflow runs](https://github.com/appunni-m/python-standard/actions/workflows/ci.yml)
for results tied to a specific commit; the release workflow requires those
checks to pass before publishing.
