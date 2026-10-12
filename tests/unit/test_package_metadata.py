from __future__ import annotations

import tomllib
from pathlib import Path


def test_distribution_and_import_names_and_optional_extras_are_explicit() -> None:
    root = Path(__file__).resolve().parents[2]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]

    assert project["name"] == "standard"
    assert project["requires-python"] == ">=3.11"
    assert set(project["dependencies"]) == {"PyYAML>=6,<7", "pydantic-settings>=2.6,<3"}
    assert (root / "src/std/py.typed").is_file()
    assert 'std = "std.cli:main"' in (root / "pyproject.toml").read_text(encoding="utf-8")
    extras = project["optional-dependencies"]
    assert extras["fastapi"] == ["fastapi>=0.115,<1"]
    assert extras["aws"] == ["boto3>=1.35,<2"]
    assert set(extras) == {"fastapi", "aws"}

    wheel = metadata["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel["packages"] == ["src/std"]
    assert wheel["force-include"] == {
        "src/std/skills/idiomatic-python.md": "std/skills/idiomatic-python.md"
    }
    assert (root / "src/std/skills/idiomatic-python.md").is_file()

    sdist = metadata["tool"]["hatch"]["build"]["targets"]["sdist"]
    assert set(sdist["only-include"]) == {"pyproject.toml", "README.md", "LICENSE", "src/std"}
    assert sdist["ignore-vcs"] is False
