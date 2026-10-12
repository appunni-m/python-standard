from __future__ import annotations

import json
from pathlib import Path

import pytest

from std import __version__
from std.cli import main


def test_agent_guide_text_and_json(capsys) -> None:
    assert main(["guide"]) == 0
    assert "standard[fastapi]" in capsys.readouterr().out

    assert main(["guide", "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["distribution"] == "standard"
    assert payload["import"] == "std"
    assert payload["version"] == __version__


def test_version_uses_the_loaded_std_package(capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"std {__version__}"


def test_skill_show_and_install(capsys, tmp_path: Path, monkeypatch) -> None:
    assert main(["skill", "show"]) == 0
    skill = capsys.readouterr().out
    assert skill.startswith("---\n")
    assert "Standard supports Python" in skill
    assert "std --version" in skill

    monkeypatch.chdir(tmp_path)
    assert main(["skill", "install"]) == 0
    installed = tmp_path / ".agents/skills/standard-python/SKILL.md"
    assert installed.read_text(encoding="utf-8") == skill

    assert main(["skill", "install"]) == 2
    assert "refusing to overwrite" in capsys.readouterr().err


def test_skill_install_force_replaces_file(capsys, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    destination = tmp_path / "skill.md"
    destination.write_text("old", encoding="utf-8")

    assert main(["skill", "install", str(destination), "--force"]) == 0
    assert "Idiomatic Python" in destination.read_text(encoding="utf-8")


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
    assert "Idiomatic Python" in destination.read_text(encoding="utf-8")


def test_skill_install_reports_filesystem_error_without_traceback(capsys, tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("content", encoding="utf-8")

    assert main(["skill", "install", str(blocker / "skill.md")]) == 1

    stderr = capsys.readouterr().err
    assert "could not install skill" in stderr
    assert "Traceback" not in stderr
