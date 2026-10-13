# Changelog

User-visible changes for the `standard` distribution and its five optional
providers are listed here. All six distributions share a release version. See
the [publishing guide](publishing.md) for the package map and release workflow.

## Unreleased

- Refresh the project, release, package, and testing documentation to match the
  coordinated `0.2.3` release.
- Update the packaged idiomatic-Python skill to describe the released core and
  provider layout.
- Add an independently assembled FastAPI consumer example and evaluation
  evidence.

## 0.2.0–0.2.3

The coordinated 0.2.x releases establish the modular package layout and agent-
first application tooling:

- Keep configuration, logging, utility helpers, async services, the `std` CLI,
  and the packaged idiomatic-Python skill in the `standard` core distribution.
- Publish FastAPI, AWS, HTTP, Redis cache, and relational database integrations
  as separate distributions under `std.fastapi`, `std.aws`, `std.http`,
  `std.cache`, and `std.rdbms`.
- Add the `fastapi`, `aws`, `http`, `cache`, and `rdbms` convenience extras to
  install each matching provider.
- Derive every distribution version from one annotated `vX.Y.Z` tag and build
  all six packages in the same release workflow.
- Add environment-aware logging presets, async service lifecycle management,
  Testcontainers consumer coverage, and a feature-first FastAPI template.
- Document the configuration merge, interpolation, precedence, error, and
  immutable-snapshot contracts.

The latest coordinated release is `0.2.3`.

## 0.1.1

- Publish the `standard` distribution through GitHub Actions Trusted
  Publishing.
- Include FastAPI and AWS modules inside the core distribution before the
  integration package split.

## 0.1.0

- Initial PyPI release of the `standard` distribution, imported as `std`.
- Provide YAML/TOML configuration and Pydantic Settings support, collection and
  file helpers, the `std` agent CLI, and optional FastAPI and AWS integrations.
