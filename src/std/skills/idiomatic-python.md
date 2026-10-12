---
name: standard-idiomatic-python
description: Write readable, typed Python that follows Standard's public APIs, error contracts, tests, and documentation conventions.
---

# Idiomatic Python with Standard

Use this skill when creating or changing Python code in a project that uses Standard.

## Before editing

1. Run `std --version` to identify the installed Standard version, then run `std guide` for project-specific directions.
2. Read the relevant API documentation and inspect the current function signatures. Do not guess names or rely on undocumented internals.
3. Follow the repository's `pyproject.toml`, formatter, linter, type checker, and test commands. Keep changes within the requested scope.

## Python style

- Target the project's declared Python floor. Standard supports Python 3.11 and newer.
- Prefer small functions, explicit names, standard-library types, and straightforward control flow.
- Add parameter and return annotations to public functions. Use `collections.abc` protocols for inputs when they describe the real contract.
- Use immutable values for shared configuration. Avoid mutable defaults; use `None` or a factory.
- Raise a specific exception at the boundary where invalid input is understood. Preserve useful context while keeping secrets, tokens, and raw configuration values out of errors and logs.
- Use context managers for resources and `pathlib.Path` for filesystem paths.
- Avoid broad exception handling. When an integration error must be redacted, catch at that integration boundary and emit a stable, useful public error.
- Keep optional integrations lazy or isolated. Core imports must not require an optional extra.
- Prefer correcting a lint or typing issue over suppressing it. If a narrow suppression is necessary, include its rule or mypy error code and explain the reason next to it; remove it when it is no longer needed.

## Using Standard

- Load YAML/TOML with `std.config.ConfigManager`; use its immutable `snapshot` for reads and `to_dict()` when an isolated mutable copy is needed.
- Use `reload()` only when configuration should be explicitly refreshed. A failed reload leaves the previous snapshot active.
- Use `std.collections.deep_merge` for the documented recursive mapping, list-append, and later-value-wins behavior.
- Use `std.files.atomic_write_text` when a complete text replacement must be visible atomically. Its default mode is owner-only.
- The intended FastAPI distribution form is `standard[fastapi]`; the PyPI name is currently occupied by an unrelated project. From this checkout, install with `pip install -e '.[fastapi]'` before importing `std.fastapi`.
- The intended AWS distribution form is `standard[aws]`; from this checkout, install with `pip install -e '.[aws]'` before importing `std.aws`. Pass a configured client when the application owns AWS client lifecycle.

## Tests and docs

- Add a focused regression test for each behavior change. Cover both the expected result and important failure cases.
- Prefer `tmp_path`, injected environment mappings, and fake clients over shared process state or live cloud calls.
- Use Testcontainers only for real container boundaries, and keep ordinary unit tests independent of Docker.
- Test the public API as a consumer would import it. Do not make tests depend on private helpers when a public call can prove the behavior.
- Update the relevant usage example and API reference when behavior changes.
- Run formatting, lint, types, and the narrow test set first, then the full suite.

## Agent response

State the files changed, the public behavior added or changed, and the exact checks run. Distinguish measured results from assumptions. Do not claim performance or compatibility that the executed checks do not establish.
