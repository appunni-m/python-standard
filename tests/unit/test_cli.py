from __future__ import annotations

import json
from pathlib import Path

import pytest

from std import __version__
from std.cli import main


def test_agent_guide_text_and_json(capsys) -> None:
    assert main(["guide"]) == 0
    text_guide = capsys.readouterr().out
    assert "standard[fastapi]" in text_guide
    assert "python-standard/" in text_guide

    assert main(["guide", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    assert payload["distribution"] == "standard"
    assert payload["import"] == "std"
    assert payload["command"] == "std"
    assert payload["version"] == __version__
    assert payload["requires_python"] == ">=3.11"
    assert payload["install"]["fastapi"] == "python -m pip install 'standard[fastapi]'"
    fastapi_module = next(
        module for module in payload["modules"] if module["name"] == "std.fastapi"
    )
    assert "token auth" in fastapi_module["purpose"]
    assert {module["name"] for module in payload["modules"]} == {
        "std.config",
        "std.collections",
        "std.files",
        "std.logging",
        "std.service",
        "std.fastapi",
        "std.aws",
    }
    assert payload["skill"]["name"] == "standard-idiomatic-python"
    assert payload["skill"]["install_path"] == (".agents/skills/standard-idiomatic-python/SKILL.md")
    assert payload["docs"]["api_reference"].endswith("/api/")
    assert payload["docs"]["logging"].endswith("/logging/")
    assert payload["docs"]["changelog"].endswith("/changelog/")


def test_version_uses_the_loaded_std_package(capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"std {__version__}"


def test_skill_show_and_install(capsys, tmp_path: Path, monkeypatch) -> None:
    assert main(["skill", "show"]) == 0
    skill = capsys.readouterr().out
    assert skill.startswith("---\n")
    assert "name: standard-idiomatic-python" in skill
    assert "std --version" in skill

    monkeypatch.chdir(tmp_path)
    assert main(["skill", "install"]) == 0
    installed = tmp_path / ".agents/skills/standard-idiomatic-python/SKILL.md"
    assert installed.read_text(encoding="utf-8") == skill

    assert main(["skill", "install"]) == 2
    assert "refusing to overwrite" in capsys.readouterr().err


def test_skill_install_force_replaces_file(capsys, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    destination = tmp_path / "skill.md"
    destination.write_text("old", encoding="utf-8")

    assert main(["skill", "install", str(destination), "--force"]) == 0
    assert "# Idiomatic Python with Standard" in destination.read_text(encoding="utf-8")


def test_skill_path_is_an_existing_filesystem_path(capsys) -> None:
    assert main(["skill", "path"]) == 0
    path = Path(capsys.readouterr().out.strip())
    assert path.name == "SKILL.md"
    assert path.parent.name == "standard-idiomatic-python"
    assert path.is_file()


def test_skill_path_explains_non_filesystem_resources(
    capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("std.cli._skill_resource", lambda: object())

    assert main(["skill", "path"]) == 1

    error = capsys.readouterr().err
    assert "not a filesystem path" in error
    assert "std skill show" in error


def test_skill_install_refuses_dangling_symlink(capsys, tmp_path: Path) -> None:
    destination = tmp_path / "skill.md"
    try:
        destination.symlink_to(tmp_path / "missing.md")
    except (NotImplementedError, OSError):
        pytest.skip("symlink creation is unavailable")

    assert main(["skill", "install", str(destination)]) == 2

    assert destination.is_symlink()
    assert "refusing to overwrite existing path" in capsys.readouterr().err


def test_skill_install_force_replaces_dangling_symlink(tmp_path: Path) -> None:
    destination = tmp_path / "skill.md"
    try:
        destination.symlink_to(tmp_path / "missing.md")
    except (NotImplementedError, OSError):
        pytest.skip("symlink creation is unavailable")

    assert main(["skill", "install", str(destination), "--force"]) == 0

    assert not destination.is_symlink()
    assert "# Idiomatic Python with Standard" in destination.read_text(encoding="utf-8")


def test_skill_install_reports_filesystem_error_without_traceback(capsys, tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("content", encoding="utf-8")

    assert main(["skill", "install", str(blocker / "skill.md")]) == 1

    stderr = capsys.readouterr().err
    assert "could not install skill" in stderr
    assert "Traceback" not in stderr
