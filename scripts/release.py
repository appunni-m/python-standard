"""Validate and stage the lockstep releases built from the shared Git tag."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tarfile
import tomllib
import zipfile
from email.message import Message
from email.parser import Parser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

PROJECTS = {
    "standard": Path("."),
    "standard-fastapi": Path("packages/standard-fastapi"),
    "standard-aws": Path("packages/standard-aws"),
    "standard-http": Path("packages/standard-http"),
    "standard-cache": Path("packages/standard-cache"),
    "standard-rdbms": Path("packages/standard-rdbms"),
}
PROVIDERS = tuple(name for name in PROJECTS if name != "standard")
EXTRA_NAMES = {
    "standard-fastapi": "fastapi",
    "standard-aws": "aws",
    "standard-http": "http",
    "standard-cache": "cache",
    "standard-rdbms": "rdbms",
}
TAG_PATTERN = r"^v(?P<version>\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?)$"
TAG_RE = re.compile(TAG_PATTERN)
USER_AGENT = "standard-release-verifier/1 (+https://github.com/appunni-m/python-standard)"


def version_from_tag(tag: str) -> str:
    """Return the PEP 440 version in a supported shared release tag."""
    match = TAG_RE.fullmatch(tag)
    if match is None:
        raise ValueError(f"Release tag must match vX.Y.Z (or a/b/rc prerelease): {tag!r}")
    return match.group("version")


def _load_project(project_root: Path, distribution: str) -> dict[str, Any]:
    """Read and validate one distribution's pyproject metadata."""
    path = project_root / PROJECTS[distribution] / "pyproject.toml"
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    project = document.get("project")
    if not isinstance(project, dict):
        raise ValueError(f"{path} has no [project] table")
    if project.get("name") != distribution:
        raise ValueError(f"{path} declares {project.get('name')!r}, expected {distribution!r}")
    return document


def verify_source(project_root: Path, tag: str) -> str:
    """Check every project derives its version from the same release-tag pattern."""
    version = version_from_tag(tag)
    for distribution in PROJECTS:
        document = _load_project(project_root, distribution)
        project = document["project"]
        build_system = document.get("build-system", {})
        build_requires = build_system.get("requires", []) if isinstance(build_system, dict) else []
        dynamic = project.get("dynamic", [])
        hatch_version = document.get("tool", {}).get("hatch", {}).get("version", {})
        raw_options = hatch_version.get("raw-options", {})
        if "version" in project:
            raise ValueError(f"{distribution} has a static project.version")
        if "version" not in dynamic:
            raise ValueError(f"{distribution} must declare project.dynamic = ['version']")
        if not any(str(requirement).startswith("hatch-vcs") for requirement in build_requires):
            raise ValueError(f"{distribution} does not install hatch-vcs in its build environment")
        if hatch_version.get("source") != "vcs" or hatch_version.get("tag-pattern") != TAG_PATTERN:
            raise ValueError(f"{distribution} does not use the shared vX.Y.Z tag pattern")
        if raw_options.get("search_parent_directories") is not True:
            raise ValueError(
                f"{distribution} must find the repository tag from its project directory"
            )

    print(f"All six distributions derive their version from {tag} ({version})")
    return version


def _pin_requirement(text: str, distribution: str, version: str) -> str:
    """Replace the one declared requirement for a distribution with an exact release pin."""
    pattern = re.compile(
        rf"(?P<quote>['\"]){re.escape(distribution)}"
        rf"(?:\[[^\]]+\])?\s*(?:===|==|~=|!=|<=|>=|<|>)[^'\"]*(?P=quote)"
    )
    replacement_count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal replacement_count
        replacement_count += 1
        return f"{match.group('quote')}{distribution}=={version}{match.group('quote')}"

    updated = pattern.sub(replace, text)
    if replacement_count != 1:
        raise ValueError(
            f"Expected one {distribution!r} requirement to pin, found {replacement_count}"
        )
    return updated


def prepare_release(project_root: Path, tag: str) -> str:
    """Pin every cross-distribution dependency to the version selected by the shared tag."""
    version = verify_source(project_root, tag)
    for distribution in PROVIDERS:
        core_path = project_root / "pyproject.toml"
        core_text = core_path.read_text(encoding="utf-8")
        core_path.write_text(_pin_requirement(core_text, distribution, version), encoding="utf-8")

        provider_path = project_root / PROJECTS[distribution] / "pyproject.toml"
        provider_text = provider_path.read_text(encoding="utf-8")
        provider_path.write_text(
            _pin_requirement(provider_text, "standard", version),
            encoding="utf-8",
        )

    for distribution in PROJECTS:
        document = _load_project(project_root, distribution)
        project = document["project"]
        if distribution == "standard":
            optional = project.get("optional-dependencies", {})
            for provider, extra in EXTRA_NAMES.items():
                requirements = optional.get(extra, [])
                if requirements != [f"{provider}=={version}"]:
                    raise ValueError(f"standard[{extra}] is not pinned to {provider}=={version}")
        else:
            dependencies = project.get("dependencies", [])
            if f"standard=={version}" not in dependencies:
                raise ValueError(f"{distribution} is not pinned to standard=={version}")

    print(f"Pinned all provider extras and core dependencies to {version}")
    return version


def _normalized_name(name: str) -> str:
    """Normalize a project name for comparison with wheel metadata."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _distribution_metadata(path: Path) -> Message:
    """Read wheel METADATA or source archive PKG-INFO without extracting files."""
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise ValueError(f"{path.name} must contain exactly one .dist-info/METADATA")
            payload = archive.read(names[0]).decode("utf-8")
    else:
        with tarfile.open(path, mode="r:gz") as archive:
            members = [
                member
                for member in archive.getmembers()
                if member.isfile() and Path(member.name).name == "PKG-INFO"
            ]
            if len(members) != 1:
                raise ValueError(f"{path.name} must contain exactly one PKG-INFO")
            stream = archive.extractfile(members[0])
            if stream is None:
                raise ValueError(f"Unable to read PKG-INFO from {path.name}")
            payload = stream.read().decode("utf-8")
    return Parser().parsestr(payload)


def verify_artifacts(project_root: Path, tag: str, artifact_root: Path) -> None:
    """Require one wheel and source archive per project with matching metadata and pins."""
    version = verify_source(project_root, tag)
    for distribution in PROJECTS:
        project_dir = artifact_root / distribution
        wheels = sorted(project_dir.glob("*.whl"))
        sdists = sorted(project_dir.glob("*.tar.gz"))
        if len(wheels) != 1 or len(sdists) != 1:
            raise ValueError(f"{distribution} must have one wheel and one source archive")
        for artifact in (wheels[0], sdists[0]):
            metadata = _distribution_metadata(artifact)
            if _normalized_name(metadata.get("Name", "")) != distribution:
                raise ValueError(f"{artifact.name} metadata does not declare {distribution}")
            if metadata.get("Version") != version:
                raise ValueError(
                    f"{artifact.name} declares {metadata.get('Version')}, expected {version}"
                )
            requirements = metadata.get_all("Requires-Dist", [])
            if distribution == "standard":
                for provider, extra in EXTRA_NAMES.items():
                    expected = f"{provider}=={version}"
                    if not any(requirement.startswith(expected) for requirement in requirements):
                        raise ValueError(
                            f"{artifact.name} does not pin extra {extra} to {expected}"
                        )
            elif f"standard=={version}" not in requirements:
                raise ValueError(f"{artifact.name} does not require standard=={version}")
    print(f"Verified 12 release artifacts: all six distributions are {version}")


def _published_files(distribution: str, version: str) -> dict[str, str]:
    """Read the version's current PyPI filenames and SHA-256 hashes; allow only a 404."""
    endpoint = (
        f"https://pypi.org/pypi/{quote(distribution, safe='')}/{quote(version, safe='')}/json"
    )
    request = Request(endpoint, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return {}
        raise
    return {
        item["filename"]: item.get("digests", {}).get("sha256", "")
        for item in payload.get("urls", [])
    }


def stage_for_pypi(
    project_root: Path,
    tag: str,
    artifact_root: Path,
    output_root: Path,
    github_output: Path,
) -> None:
    """Stage only missing, checksum-matching artifacts and expose per-project upload flags."""
    version = verify_source(project_root, tag)
    outputs: list[str] = []
    for distribution in PROJECTS:
        project_dir = artifact_root / distribution
        artifacts = sorted(path for path in project_dir.iterdir() if path.is_file())
        if len(artifacts) != 2:
            raise ValueError(f"{distribution} must have exactly two built files before publishing")
        published = _published_files(distribution, version)
        local = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in artifacts}
        unexpected = sorted(set(published) - set(local))
        if unexpected:
            raise ValueError(
                f"PyPI already contains unexpected {distribution} files for {version}: "
                + ", ".join(unexpected)
            )
        conflicts = sorted(name for name, digest in published.items() if digest != local[name])
        if conflicts:
            raise ValueError(
                f"PyPI has different checksums for {distribution} {version}: "
                + ", ".join(conflicts)
            )

        missing = [path for path in artifacts if path.name not in published]
        staged = output_root / distribution
        if staged.exists():
            shutil.rmtree(staged)
        staged.mkdir(parents=True)
        for artifact in missing:
            shutil.copy2(artifact, staged / artifact.name)
        output_key = f"{distribution.replace('-', '_')}_missing"
        outputs.append(f"{output_key}={'true' if missing else 'false'}")
        print(
            f"{distribution} {version}: {len(published)} verified existing file(s); "
            f"{len(missing)} file(s) to publish"
        )

    with github_output.open("a", encoding="utf-8") as output:
        output.write("\n".join(outputs) + "\n")


def main() -> None:
    """Run release metadata verification, preparation, or PyPI staging."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("verify-source", "prepare"):
        child = commands.add_parser(command)
        child.add_argument("--tag", required=True)
    artifact_command = commands.add_parser("verify-artifacts")
    artifact_command.add_argument("--tag", required=True)
    artifact_command.add_argument("--directory", type=Path, required=True)
    stage_command = commands.add_parser("stage")
    stage_command.add_argument("--tag", required=True)
    stage_command.add_argument("--directory", type=Path, required=True)
    stage_command.add_argument("--output", type=Path, required=True)
    stage_command.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    if args.command == "verify-source":
        verify_source(project_root, args.tag)
    elif args.command == "prepare":
        prepare_release(project_root, args.tag)
    elif args.command == "verify-artifacts":
        verify_artifacts(project_root, args.tag, args.directory)
    else:
        stage_for_pypi(project_root, args.tag, args.directory, args.output, args.github_output)


if __name__ == "__main__":
    main()
