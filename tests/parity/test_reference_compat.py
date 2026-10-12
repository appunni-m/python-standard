from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_settings import SettingsConfigDict
from pydantic_settings_sources import TomlEnvSettings, YamlEnvSettings
from pydantic_settings_sources.errors import MissingEnvVarError

from std.config import ConfigInterpolationError, TomlSettings, YamlSettings


@pytest.mark.parametrize(
    ("suffix", "contents"),
    [
        (
            ".yaml",
            """service:
  name: catalog
  ports: [8000, 8001]
enabled: true
retries: ${STD_PARITY_RETRIES:-3}
settings: ${STD_PARITY_SETTINGS}
endpoint: ${STD_PARITY_ALIAS}
""",
        ),
        (
            ".toml",
            """enabled = true
retries = "${STD_PARITY_RETRIES:-3}"
settings = "${STD_PARITY_SETTINGS}"
endpoint = "${STD_PARITY_ALIAS}"

[service]
name = "catalog"
ports = [8000, 8001]
""",
        ),
    ],
)
def test_typed_values_and_interpolation_match_live_reference_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suffix: str,
    contents: str,
) -> None:
    path = tmp_path / f"settings{suffix}"
    path.write_text(contents, encoding="utf-8")
    monkeypatch.setenv("STD_PARITY_ALIAS", "${STD_PARITY_ENDPOINT}")
    monkeypatch.setenv("STD_PARITY_ENDPOINT", "catalog.internal")
    monkeypatch.setenv("STD_PARITY_SETTINGS", '{"mode":"safe","levels":[1,2]}')
    for field in ("SERVICE", "ENABLED", "RETRIES", "SETTINGS", "ENDPOINT"):
        monkeypatch.delenv(field, raising=False)

    if suffix == ".yaml":

        class Reference(YamlEnvSettings):
            service: dict[str, object]
            enabled: bool
            retries: int
            settings: dict[str, object]
            endpoint: str

            model_config = SettingsConfigDict(yaml_file=path, env_file=None)

        class Target(YamlSettings):
            service: dict[str, object]
            enabled: bool
            retries: int
            settings: dict[str, object]
            endpoint: str

            std_config_file = path

    else:

        class Reference(TomlEnvSettings):
            service: dict[str, object]
            enabled: bool
            retries: int
            settings: dict[str, object]
            endpoint: str

            model_config = SettingsConfigDict(toml_file=path, env_file=None)

        class Target(TomlSettings):
            service: dict[str, object]
            enabled: bool
            retries: int
            settings: dict[str, object]
            endpoint: str

            std_config_file = path

    expected = {
        "service": {"name": "catalog", "ports": [8000, 8001]},
        "enabled": True,
        "retries": 3,
        "settings": {"mode": "safe", "levels": [1, 2]},
        "endpoint": "catalog.internal",
    }
    assert Reference().model_dump() == expected
    assert Target().model_dump() == expected


def test_yaml_source_priority_and_directory_merge_match_live_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text("port: 8000\n", encoding="utf-8")

    class ReferenceSettings(YamlEnvSettings):
        port: int

        model_config = SettingsConfigDict(yaml_file=settings_path, env_file=None)

    class TargetSettings(YamlSettings):
        port: int

        std_config_file = settings_path

    monkeypatch.setenv("PORT", "9000")
    assert ReferenceSettings().port == TargetSettings().port == 8000
    assert ReferenceSettings(port=7000).port == TargetSettings(port=7000).port == 7000

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "01-base.yaml").write_text(
        "service:\n  name: base\n  retries: 2\n  tags: [base]\nitems: [first]\n",
        encoding="utf-8",
    )
    (config_dir / "02-override.yaml").write_text(
        "service:\n  name: override\n  timeout: 5\n  tags: [override]\nitems: [second]\n",
        encoding="utf-8",
    )

    class ReferenceDirectory(YamlEnvSettings):
        service: dict[str, object]
        items: list[str]

        model_config = SettingsConfigDict(yaml_file=config_dir, env_file=None)

    class TargetDirectory(YamlSettings):
        service: dict[str, object]
        items: list[str]

        std_config_file = config_dir

    expected = {
        "service": {
            "name": "override",
            "retries": 2,
            "timeout": 5,
            "tags": ["base", "override"],
        },
        "items": ["first", "second"],
    }
    assert ReferenceDirectory().model_dump() == expected
    assert TargetDirectory().model_dump() == expected


def test_missing_interpolation_fails_in_reference_and_target_without_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text("token: ${STD_PARITY_REQUIRED_TOKEN}\n", encoding="utf-8")
    monkeypatch.delenv("STD_PARITY_REQUIRED_TOKEN", raising=False)

    class Reference(YamlEnvSettings):
        token: str

        model_config = SettingsConfigDict(yaml_file=path, env_file=None)

    class Target(YamlSettings):
        token: str

        std_config_file = path

    with pytest.raises(MissingEnvVarError) as reference_error:
        Reference()
    with pytest.raises(ConfigInterpolationError) as target_error:
        Target()
    assert "STD_PARITY_REQUIRED_TOKEN" in str(reference_error.value)
    assert "STD_PARITY_REQUIRED_TOKEN" in str(target_error.value)
