"""HTTP request and response schemas owned by the health module."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Public response shape for the process health endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"]
    application: str
