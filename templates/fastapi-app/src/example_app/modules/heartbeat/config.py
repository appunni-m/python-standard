"""Configuration schema owned by the heartbeat module."""

from pydantic import BaseModel, ConfigDict, Field


class HeartbeatSettings(BaseModel):
    """Settings for the optional sample background worker."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    interval_seconds: int = Field(default=30, gt=0)
