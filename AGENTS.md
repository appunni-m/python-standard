<!-- BEGIN KATA (managed by `kata init --with-agents`) -->
Kata is the system of record for intent.

- Never `kata delete` or `kata purge` without explicit user authorization.

~~~dot
digraph kata {
  rankdir=TB; node [shape=box];

  arrive   [shape=diamond label="Work arrives"];
  search   [label="Search first:\nkata search \"<terms>\" --agent\nReuse an open issue or create one."];
  route    [shape=diamond label="Work it, or delegate it?"];

  subgraph cluster_work {
    label="";
    claim  [label="On claim or start, mark it tracked:\nkata meta set <ref> work.attention ok"];
    branch [label="If the work happens on a dedicated branch, stamp it once:\nkata meta set <ref> work.branch <branch>\nor bind at creation:\nkata create ... --meta work.branch=<branch> --idempotency-key <key>"];
    live   [label="Keep state current:\nkata meta set <ref> work.attention stuck|needs-human|ok\nkata meta set <ref> work.attention_msg \"<why>\"\nstuck = blocked; needs-human = input/review; ok = unblocked.\nRequest attention:\nkata notify <ref> --to <actor>[/<teammate>] --message <reason>"];
    claim -> branch -> live;
  }

  subgraph cluster_delegate {
    label="";
    fanout [label="Tracked children: --parent <ref>, --meta work.branch=<branch>,\n--idempotency-key <key>, --json; capture .issue.short_id.\nSubagents: distinct KATA_TEAMMATE and\nKATA_INBOX_USER=<actor>/<teammate>; keep the actor.\nRead requests: kata inbox --for <actor>[/<teammate>].\nAfter handling: kata notify <ref> --to <actor>[/<teammate>] --clear."];
    join   [label="Join with kata wait <refs> --until attention --any\nMatches needs-human or stuck; a close also completes the wait,\nand the reported reason distinguishes which. Use --timeout so a\nwrapper can tell timeout from satisfaction."];
    coord  [label="Read delegated work.*; never write it."];
    fanout -> join -> coord;
  }

  done     [shape=diamond label="Verified complete?"];
  close    [label="kata close <ref> --done\nwith a message and evidence"];
  review   [label="kata label add <ref> needs-review\nplus a comment on what remains"];
  park     [shape=diamond label="Park it?"];
  schedule [label="kata schedule <ref> <date-or-time>\nsets scheduled_on; clear with -"];
  someday  [label="kata meta set <ref> someday true --json-value\nclear with kata meta unset <ref> someday"];

  arrive -> search -> route;
  route -> claim   [label="work it"];
  route -> fanout  [label="delegate it"];
  route -> park    [label="record only"];
  live  -> done;
  coord -> done;
  done -> close    [label="yes"];
  done -> park     [label="no"];
  park -> schedule [label="start date known"];
  park -> someday  [label="start date unknown"];
  park -> review   [label="needs review"];
}
~~~

Parent links group work; they do not gate readiness, but a parent cannot close with open children.
Use --blocks <dependent> / --blocked-by <prerequisite> only for real prerequisites; they gate kata ready.
Use --related <ref> for context only. kata wait observes state without requiring a dependency edge.

One writer per key: only write your own work.*. Ignore work.* on closed issues; never write it there.
Before stopping, close completed work or update both work.attention and work.attention_msg for the handoff.

Schedule/someday defer work; deadlines don’t. kata deadline <ref> <date-or-time> sets deadline_on without changing readiness.
Reached schedules and deadlines use notify.* for the current owner, or the author when unowned; clear with kata notify <ref> --to <recipient> --clear.
<!-- END KATA -->

## Project engineering standards

These rules supplement the managed Kata instructions above. Do not edit the
managed Kata block. Keep architecture decisions in
[`docs/decisions/index.md`](docs/decisions/index.md) and the configuration
behavior contract in [`docs/configuration/index.md`](docs/configuration/index.md);
do not create a separate architecture document for choices already recorded
there.

### Architecture and public API

- The core distribution is `standard`; Python imports and the executable are
  named `std`. Core capabilities, the CLI, and the skill stay in `standard`;
  do not create separate `standard-core` or `standard-cli` distributions.
- The integration distributions are `standard-fastapi` (`std.fastapi`) and
  `standard-aws` (`std.aws`), with `standard-http` (`std.http`),
  `standard-cache` (`std.cache`), and `standard-rdbms` (`std.rdbms`) planned.
  Core extras `fastapi` and `aws` select their standalone distributions in the
  0.2.0 source. Add later extras only with an implemented provider. Core code
  must not import integration packages or their dependencies. PyPI 0.1.1 still
  bundles FastAPI and AWS; do not claim the split is released until artifacts
  and clean installs prove it.
- PyPI availability and publisher setup for all add-on project names are
  unverified. Design each API and dependency boundary before creating its
  distribution or workflow.
- Core contains configuration, `std.logging`, utility helpers, `Service`, and
  `BackgroundService(Service)`, as well as the `std` CLI and packaged skill.
  Track service lifecycle contracts and verify them before release. For
  app-level composition, settings, routes, services, and lifecycle
  conventions, follow the packaged skill and architecture page.
- Organize application code and templates by feature module, not by global
  technical-layer folders. Keep a module's API/controllers, schemas, domain or
  persistence models, repositories, services, and module-specific config with
  that module. Reserve `core/` for cross-feature infrastructure; do not add
  empty model/repository/config layers. `main.py` remains the composition root,
  `core/settings.py` aggregates module settings, and only `main.py` constructs
  `Settings()`.
- Treat the configuration contract as the source of truth for parsing,
  interpolation, merge order, source priority, errors, snapshot immutability,
  and reload behavior. Update it when those behaviors change.
- Before adding a public module, symbol, CLI command, or JSON field, check the
  existing module and schema boundaries. Update `__all__` where applicable,
  `docs/api.md`, the relevant usage guide, and the changelog in the same change.
- Keep performance claims tied to a named workload, comparable behavior,
  runtime and dependency versions, raw results, and the measured code revision.
  A target or experiment is not a measured result.

### Python style and typing

- Support CPython 3.11–3.14 and follow the settings in `pyproject.toml`.
- Ruff is the sole formatter, import sorter, linter, and style checker. Use
  `make lint`; do not add Black, isort, Flake8, or a second style tool for rules
  Ruff already enforces. Ruff targets Python 3.11, uses a 100-character line
  length, and checks `src/`, `tests/`, and `benchmarks/`.
- Mypy runs in strict mode. Use `make type`; add a rule-specific
  `type: ignore[code]` only when necessary and explain the reason next to it.
  Keep suppressions narrow and remove stale ones. Ruff rejects unused `noqa`
  comments.
- Prefer a direct fix over a suppression. Do not disable a lint rule broadly
  to make a check pass. Public APIs need useful type annotations and docstrings;
  the configured docstring exceptions are recorded in `pyproject.toml`.

### Verification and documentation

- Run `make check` for the tox Python matrix available locally, formatting and
  lint checks, strict typing, coverage, and a clean documentation build. CI
  explicitly runs CPython 3.11–3.14.
- Run `make test-e2e` for changes to packaged consumer behavior or optional
  dependency boundaries when Docker is available. The CI container job uses
  Testcontainers. Keep the configured 90% coverage floor.
- Run `make docs-build` after documentation or navigation edits. Check claims
  against source, package metadata, CI, or a primary reference; mark plans,
  historical evidence, and current verification status distinctly.
- For configuration changes, add regression coverage for the changed contract
  and preserve the reference-parity cases. For performance changes, run the
  documented benchmark only after correctness preflight and retain its raw
  result.
