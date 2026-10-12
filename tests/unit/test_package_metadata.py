from __future__ import annotations

import tomllib
from pathlib import Path


def test_core_distribution_owns_only_core_modules_and_selects_addons() -> None:
    root = Path(__file__).resolve().parents[2]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]

    assert project["name"] == "standard"
    assert project["version"] == "0.2.0"
    assert project["requires-python"] == ">=3.11"
    assert set(project["dependencies"]) == {
        "PyYAML>=6,<7",
        "pydantic-settings>=2.6,<3",
    }
    assert (root / "src/std/py.typed").is_file()
    assert 'std = "std.cli:main"' in (root / "pyproject.toml").read_text(encoding="utf-8")
    assert project["optional-dependencies"] == {
        "fastapi": ["standard-fastapi>=0.1,<0.2"],
        "aws": ["standard-aws>=0.1,<0.2"],
        "http": ["standard-http>=0.1,<0.2"],
        "cache": ["standard-cache>=0.1,<0.2"],
        "rdbms": ["standard-rdbms>=0.1,<0.2"],
    }

    wheel = metadata["tool"]["hatch"]["build"]["targets"]["wheel"]
    core_paths = {
        "src/std/__init__.py",
        "src/std/cli.py",
        "src/std/collections.py",
        "src/std/config",
        "src/std/files.py",
        "src/std/logging.py",
        "src/std/service.py",
        "src/std/py.typed",
    }
    assert set(wheel["only-include"]) == core_paths
    assert not any("/aws" in path or "/fastapi" in path for path in core_paths)
    assert wheel["force-include"] == {
        "src/std/skills/standard-idiomatic-python/SKILL.md": (
            "std/skills/standard-idiomatic-python/SKILL.md"
        )
    }
    skill_path = root / "src/std/skills/standard-idiomatic-python/SKILL.md"
    assert skill_path.is_file()
    assert "name: standard-idiomatic-python" in skill_path.read_text(encoding="utf-8")

    sdist = metadata["tool"]["hatch"]["build"]["targets"]["sdist"]
    assert set(sdist["only-include"]) == {
        "pyproject.toml",
        "README.md",
        "LICENSE",
        *core_paths,
        "src/std/skills/standard-idiomatic-python/SKILL.md",
    }
    assert sdist["ignore-vcs"] is False


def test_addon_distributions_own_subpackages_and_their_dependencies() -> None:
    root = Path(__file__).resolve().parents[2]
    expected = {
        "standard-fastapi": {
            "subpackage": "fastapi",
            "dependencies": ["standard>=0.2.0,<0.3", "fastapi>=0.115,<1"],
        },
        "standard-aws": {
            "subpackage": "aws",
            "dependencies": ["standard>=0.2.0,<0.3", "aioboto3>=13,<16"],
        },
        "standard-http": {
            "subpackage": "http",
            "dependencies": ["standard>=0.2.0,<0.3", "httpx>=0.27,<1"],
        },
        "standard-cache": {
            "subpackage": "cache",
            "dependencies": ["standard>=0.2.0,<0.3", "redis[hiredis]>=5,<8"],
        },
        "standard-rdbms": {
            "subpackage": "rdbms",
            "dependencies": [
                "standard>=0.2.0,<0.3",
                "pydantic>=2.6,<3",
                "SQLAlchemy[asyncio]>=2.0,<3",
                "aiosqlite>=0.19,<1",
                "asyncpg>=0.29,<1",
                "aiomysql>=0.2,<1",
                "cryptography>=41",
            ],
        },
    }

    for distribution, details in expected.items():
        project_dir = root / "packages" / distribution
        metadata = tomllib.loads((project_dir / "pyproject.toml").read_text(encoding="utf-8"))
        project = metadata["project"]
        subpackage = details["subpackage"]
        source = f"src/std/{subpackage}"

        assert project["name"] == distribution
        assert project["version"] == "0.1.0"
        assert project["requires-python"] == ">=3.11"
        assert project["dependencies"] == details["dependencies"]
        assert (project_dir / source / "__init__.py").is_file()
        assert (project_dir / "LICENSE").is_file()
        assert (project_dir / "README.md").is_file()

        wheel = metadata["tool"]["hatch"]["build"]["targets"]["wheel"]
        assert wheel["only-include"] == [source]
        assert wheel["sources"] == ["src"]

        sdist = metadata["tool"]["hatch"]["build"]["targets"]["sdist"]
        assert set(sdist["only-include"]) == {
            "pyproject.toml",
            "README.md",
            "LICENSE",
            source,
        }


def test_addon_release_workflows_match_project_names_and_tag_versions() -> None:
    root = Path(__file__).resolve().parents[2]
    workflows = {
        "standard-fastapi": "release-fastapi.yml",
        "standard-aws": "release-aws.yml",
        "standard-http": "release-http.yml",
        "standard-cache": "release-cache.yml",
        "standard-rdbms": "release-rdbms.yml",
    }

    for distribution, workflow_name in workflows.items():
        workflow = (root / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")
        assert f'"{distribution}-v*"' in workflow
        assert f'Path("packages/{distribution}/pyproject.toml")' in workflow
        assert f'expected_tag = f"{distribution}-v{{version}}"' in workflow
        assert f"python -m build packages/{distribution} --outdir dist" in workflow
        assert f"https://pypi.org/project/{distribution}/" in workflow
        assert 'tag_prefix = f"{project_name}-v"' in workflow
        assert "version = release_tag.removeprefix(tag_prefix)" in workflow
