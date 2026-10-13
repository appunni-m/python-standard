"""Aggregate feature-owned settings and load them from the application's YAML file."""

from pathlib import Path
from typing import ClassVar

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from std.config import YamlSettings, YamlSettingsSource
from std.logging import LoggingConfig

from consumer_app.modules.application.config import ApplicationSettings
from consumer_app.modules.orders.config import OrdersSettings


class Settings(YamlSettings):
    """Top-level settings aggregate populated only by YAML and its placeholders."""

    model_config = SettingsConfigDict(extra="forbid")
    std_config_file: ClassVar[Path] = (
        Path(__file__).resolve().parents[3] / "config" / "settings.yaml"
    )

    application: ApplicationSettings
    logging: LoggingConfig
    orders: OrdersSettings

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Use YAML as the settings source; environment values enter through placeholders."""
        return (YamlSettingsSource(settings_cls, cls.std_config_file),)
