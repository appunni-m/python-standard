"""Aggregate the application's YAML-backed Pydantic settings models."""

from pathlib import Path
from typing import ClassVar

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from std.config import YamlSettings, YamlSettingsSource
from std.logging import LoggingConfig

from example_app.modules.application.config import ApplicationSettings
from example_app.modules.heartbeat.config import HeartbeatSettings


class Settings(YamlSettings):
    """Collect configuration models and load their values from one YAML file."""

    model_config = SettingsConfigDict(extra="forbid")
    std_config_file: ClassVar[Path] = (
        Path(__file__).resolve().parents[3] / "config" / "settings.yaml"
    )

    application: ApplicationSettings
    logging: LoggingConfig
    heartbeat: HeartbeatSettings

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Use YAML as the only Pydantic source; environment flows through placeholders."""
        return (YamlSettingsSource(settings_cls, cls.std_config_file),)
