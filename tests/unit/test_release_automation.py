from __future__ import annotations

import hashlib
import io
import shutil
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest
from scripts import release
from scripts.release import prepare_release, verify_artifacts, version_from_tag


def test_version_is_taken_from_one_standard_release_tag() -> None:
    assert version_from_tag("v0.2.0") == "0.2.0"
    assert version_from_tag("v1.4.2rc1") == "1.4.2rc1"
    with pytest.raises(ValueError, match="Release tag must match"):
        version_from_tag("standard-fastapi-v0.2.0")


def test_prepare_pins_every_distribution_to_the_shared_tag(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    for relative_path in release.PROJECTS.values():
        destination = tmp_path / relative_path
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repository / relative_path / "pyproject.toml", destination / "pyproject.toml")

    prepare_release(tmp_path, "v0.2.0")

    core = tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert core["optional-dependencies"] == {
        "fastapi": ["standard-fastapi==0.2.0"],
        "aws": ["standard-aws==0.2.0"],
        "http": ["standard-http==0.2.0"],
        "cache": ["standard-cache==0.2.0"],
        "rdbms": ["standard-rdbms==0.2.0"],
    }
    for distribution in release.PROJECTS:
        if distribution == "standard":
            continue
        provider = tomllib.loads(
            (tmp_path / release.PROJECTS[distribution] / "pyproject.toml").read_text(
                encoding="utf-8"
            )
        )["project"]
        assert "standard==0.2.0" in provider["dependencies"]


def _metadata(distribution: str, version: str) -> str:
    requirements = (
        [
            f'Requires-Dist: {provider}=={version}; extra == "{extra}"'
            for provider, extra in (
                ("standard-fastapi", "fastapi"),
                ("standard-aws", "aws"),
                ("standard-http", "http"),
                ("standard-cache", "cache"),
                ("standard-rdbms", "rdbms"),
            )
        ]
        if distribution == "standard"
        else [f"Requires-Dist: standard=={version}"]
    )
    return "\n".join(
        ["Metadata-Version: 2.3", f"Name: {distribution}", f"Version: {version}", *requirements, ""]
    )


def _write_test_artifact_pair(directory: Path, distribution: str, version: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    wheel_name = f"{distribution.replace('-', '_')}-{version}-py3-none-any.whl"
    metadata_name = f"{distribution.replace('-', '_')}-{version}.dist-info/METADATA"
    with zipfile.ZipFile(directory / wheel_name, "w") as wheel:
        wheel.writestr(metadata_name, _metadata(distribution, version))

    sdist = directory / f"{distribution}-{version}.tar.gz"
    metadata_bytes = _metadata(distribution, version).encode()
    info = tarfile.TarInfo(name=f"{distribution}-{version}/PKG-INFO")
    info.size = len(metadata_bytes)
    with tarfile.open(sdist, "w:gz") as archive:
        archive.addfile(info, fileobj=io.BytesIO(metadata_bytes))


def test_artifact_gate_checks_all_distributions_and_exact_dependency_pins(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    artifacts = tmp_path / "distributions"
    for distribution in release.PROJECTS:
        _write_test_artifact_pair(artifacts / distribution, distribution, "0.2.0")

    verify_artifacts(repository, "v0.2.0", artifacts)

    wrong_version = artifacts / "standard-aws" / "standard_aws-0.2.0-py3-none-any.whl"
    wrong_version.unlink()
    with zipfile.ZipFile(wrong_version, "w") as wheel:
        wheel.writestr(
            "standard_aws-0.2.0.dist-info/METADATA",
            _metadata("standard-aws", "0.2.1"),
        )
    with pytest.raises(ValueError, match="declares 0.2.1, expected 0.2.0"):
        verify_artifacts(repository, "v0.2.0", artifacts)


def test_stage_skips_matching_files_and_stages_only_missing_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = Path(__file__).resolve().parents[2]
    artifacts = tmp_path / "distributions"
    published: dict[str, dict[str, str]] = {}
    for distribution in release.PROJECTS:
        project_dir = artifacts / distribution
        project_dir.mkdir(parents=True)
        filenames = [f"{distribution}-0.2.0.whl", f"{distribution}-0.2.0.tar.gz"]
        for filename in filenames:
            path = project_dir / filename
            path.write_text(f"{distribution}:{filename}", encoding="utf-8")
        if distribution in {"standard", "standard-fastapi"}:
            selected = filenames if distribution == "standard-fastapi" else filenames[:1]
            published[distribution] = {
                filename: hashlib.sha256((project_dir / filename).read_bytes()).hexdigest()
                for filename in selected
            }
        else:
            published[distribution] = {}

    monkeypatch.setattr(release, "_published_files", lambda name, _version: published[name])
    output = tmp_path / "github-output"
    staged = tmp_path / "pypi-publish"
    release.stage_for_pypi(repository, "v0.2.0", artifacts, staged, output)

    states = dict(line.split("=", maxsplit=1) for line in output.read_text().splitlines())
    assert states["standard_missing"] == "true"
    assert states["standard_fastapi_missing"] == "false"
    assert states["standard_aws_missing"] == "true"
    assert len(list((staged / "standard").iterdir())) == 1
    assert list((staged / "standard-fastapi").iterdir()) == []
    assert len(list((staged / "standard-aws").iterdir())) == 2
