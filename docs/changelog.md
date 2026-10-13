# Changelog

User-visible changes for the `standard` distribution and its five optional
providers are listed here. All six distributions share a release version. See
the [publishing guide](publishing.md) for the package map and release workflow.

## 0.2.4

- Correct the packaged idiomatic-Python skill to describe `std.service` as a
  released core API.
- Add regression coverage for the skill in source and built-wheel consumer
  tests.
- Add a fresh FastAPI consumer sample and update documentation to reflect the
  coordinated release and tested consumer workflow.
- Publish the core package and all five providers from the `v0.2.4` tag.

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

The `0.2.3` core wheel's packaged skill incorrectly described `std.service` as
unreleased. That historical artifact remains unchanged; the guidance is
corrected in `0.2.4` and guarded by regression tests.

## 0.1.1

- Publish the `standard` distribution through GitHub Actions Trusted
  Publishing.
- Include FastAPI and AWS modules inside the core distribution before the
  integration package split.

## 0.1.0

- Initial PyPI release of the `standard` distribution, imported as `std`.
- Provide YAML/TOML configuration and Pydantic Settings support, collection and
  file helpers, the `std` agent CLI, and optional FastAPI and AWS integrations.
