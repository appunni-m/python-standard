"""Application-level settings owned by the application feature."""

from pydantic import BaseModel, Field
from std.logging import LoggingEnvironment


class ApplicationSettings(BaseModel):
    """Validated process and HTTP server settings for the application."""

    name: str = Field(min_length=1)
    environment: LoggingEnvironment = LoggingEnvironment.DEVELOPMENT
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    debug: bool = False
