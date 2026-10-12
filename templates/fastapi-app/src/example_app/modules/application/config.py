"""Application identity and runtime-environment settings."""

from pydantic import BaseModel, ConfigDict
from std.logging import LoggingEnvironment


class ApplicationSettings(BaseModel):
    """Settings that identify this application instance."""

    model_config = ConfigDict(extra="forbid")

    name: str
    environment: LoggingEnvironment = LoggingEnvironment.DEVELOPMENT
