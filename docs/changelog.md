# Changelog

This file records user-visible changes. The repository version can be newer than the latest version published on PyPI; see the [publishing guide](publishing.md) for the current release state.

## Unreleased (repository version 0.2.0)

- Add `std.service.Service` and `BackgroundService` lifecycle management, health checks, state reporting, graceful shutdown, and cancellation handling.
- Complete `standard-fastapi` with validated app configuration, injected lifespan management, API-token auth, health checks, and structured request logging.
- Add `std.logging` with development/test console defaults, staging/production JSON output, stdout/stderr selection, severity overrides, structured context fields, and custom standard-library formatter support.
- Move FastAPI and AWS integration code into independently built `standard-fastapi` and `standard-aws` projects while keeping core and the `std` CLI in `standard`.
- Point the `fastapi` and `aws` convenience extras at their add-on distributions, and verify their installation from built wheels in the Testcontainers consumer suite.
- Add separate annotated-tag release workflows for `standard-fastapi` and `standard-aws`, following the verified core Trusted Publishing workflow.
- Add independently built `standard-http`, `standard-cache`, and `standard-rdbms` distributions under `std.http`, `std.cache`, and `std.rdbms`, with focused guides and Testcontainers-backed service coverage.
- Add `http`, `cache`, and `rdbms` convenience extras, clean wheel-install coverage, and dedicated annotated-tag release workflows with checksum verification and Trusted Publishing.
- Update the CLI guide, idiomatic-Python skill, docs, and templates for the standalone package layout.
- Continue the feature-first application template, YAML settings, dependency injection, route/service, and background lifecycle guidance.

## 0.1.1

- Publish the `standard` distribution through GitHub Actions Trusted Publishing.
- Keep the FastAPI and AWS import modules bundled in this release; the distribution split is part of the unreleased 0.2.0 source.

## 0.1.0

- Initial PyPI release of the `standard` distribution, imported as `std`.
- Provide YAML/TOML configuration and Pydantic Settings support, collection and file helpers, the `std` agent CLI, and optional FastAPI and AWS integrations.
