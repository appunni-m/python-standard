# Related projects and design references

This survey identifies useful approaches to study. It does not rank the projects or imply that Standard should depend on them.

## Configuration systems

| Project | Useful design ideas | Trade-off to evaluate |
| --- | --- | --- |
| [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | Typed settings, configurable source priority, and a YAML source. | Measure validation and source flexibility against the desired hot-read path. |
| [Dynaconf](https://www.dynaconf.com/settings_files/) | Multiple settings files, environment layers, and environment switching. | Study its broader settings model and how it represents precedence. |
| [OmegaConf](https://omegaconf.readthedocs.io/en/latest/structured_config.html) | Hierarchical merge and structured validation. | Compare its data model and access costs with the planned API. |
| [Hydra](https://hydra.cc/docs/intro/) | Config composition, groups, command-line overrides, and multirun. | It is an application configuration framework; compare scope carefully. |
| [`pydantic-settings-extra-sources`](https://pypi.org/project/pydantic-settings-extra-sources/0.1.0/) | YAML/env interpolation and directory-based sources, as requested for study. | Early artifact; its published page has inconsistent package/import naming. Its exact source archive has been inspected; verify imports rather than relying on its README examples. |
| [`confspec`](https://pypi.org/project/confspec/) | Interpolation and validation adapters across formats. | Newer project; evaluate maturity, API stability, and comparable features. |

## Early conclusions

- Match the reference package's documented feature set; differentiate through clear semantics, edge-case correctness, and measured performance.
- Performance comparisons must use the same config shape, precedence, interpolation, validation, and output guarantees.
- The requested `pydantic-settings-extra-sources` package is the compatibility reference, not a dependency. Its exact source archive has been inspected; the adopted behavior and edge-case decisions are summarized in the [configuration contract](index.md).
- PyPI now lists `standard` 0.1.0 under maintainer `appunni-m`; fresh installs of the base package and all extras passed on 2026-10-12. See [publishing](../publishing.md) for the current release-workflow status.

## Closer look at the provided 0.1.0 source archive

I inspected the [source distribution](https://files.pythonhosted.org/packages/8d/8e/d54a98961f0364d253a933a7b6c66fa68d387bdf91e52eb694e58781e859/pydantic_settings_extra_sources-0.1.0.tar.gz) without installing or executing it. These notes describe that artifact, not a recommendation to copy its implementation.

| Behavior in the artifact | Standard decision |
| --- | --- |
| Reads YAML and TOML files, including directories; uses `yaml.safe_load` for YAML. | Keep both formats. Empty YAML means `{}`; reject non-mapping YAML roots. |
| Substitutes `${NAME}` and `${NAME:-default}` recursively in strings, lists, and mappings. | Interpolate nested string values, support empty defaults and `$$` escaping, and detect cycles. Empty-but-set variables remain set. |
| Attempts `json.loads` on every string after substitution. This converts JSON-looking scalars such as `false`, `null`, and numeric strings into non-string values. | Decode JSON only for one whole-value interpolation; preserve ordinary strings and mixed literal text. Keep non-JSON substitution values as strings. |
| Returns Pydantic sources in this order: init kwargs, YAML/TOML, environment, dotenv, file secrets. Pydantic documents the first returned source as highest priority. | Keep this as the default priority and allow callers to customize source order. |
| Merges directory files through [`deepmerge.always_merger`](https://deepmerge.readthedocs.io/en/latest/guide.html): mappings merge, lists append, and later values replace on conflicts. The README says alphabetical order, while the implementation sorts filenames within each walked directory. | Keep the merge rules; sort all files by normalized relative path before merging. |
| Returns an empty mapping when the configured path is neither an existing file nor directory. | A missing configured source is an error unless explicitly optional; an existing directory with no matching files is empty. |
| Reports missing variables differently in YAML and TOML paths; TOML wraps a missing-variable error as a file-parsing error. | Use consistent source-aware errors and do not expose configuration or environment values. |
| The source tree imports `pydantic_settings_sources`, while its README error example imports `pydantic_settings_extra_sources.errors`; those module paths do not match. | Publish one canonical `std` API; treat the inspected source tree as evidence, not a namespace to copy. |
| The metadata advertises broad Python and Pydantic version ranges, but no compatibility tests were part of this artifact. | Choose supported versions independently and test those exact versions. |

The archive's `LICENSE` and package metadata identify it as MIT licensed. If code is ever reused, include the required copyright and license notice and choose a compatible project license first. This design stage does not copy its source.

The source order above follows [Pydantic Settings' documented priority rule](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#changing-priority). In this artifact, YAML/TOML therefore has higher priority than the regular environment source, while interpolation inside the file reads `os.environ` directly. Those are two different mechanisms and should be described separately in our design.

## Sources

Pages and the provided source archive were reviewed on 2026-10-10. Project features and releases can change; verify them again before selecting dependencies.
