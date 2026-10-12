from __future__ import annotations

import os
from collections import UserDict
from pathlib import Path
from types import MappingProxyType

import pytest

from std.collections import deep_merge, get_path, set_path
from std.files import atomic_write_text


def test_deep_merge_is_recursive_and_does_not_mutate_inputs() -> None:
    first = {"nested": {"left": [1]}, "value": {"old": True}}
    second = {"nested": {"right": [2]}, "value": "replaced"}

    merged = deep_merge(first, second)

    assert merged == {"nested": {"left": [1], "right": [2]}, "value": "replaced"}
    merged["nested"]["left"].append(3)
    assert first["nested"]["left"] == [1]


def test_deep_merge_rejects_non_mappings() -> None:
    with pytest.raises(TypeError, match="mappings only"):
        # Deliberately pass an invalid type to verify runtime validation.
        deep_merge({"valid": True}, ["not a mapping"])  # type: ignore[arg-type]


def test_deep_merge_accepts_mapping_implementations_and_no_sources() -> None:
    source = MappingProxyType(UserDict({"nested": MappingProxyType({"items": [1]})}))

    merged = deep_merge(source)
    merged["nested"]["items"].append(2)

    assert deep_merge() == {}
    assert merged == {"nested": {"items": [1, 2]}}
    assert source["nested"]["items"] == [1]


def test_deep_merge_copies_mutable_leaf_values() -> None:
    source_set = {"before"}
    source_buffer = bytearray(b"before")

    merged = deep_merge({"set": source_set, "buffer": source_buffer})
    merged["set"].add("after")
    merged["buffer"].extend(b" after")

    assert source_set == {"before"}
    assert source_buffer == b"before"


def test_deep_merge_rejects_cycles() -> None:
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    with pytest.raises(ValueError, match="cyclic"):
        deep_merge(cyclic)


def test_get_and_set_nested_paths() -> None:
    value: dict[str, object] = {}
    set_path(value, "server.host", "localhost")
    set_path(value, ("server", "port"), 8000)

    assert get_path(value, "server.host") == "localhost"
    assert get_path(value, ("server", "missing"), "fallback") == "fallback"
    assert get_path(value, "server..port") == 8000


def test_paths_support_literal_dots_and_distinguish_missing_from_none() -> None:
    value: dict[str, object] = {"database.host": {"port": None}}
    missing = object()

    assert get_path(value, ("database.host", "port")) is None
    assert get_path(value, ("database.host", "missing"), missing) is missing
    assert get_path(value, "database.host.port", "missing") == "missing"


def test_set_path_rejects_empty_path_and_scalar_parent() -> None:
    with pytest.raises(ValueError, match="at least one"):
        set_path({}, "", 1)
    with pytest.raises(TypeError, match="non-mapping"):
        set_path({"server": "offline"}, "server.port", 8000)
    with pytest.raises(TypeError, match="non-mapping"):
        set_path({"server": None}, "server.port", 8000)


def test_atomic_write_replaces_content_with_owner_only_mode(tmp_path: Path) -> None:
    target = tmp_path / "settings.txt"
    target.write_text("old\n", encoding="utf-8")

    result = atomic_write_text(target, "new\n")

    assert result == target
    assert target.read_text(encoding="utf-8") == "new\n"
    assert os.stat(target).st_mode & 0o777 == 0o600
    assert list(tmp_path.glob(".settings.txt.*.tmp")) == []


def test_atomic_write_can_create_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "settings.txt"

    atomic_write_text(target, "hello", create_parents=True, mode=0o640)

    assert target.read_text(encoding="utf-8") == "hello"
    assert os.stat(target).st_mode & 0o777 == 0o640


def test_atomic_write_requires_existing_parent_by_default(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        atomic_write_text(tmp_path / "missing" / "settings.txt", "hello")


def test_atomic_write_preserves_existing_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "settings.txt"
    target.write_text("original", encoding="utf-8")

    def fail_replace(source: str, destination: str) -> None:
        raise PermissionError("replacement denied")

    monkeypatch.setattr("std.files.os.replace", fail_replace)

    with pytest.raises(PermissionError, match="replacement denied"):
        atomic_write_text(target, "replacement")

    assert target.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.glob(".settings.txt.*.tmp")) == []
