# Contributing

## Local development

```bash
make install
make check
make test-e2e
make docs-build
```

The project targets CPython 3.11–3.14 and uses MIT licensing. Keep the core install small, preserve the documented config compatibility and error contracts, and isolate integrations behind their named extras. Update the public API documentation when behavior changes.

Thank you for helping shape Standard. It is an early-stage alpha library, so proposals and clear examples are especially useful.

## Before proposing a feature

1. Check the [current decisions and open questions](decisions/index.md).
2. Describe the user problem and one or two realistic usage examples.
3. For configuration behavior, include source inputs, expected precedence, validation, and failure behavior.
4. For performance proposals, state the comparable workload and what must remain behaviorally identical.

## Documentation changes

Install the documentation toolchain and preview the site:

```bash
python3 -m venv .venv
. .venv/bin/activate
make docs-install
make docs-serve
```

Before submitting, build the complete site:

```bash
make docs-build
```

Keep pages focused. Label a statement as a fact, proposal, or open decision. Avoid presenting unmeasured speed targets as results.

## Code changes

Follow the repository rules in [`AGENTS.md`](https://github.com/appunni-m/python-standard/blob/main/AGENTS.md). Run `make check` before submitting. It runs the supported Python test environments available on your machine, Ruff formatting and lint checks, strict mypy, coverage, and a clean docs build. Run `make test-e2e` separately when Docker is available; CI runs the Testcontainers suite in its own Docker-enabled job.

Use `std skill show` for the project's idiomatic Python, application architecture, and public API guidance; the checks below enforce the repository-specific rules.

Ruff is the project's single formatter, linter, and style checker. The formatter and selected lint rules live in `pyproject.toml`; do not add overlapping tools such as Black, isort, or Flake8 unless a specific uncovered check justifies it. The configured Ruff exceptions are limited to constructor and special-method docstrings, with test module/function docstrings handled separately.

Prefer fixing the cause over suppressing a diagnostic. When a real type-checker limitation or unavoidable lint exception remains, use a rule-specific suppression at the narrowest scope and explain the reason beside it. Mypy requires error codes on `type: ignore` comments, and Ruff checks for unused `noqa` comments. Avoid file-wide suppressions and broad rule disables; remove a suppression when its reason no longer applies. See the official [Ruff suppression guidance](https://docs.astral.sh/ruff/linter/#error-suppression) and [mypy error-code guidance](https://mypy.readthedocs.io/en/stable/error_code_list2.html).

Keep type annotations compatible with strict mypy. Add regression cases for behavior changes, preserve the documented configuration contract, and update the relevant API or usage guide when public behavior changes.
