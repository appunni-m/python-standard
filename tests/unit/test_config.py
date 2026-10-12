from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import Field

from std.config import (
    ConfigFormatError,
    ConfigInterpolationError,
    ConfigManager,
    MissingConfigSourceError,
    TomlSettings,
    TomlSettingsSource,
    YamlSettings,
    YamlSettingsSource,
)


def test_load_yaml_and_toml(tmp_path: Path) -> None:
    yaml_file = tmp_path / "config.yaml"
    toml_file = tmp_path / "config.toml"
    yaml_file.write_text("server:\n  host: localhost\n  ports: [8000, 8001]\n", encoding="utf-8")
    toml_file.write_text('[server]\nname = "api"\n', encoding="utf-8")

    snapshot = ConfigManager.from_files(yaml_file, toml_file).snapshot

    assert snapshot.to_dict() == {
        "server": {"host": "localhost", "ports": [8000, 8001], "name": "api"}
    }


def test_directory_files_are_sorted_by_relative_posix_path(tmp_path: Path) -> None:
    root = tmp_path / "config"
    (root / "z").mkdir(parents=True)
    (root / "a").mkdir()
    (root / "z" / "settings.yaml").write_text("value: later\nitems: [z]\n", encoding="utf-8")
    (root / "a" / "settings.yaml").write_text("value: first\nitems: [a]\n", encoding="utf-8")

    snapshot = ConfigManager.from_file(root).snapshot

    assert snapshot["value"] == "later"
    assert snapshot["items"] == ("a", "z")
    assert snapshot.sources == (
        str(root / "a" / "settings.yaml"),
        str(root / "z" / "settings.yaml"),
    )


def test_merge_rules_replace_conflicting_types(tmp_path: Path) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    first.write_text(
        "nested:\n  value: 1\nitems: [one]\nreplace: {child: true}\n", encoding="utf-8"
    )
    second.write_text("nested:\n  next: 2\nitems: [two]\nreplace: scalar\n", encoding="utf-8")

    assert ConfigManager.from_files(first, second).snapshot.to_dict() == {
        "nested": {"value": 1, "next": 2},
        "items": ["one", "two"],
        "replace": "scalar",
    }


def test_missing_source_optional_source_and_empty_directory(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    with pytest.raises(MissingConfigSourceError):
        ConfigManager.from_file(missing)
    assert ConfigManager.from_file(missing, optional=True).snapshot.to_dict() == {}
    empty = tmp_path / "empty"
    empty.mkdir()
    assert ConfigManager.from_file(empty).snapshot.to_dict() == {}


@pytest.mark.parametrize("contents", ["", "# comment only\n", "---\n# no document\n"])
def test_empty_yaml_is_an_empty_mapping(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text(contents, encoding="utf-8")
    assert ConfigManager.from_file(path).snapshot.to_dict() == {}


@pytest.mark.parametrize("contents", ["null\n", "[]\n", "scalar\n"])
def test_yaml_non_mapping_root_is_rejected(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ConfigFormatError, match="root must be a mapping"):
        ConfigManager.from_file(path)


def test_yaml_syntax_and_nested_key_errors_are_source_aware(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("value: [\n", encoding="utf-8")
    with pytest.raises(ConfigFormatError) as syntax_error:
        ConfigManager.from_file(invalid)
    assert str(invalid) in str(syntax_error.value)
    assert "line 2" in str(syntax_error.value)

    invalid.write_text("outer:\n  ? 4\n  : value\n", encoding="utf-8")
    with pytest.raises(ConfigFormatError, match="keys must be strings"):
        ConfigManager.from_file(invalid)


def test_yaml_unhashable_mapping_keys_are_reported_as_key_errors(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("outer:\n  ? [one, two]\n  : value\n", encoding="utf-8")

    with pytest.raises(ConfigFormatError, match="keys must be strings") as error:
        ConfigManager.from_file(invalid)

    assert str(invalid) in str(error.value)
    assert "line 2" in str(error.value)


def test_directory_scan_errors_are_source_aware(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "settings"
    root.mkdir()
    original_rglob = Path.rglob

    def fail_scan(path: Path, pattern: str):
        if path == root:
            raise PermissionError("private directory detail")
        return original_rglob(path, pattern)

    monkeypatch.setattr(Path, "rglob", fail_scan)

    with pytest.raises(
        ConfigFormatError, match="could not inspect configuration directory"
    ) as error:
        ConfigManager.from_file(root)

    assert str(root) in str(error.value)
    assert "private directory detail" not in str(error.value)


def test_toml_parse_error_is_source_aware(tmp_path: Path) -> None:
    path = tmp_path / "invalid.toml"
    path.write_text("bad = [\n", encoding="utf-8")
    with pytest.raises(ConfigFormatError, match="invalid TOML syntax") as error:
        ConfigManager.from_file(path)
    assert str(path) in str(error.value)


def test_unsupported_extension_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigFormatError, match="supported file extensions"):
        ConfigManager.from_file(path)


def test_interpolates_recursive_nested_values_and_json_types(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """plain: "false"
typed: ${TYPED}
mixed: "prefix-${TEXT}"
price: "$5"
list:
  - ${NESTED}
  - "$$HOME"
""",
        encoding="utf-8",
    )
    snapshot = ConfigManager.from_file(
        path,
        environ={
            "TYPED": '{"enabled": true, "ports": [80, 443]}',
            "TEXT": "value",
            "NESTED": "${VALUE}",
            "VALUE": "42",
        },
    ).snapshot

    assert snapshot.to_dict() == {
        "plain": "false",
        "typed": {"enabled": True, "ports": [80, 443]},
        "mixed": "prefix-value",
        "price": "$5",
        "list": [42, "$HOME"],
    }


def test_empty_environment_value_wins_and_empty_default_is_allowed(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("empty: ${EMPTY:-fallback}\ndefault: ${UNSET:-}\n", encoding="utf-8")
    snapshot = ConfigManager.from_file(path, environ={"EMPTY": ""}).snapshot
    assert snapshot.to_dict() == {"empty": "", "default": ""}


def test_interpolation_cycles_missing_names_and_malformed_placeholders_fail_safely(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("value: ${SECRET}\n", encoding="utf-8")
    with pytest.raises(ConfigInterpolationError, match="not set"):
        ConfigManager.from_file(path, environ={})

    with pytest.raises(ConfigInterpolationError, match="cycle") as cycle:
        ConfigManager.from_file(path, environ={"SECRET": "${NEXT}", "NEXT": "${SECRET}"})
    assert "${SECRET}" not in str(cycle.value)

    path.write_text("value: ${bad-name}\n", encoding="utf-8")
    with pytest.raises(ConfigInterpolationError, match="invalid environment variable name"):
        ConfigManager.from_file(path, environ={})

    path.write_text("value: ${UNFINISHED\n", encoding="utf-8")
    with pytest.raises(ConfigInterpolationError, match="malformed"):
        ConfigManager.from_file(path, environ={})


def test_interpolation_errors_keep_nested_mapping_and_list_locations(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("services:\n  - token: ${MISSING_TOKEN}\n", encoding="utf-8")
    with pytest.raises(ConfigInterpolationError) as error:
        ConfigManager.from_file(path, environ={})
    assert f"{path}:$.services[0].token" in str(error.value)


def test_yaml_alias_cycles_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "cycle.yaml"
    path.write_text("value: &cycle [*cycle]\n", encoding="utf-8")
    with pytest.raises(ConfigFormatError, match="cyclic YAML aliases"):
        ConfigManager.from_file(path)


def test_yaml_anchors_without_cycles_load_normally(tmp_path: Path) -> None:
    path = tmp_path / "anchors.yaml"
    path.write_text("defaults: &defaults\n  port: 8000\ncopy: *defaults\n", encoding="utf-8")
    assert ConfigManager.from_file(path).snapshot.to_dict() == {
        "defaults": {"port": 8000},
        "copy": {"port": 8000},
    }


def test_yaml_anchor_interpolation_resolves_all_aliases(tmp_path: Path) -> None:
    path = tmp_path / "anchors.yaml"
    path.write_text("defaults: &defaults\n  host: ${HOST}\ncopy: *defaults\n", encoding="utf-8")
    assert ConfigManager.from_file(path, environ={"HOST": "internal"}).snapshot.to_dict() == {
        "defaults": {"host": "internal"},
        "copy": {"host": "internal"},
    }


def test_errors_do_not_include_environment_values(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("token: ${PRIVATE_TOKEN}\n", encoding="utf-8")
    with pytest.raises(ConfigInterpolationError) as error:
        ConfigManager.from_file(path, environ={})
    assert "top-secret" not in str(error.value)


def test_snapshot_is_immutable_and_to_dict_is_independent(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("nested:\n  items: [one]\n", encoding="utf-8")
    snapshot = ConfigManager.from_file(path).snapshot
    copy = snapshot.to_dict()
    copy["nested"]["items"].append("two")

    assert snapshot.get_path("nested.items") == ("one",)
    assert snapshot["nested"]["items"] == ("one",)
    # Deliberately bypass static types to verify runtime immutability failures.
    with pytest.raises(TypeError):
        snapshot["nested"]["new"] = True  # type: ignore[index]
    with pytest.raises(AttributeError, match="immutable"):
        snapshot.revision = 3  # type: ignore[misc]


def test_snapshot_constructor_copies_and_freezes_caller_data() -> None:
    from std.config import ConfigSnapshot

    values: dict[str, object] = {
        "nested": [{"value": 1}],
        "choices": {"safe", "fast"},
    }
    snapshot = ConfigSnapshot(values)
    nested = values["nested"]
    choices = values["choices"]
    assert isinstance(nested, list)
    assert isinstance(choices, set)
    nested[0]["value"] = 2
    nested.append({"value": 3})
    choices.add("mutable")

    assert snapshot.to_dict() == {"nested": [{"value": 1}], "choices": {"safe", "fast"}}
    assert snapshot["choices"] == frozenset({"safe", "fast"})


def test_yaml_set_values_are_frozen_and_thawed(tmp_path: Path) -> None:
    path = tmp_path / "set.yaml"
    path.write_text("members: !!set {alpha: null, beta: null}\n", encoding="utf-8")

    snapshot = ConfigManager.from_file(path).snapshot

    assert snapshot["members"] == frozenset({"alpha", "beta"})
    assert snapshot.to_dict() == {"members": {"alpha", "beta"}}


def test_snapshot_constructor_rejects_cyclic_data() -> None:
    from std.config import ConfigSnapshot

    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    with pytest.raises(ValueError, match="cyclic"):
        ConfigSnapshot(cyclic)


def test_reload_publishes_new_revision_and_failure_keeps_old_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("value: one\n", encoding="utf-8")
    manager = ConfigManager.from_file(path)
    previous = manager.snapshot
    path.write_text("value: two\n", encoding="utf-8")
    current = manager.reload()

    assert current.revision == 2
    assert current["value"] == "two"
    assert previous["value"] == "one"

    path.write_text("value: ${MISSING}\n", encoding="utf-8")
    with pytest.raises(ConfigInterpolationError):
        manager.reload(environ={})
    assert manager.snapshot is current


def test_yaml_settings_source_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text("value: from-file\ncount: 1\n", encoding="utf-8")
    monkeypatch.setenv("VALUE", "from-env")

    class Settings(YamlSettings):
        value: str
        count: int
        std_config_file = path

    settings = Settings(value="from-init")
    assert settings.value == "from-init"
    assert settings.count == 1
    assert Settings().value == "from-file"


def test_toml_settings_source_reads_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text('name = "api"\nport = 8000\n', encoding="utf-8")

    class Settings(TomlSettings):
        name: str
        port: int = Field(gt=0)
        std_config_file = path

    settings = Settings()
    assert (settings.name, settings.port) == ("api", 8000)


def test_yaml_settings_source_accepts_directory_and_filters_toml(tmp_path: Path) -> None:
    directory = tmp_path / "settings"
    directory.mkdir()
    (directory / "a.yaml").write_text("name: yaml\n", encoding="utf-8")
    (directory / "b.toml").write_text("port = 9000\n", encoding="utf-8")

    class Settings(YamlSettings):
        name: str
        port: int | None = None
        std_config_file = directory

    settings = Settings()
    assert settings.name == "yaml"
    assert settings.port is None
    assert YamlSettingsSource(Settings, directory)() == {"name": "yaml"}


def test_yaml_settings_source_accepts_dot_named_directory(tmp_path: Path) -> None:
    directory = tmp_path / "settings.v1"
    directory.mkdir()
    (directory / "settings.yaml").write_text("name: yaml\n", encoding="utf-8")

    class Settings(YamlSettings):
        name: str
        std_config_file = directory

    assert Settings().name == "yaml"
    assert YamlSettingsSource(Settings, directory)() == {"name": "yaml"}


def test_toml_settings_source_accepts_dot_named_directory(tmp_path: Path) -> None:
    directory = tmp_path / "settings.v1"
    directory.mkdir()
    (directory / "settings.toml").write_text('name = "toml"\n', encoding="utf-8")

    class Settings(TomlSettings):
        name: str
        std_config_file = directory

    assert Settings().name == "toml"
    assert TomlSettingsSource(Settings, directory)() == {"name": "toml"}


def test_optional_settings_source_accepts_missing_dot_named_directory(tmp_path: Path) -> None:
    missing = tmp_path / "settings.v1"

    assert YamlSettingsSource(YamlSettings, missing, optional=True)() == {}
    assert TomlSettingsSource(TomlSettings, missing, optional=True)() == {}
    with pytest.raises(MissingConfigSourceError):
        YamlSettingsSource(YamlSettings, missing)()


def test_custom_pydantic_source_order_remains_supported(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text("value: from-file\n", encoding="utf-8")

    class Settings(YamlSettings):
        value: str
        std_config_file = path

        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls,
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        ):
            return (init_settings, env_settings, YamlSettingsSource(settings_cls, path))

    from std.config import YamlSettingsSource

    assert Settings(value="init").value == "init"
