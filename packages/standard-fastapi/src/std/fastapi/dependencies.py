"""FastAPI dependencies that construct validated Pydantic Settings models."""

from __future__ import annotations

from typing import TypeVar

from pydantic_settings import BaseSettings

from fastapi import HTTPException, Request
from fastapi.params import Depends as DependsType

SettingsT = TypeVar("SettingsT", bound=BaseSettings)


def settings_dependency(settings_type: type[SettingsT]) -> DependsType:
    """Return a dependency that retrieves main-initialized app settings.

    Construct the model once in the application composition root and assign it
    to ``app.state.settings`` before serving requests. The dependency verifies
    its type and returns that same instance; it never constructs settings.
    """
    if not isinstance(settings_type, type) or not issubclass(settings_type, BaseSettings):
        raise TypeError("settings_type must be a BaseSettings subclass")

    async def get_settings(request: Request) -> SettingsT:
        settings = getattr(request.app.state, "settings", None)
        if not isinstance(settings, settings_type):
            raise HTTPException(
                status_code=500,
                detail="Application settings were not initialized in the composition root",
            )
        return settings

    return DependsType(get_settings)


__all__ = ["settings_dependency"]
