"""Optional FastAPI settings dependencies."""

from __future__ import annotations

from typing import TypeVar

try:
    from fastapi.params import Depends as DependsType
except ImportError as error:  # pragma: no cover - depends on installation extra
    raise ImportError(
        "FastAPI integration requires the fastapi extra; "
        "from a checkout run `pip install -e '.[fastapi]'`"
    ) from error

from pydantic_settings import BaseSettings

SettingsT = TypeVar("SettingsT", bound=BaseSettings)


def settings_dependency(settings_type: type[SettingsT]) -> DependsType:
    """Return a FastAPI dependency that constructs the given Settings model.

    A zero-argument factory keeps BaseSettings constructor controls out of the
    route's request parameters.

    FastAPI caches this dependency once per request by default. Override it with
    ``app.dependency_overrides`` in tests or when an application needs a custom
    lifecycle.
    """
    if not isinstance(settings_type, type) or not issubclass(settings_type, BaseSettings):
        raise TypeError("settings_type must be a BaseSettings subclass")

    def create_settings() -> SettingsT:
        return settings_type()

    return DependsType(create_settings)


__all__ = ["settings_dependency"]
