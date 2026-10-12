#!/usr/bin/env python3
"""Correctness-gated config load, lookup, merge, reload, and memory benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import timeit
import tracemalloc
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import SettingsConfigDict
from pydantic_settings_sources import YamlEnvSettings

from std.config import ConfigManager, YamlSettings

ROOT = Path(__file__).resolve().parents[1]
SIZES = {"small": 20, "medium": 500, "large": 3000}
INTERPOLATION_VARIABLE = "STD_BENCHMARK_PREFIX"
INTERPOLATION_VALUE = "standard-benchmark"


class BenchmarkSection(BaseModel):
    """Validated typed section used by the settings-load workloads."""

    value: int
    enabled: bool
    labels: list[str]
    limits: dict[str, int]
    endpoint: str


class BenchmarkConfiguration(BaseModel):
    """Plain Pydantic schema for measuring validation without settings sources."""

    sections: dict[str, BenchmarkSection]


def _system_memory_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _cpu_model() -> str | None:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith(("model name", "hardware")):
                return line.partition(":")[2].strip()
    except OSError:
        return platform.processor() or None
    return platform.processor() or None


def _package_version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def _config(size: int, *, resolved: bool = False) -> dict[str, Any]:
    return {
        "sections": {
            f"section_{index:04d}": {
                "value": index,
                "enabled": index % 2 == 0,
                "labels": ["standard", f"item-{index}"],
                "limits": {"soft": index + 10, "hard": index + 100},
                "endpoint": (
                    f"{INTERPOLATION_VALUE}/section-{index:04d}"
                    if resolved
                    else f"${{{INTERPOLATION_VARIABLE}}}/section-{index:04d}"
                ),
            }
            for index in range(size)
        }
    }


@contextmanager
def _benchmark_environment() -> Iterator[None]:
    previous = os.environ.get(INTERPOLATION_VARIABLE)
    os.environ[INTERPOLATION_VARIABLE] = INTERPOLATION_VALUE
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(INTERPOLATION_VARIABLE, None)
        else:
            os.environ[INTERPOLATION_VARIABLE] = previous


def _measure(function: Any, *, repeats: int, number: int) -> dict[str, Any]:
    samples = timeit.repeat(function, repeat=repeats, number=number)
    return _summarize_samples(samples, repeats=repeats, number=number)


def _summarize_samples(samples: list[float], *, repeats: int, number: int) -> dict[str, Any]:
    per_call = [sample / number for sample in samples]
    median = statistics.median(per_call)
    return {
        "repeats": repeats,
        "iterations_per_repeat": number,
        "seconds_per_call_median": median,
        "seconds_per_call_mad": statistics.median(abs(sample - median) for sample in per_call),
        "seconds_per_call_samples": per_call,
    }


def _measure_interleaved(
    first: Any,
    second: Any,
    *,
    repeats: int,
    number: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    samples: tuple[list[float], list[float]] = ([], [])
    for repeat_index in range(repeats):
        order = ((0, first), (1, second)) if repeat_index % 2 == 0 else ((1, second), (0, first))
        for sample_index, function in order:
            started = timeit.default_timer()
            for _ in range(number):
                function()
            samples[sample_index].append(timeit.default_timer() - started)
    return (
        _summarize_samples(samples[0], repeats=repeats, number=number),
        _summarize_samples(samples[1], repeats=repeats, number=number),
    )


def _git_identity() -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return {"revision": revision, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"revision": "unavailable", "dirty": True}


def _source_identity() -> dict[str, Any]:
    """Fingerprint the local code and dependency declarations used by this run."""
    source_paths = [ROOT / "benchmarks" / "configuration.py", ROOT / "pyproject.toml"]
    source_paths.extend(sorted((ROOT / "src" / "std" / "config").rglob("*.py")))

    files: dict[str, str] = {}
    manifest = hashlib.sha256()
    for source_path in source_paths:
        relative_path = source_path.relative_to(ROOT).as_posix()
        file_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        files[relative_path] = file_digest
        manifest.update(relative_path.encode("utf-8"))
        manifest.update(b"\0")
        manifest.update(bytes.fromhex(file_digest))

    return {"manifest_sha256": manifest.hexdigest(), "files_sha256": files}


def _benchmark_size(name: str, size: int, repeats: int) -> dict[str, Any]:
    data = _config(size)
    expected = _config(size, resolved=True)
    yaml_text = yaml.safe_dump(data, sort_keys=True)
    with tempfile.TemporaryDirectory(prefix="standard-benchmark-") as temporary:
        root = Path(temporary)
        file_path = root / "settings.yaml"
        file_path.write_text(yaml_text, encoding="utf-8")

        class TargetSettings(YamlSettings):
            std_config_file = file_path
            sections: dict[str, BenchmarkSection]

        class ReferenceSettings(YamlEnvSettings):
            sections: dict[str, BenchmarkSection]
            model_config = SettingsConfigDict(yaml_file=file_path, env_file=None)

        target = TargetSettings()
        reference = ReferenceSettings()
        if target.model_dump() != reference.model_dump() or target.model_dump() != expected:
            raise RuntimeError(f"parity check failed before timing for {name} configuration")

        target_load, reference_load = _measure_interleaved(
            TargetSettings, ReferenceSettings, repeats=repeats, number=1
        )

        manager = ConfigManager.from_file(file_path)
        if manager.snapshot.to_dict() != expected:
            raise RuntimeError(f"ConfigManager interpolation check failed before timing for {name}")
        interpolation_load = _measure(
            lambda: ConfigManager.from_file(file_path), repeats=repeats, number=1
        )
        validated = BenchmarkConfiguration.model_validate(expected)
        if validated.model_dump() != expected:
            raise RuntimeError(f"Pydantic validation check failed before timing for {name}")
        validation = _measure(
            lambda: BenchmarkConfiguration.model_validate(expected), repeats=repeats, number=1
        )
        lookup = _measure(
            lambda: manager.snapshot.get_path("sections.section_0000.value"),
            repeats=repeats,
            number=10000,
        )
        reload_measure = _measure(manager.reload, repeats=repeats, number=1)

        directory = root / "parts"
        directory.mkdir()
        chunk_size = max(1, (size + 7) // 8)
        for start in range(0, size, chunk_size):
            subset = {
                "sections": {
                    key: value
                    for key, value in data["sections"].items()
                    if start <= int(key.removeprefix("section_")) < start + chunk_size
                }
            }
            (directory / f"part-{start:05d}.yaml").write_text(
                yaml.safe_dump(subset, sort_keys=True), encoding="utf-8"
            )
        directory_digest = hashlib.sha256()
        directory_files = sorted(directory.glob("*.yaml"))
        for directory_file in directory_files:
            directory_digest.update(directory_file.name.encode("utf-8"))
            directory_digest.update(b"\0")
            directory_digest.update(directory_file.read_bytes())
        directory_manager = ConfigManager.from_file(directory)
        expected_directory = {"sections": expected["sections"]}
        if directory_manager.snapshot.to_dict() != expected_directory:
            raise RuntimeError(f"directory merge parity check failed before timing for {name}")
        directory_merge = _measure(
            lambda: ConfigManager.from_file(directory), repeats=repeats, number=1
        )

        tracemalloc.start()
        measured_manager = ConfigManager.from_file(file_path)
        current_bytes, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if measured_manager.snapshot.to_dict() != expected:
            raise RuntimeError(f"memory workload correctness check failed for {name}")

        return {
            "id": name,
            "sections": size,
            "yaml_bytes": len(yaml_text.encode("utf-8")),
            "input_sha256": hashlib.sha256(yaml_text.encode("utf-8")).hexdigest(),
            "directory_files": len(directory_files),
            "directory_input_sha256": directory_digest.hexdigest(),
            "checks": {
                "target_matches_reference": True,
                "target_matches_resolved_input": True,
                "interpolation_matches_expected": True,
                "pydantic_validation_matches_expected": True,
                "directory_merge_matches_input": True,
            },
            "measurement_policy": {
                "repeats": repeats,
                "load_order": "alternating target-reference and reference-target",
                "concurrency": 1,
                "cache_state": "correctness preflight followed by warm OS file cache",
                "settings_load_boundary": "file read through validated Pydantic Settings object",
                "interpolation_boundary": "file read through resolved immutable ConfigSnapshot",
                "validation_boundary": "in-memory mapping through Pydantic BaseModel validation",
            },
            "measurements": {
                "settings_load_target": target_load,
                "settings_load_reference": reference_load,
                "config_manager_interpolation_load": interpolation_load,
                "pydantic_validation_only": validation,
                "warm_lookup_10000": lookup,
                "directory_merge": directory_merge,
                "reload": reload_measure,
                "load_memory": {"current_bytes": current_bytes, "peak_bytes": peak_bytes},
            },
        }


def main() -> int:
    """Run selected configuration workloads and write their raw results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", choices=(*SIZES, "all"), default="all")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    selected = SIZES if args.size == "all" else {args.size: SIZES[args.size]}
    with _benchmark_environment():
        results = [_benchmark_size(name, size, args.repeats) for name, size in selected.items()]
    payload = {
        "schema": "standard/config-benchmark@3",
        "created_at": datetime.now(UTC).isoformat(),
        "command": [sys.executable, *sys.argv],
        "runtime": {
            "python": sys.version,
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "cpu_model": _cpu_model(),
            "cpu_count": os.cpu_count(),
            "memory_bytes": _system_memory_bytes(),
            "power_mode": None,
        },
        "toolchain": {
            "PyYAML": yaml.__version__,
            "pydantic": _package_version("pydantic"),
            "pydantic-settings": _package_version("pydantic-settings"),
            "pydantic-settings-extra-sources": _package_version("pydantic-settings-extra-sources"),
        },
        "target": _git_identity(),
        "source": _source_identity(),
        "oracle": {"name": "pydantic-settings-extra-sources", "version": "0.1.0"},
        "workloads": results,
        "performance_claim": None,
    }
    output = args.output or ROOT / "benchmarks" / "results" / (
        f"configuration-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": str(output), "workloads": len(results), "claim": None}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
