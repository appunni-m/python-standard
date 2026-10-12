"""Agent-facing command line guidance for the Standard library."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from importlib import resources
from pathlib import Path

from std import __version__
from std.files import atomic_write_text

_DISTRIBUTION_NAME = "standard"

_GUIDE = """Standard targets the `standard` distribution and is imported as `std`.

Use `std.config.ConfigManager` for YAML/TOML configuration and Pydantic Settings
sources. Snapshots are immutable; call `to_dict()` for an isolated mutable copy.
`reload()` is explicit and atomic. Core helpers are `std.collections` and
`std.files`. FastAPI and AWS adapters are optional: install
`standard[fastapi]` or `standard[aws]` before importing `std.fastapi` or
`std.aws`. The existing PyPI project named `standard` is unrelated; until the
name is resolved, install extras from this checkout with `pip install -e '.[fastapi]'`
or `pip install -e '.[aws]'`.

Run `std skill show` to print the portable idiomatic-Python skill. Run
`std skill install` to copy it to `.agents/skills/standard-python/SKILL.md`.
"""


def _skill_text() -> str:
    return (
        resources.files("std").joinpath("skills", "idiomatic-python.md").read_text(encoding="utf-8")
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="std",
        description="Standard library and coding-agent guidance",
    )
    parser.add_argument("--version", action="version", version=f"std {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    guide = subparsers.add_parser("guide", help="show concise instructions for coding agents")
    guide.add_argument("--format", choices=("text", "json"), default="text")

    skill = subparsers.add_parser("skill", help="show or install the idiomatic Python skill")
    skill_subparsers = skill.add_subparsers(dest="skill_command", required=True)
    skill_subparsers.add_parser("show", help="print the portable skill document")
    skill_subparsers.add_parser("path", help="print the packaged skill resource path")
    install = skill_subparsers.add_parser(
        "install", help="copy the skill into the current repository"
    )
    install.add_argument(
        "destination",
        nargs="?",
        default=".agents/skills/standard-python/SKILL.md",
        help="destination file (default: .agents/skills/standard-python/SKILL.md)",
    )
    install.add_argument("--force", action="store_true", help="replace an existing destination")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``std`` command."""
    args = _parser().parse_args(argv)
    if args.command == "guide":
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "distribution": _DISTRIBUTION_NAME,
                        "import": "std",
                        "version": __version__,
                        "guide": _GUIDE,
                    }
                )
            )
        else:
            print(_GUIDE.rstrip())
        return 0
    if args.skill_command == "show":
        print(_skill_text(), end="")
        return 0
    if args.skill_command == "path":
        print(resources.files("std").joinpath("skills", "idiomatic-python.md"))
        return 0
    target = Path(args.destination)
    if (target.exists() or target.is_symlink()) and not args.force:
        print(f"refusing to overwrite existing path: {target} (pass --force)", file=sys.stderr)
        return 2
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(target, _skill_text(), mode=0o644)
    except OSError as error:
        print(f"could not install skill at {target}: {error}", file=sys.stderr)
        return 1
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
