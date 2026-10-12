from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from std import __version__

SHARED_TAG_PATTERN = r"^v(?P<version>\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?)$"


def test_core_distribution_owns_only_core_modules_and_selects_addons() -> None:
    root = Path(__file__).resolve().parents[2]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]

    assert project["name"] == "standard"
    assert project["dynamic"] == ["version"]
    assert "version" not in project
    assert project["requires-python"] == ">=3.11"
    assert any(
        requirement.startswith("hatch-vcs") for requirement in metadata["build-system"]["requires"]
    )
    assert set(project["dependencies"]) == {
        "PyYAML>=6,<7",
        "pydantic-settings>=2.6,<3",
    }
    assert (root / "src/std/py.typed").is_file()
    assert 'std = "std.cli:main"' in (root / "pyproject.toml").read_text(encoding="utf-8")
    assert project["optional-dependencies"] == {
        "fastapi": ["standard-fastapi>=0.1.1.dev0,<1"],
        "aws": ["standard-aws>=0.1.1.dev0,<1"],
        "http": ["standard-http>=0.1.1.dev0,<1"],
        "cache": ["standard-cache>=0.1.1.dev0,<1"],
        "rdbms": ["standard-rdbms>=0.1.1.dev0,<1"],
    }
    assert metadata["tool"]["hatch"]["version"] == {
        "source": "vcs",
        "tag-pattern": SHARED_TAG_PATTERN,
        "raw-options": {"search_parent_directories": True},
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
            "dependencies": ["standard>=0.1.1.dev0,<1", "fastapi>=0.115,<1"],
        },
        "standard-aws": {
            "subpackage": "aws",
            "dependencies": ["standard>=0.1.1.dev0,<1", "aioboto3>=13,<16"],
        },
        "standard-http": {
            "subpackage": "http",
            "dependencies": ["standard>=0.1.1.dev0,<1", "httpx>=0.27,<1"],
        },
        "standard-cache": {
            "subpackage": "cache",
            "dependencies": ["standard>=0.1.1.dev0,<1", "redis[hiredis]>=5,<8"],
        },
        "standard-rdbms": {
            "subpackage": "rdbms",
            "dependencies": [
                "standard>=0.1.1.dev0,<1",
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
        assert project["dynamic"] == ["version"]
        assert "version" not in project
        assert metadata["tool"]["hatch"]["version"] == {
            "source": "vcs",
            "tag-pattern": SHARED_TAG_PATTERN,
            "raw-options": {"search_parent_directories": True},
        }
        assert project["requires-python"] == ">=3.11"
        assert any(
            requirement.startswith("hatch-vcs")
            for requirement in metadata["build-system"]["requires"]
        )
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


def test_public_version_matches_installed_distribution_metadata() -> None:
    try:
        installed_version = version("standard")
    except PackageNotFoundError:
        assert __version__ == "0+unknown"
    else:
        assert __version__ == installed_version


def test_one_release_workflow_builds_all_projects_from_the_shared_tag() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow_path = root / ".github" / "workflows" / "release.yml"
    workflow = workflow_path.read_text(encoding="utf-8")

    assert '"v*"' in workflow
    assert "python scripts/release.py verify-source --tag" in workflow
    assert "python scripts/release.py prepare --tag" in workflow
    assert "python scripts/release.py verify-artifacts" in workflow
    assert "SETUPTOOLS_SCM_PRETEND_VERSION" in workflow
    assert workflow.count("pypa/gh-action-pypi-publish@") == 6
    for distribution, project_dir in {
        "standard": ".",
        "standard-fastapi": "packages/standard-fastapi",
        "standard-aws": "packages/standard-aws",
        "standard-http": "packages/standard-http",
        "standard-cache": "packages/standard-cache",
        "standard-rdbms": "packages/standard-rdbms",
    }.items():
        build_command = (
            f"python -m build {project_dir} --outdir release-bundle/distributions/{distribution}"
        )
        assert build_command in workflow
        assert f"name: Publish {distribution}" in workflow
    for distribution in (
        "fastapi",
        "aws",
        "http",
        "cache",
        "rdbms",
    ):
        assert not (root / ".github" / "workflows" / f"release-{distribution}.yml").exists()
