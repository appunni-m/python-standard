"""Validated settings and SQLAlchemy URL construction for relational databases."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.engine import URL


class DatabaseConfig(BaseModel):
    """Connection and pool settings shared by the async database managers.

    The ``url`` property is computed from the current fields. It includes the
    password when one is configured, so treat the returned string as a secret.
    The password is excluded from the model representation and serialization.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    driver: str = Field(default="mysql+aiomysql", description="SQLAlchemy async dialect and driver")
    host: str = Field(default="localhost", description="Database server hostname")
    port: int | None = Field(default=None, ge=1, le=65535, description="Database server port")
    user: str | None = Field(default=None, description="Database username")
    password: str | None = Field(
        default=None,
        repr=False,
        exclude=True,
        description="Database password",
    )
    name: str = Field(default="agent_framework", description="Database name or SQLite path")
    echo: bool = Field(default=False, description="Echo SQL statements for debugging")
    pool_size: int = Field(default=5, ge=0, description="Number of persistent connections")
    max_overflow: int = Field(default=10, ge=-1, description="Connections beyond the pool size")
    pool_timeout: float = Field(default=30.0, ge=0, description="Seconds to wait for a connection")
    pool_recycle: int = Field(
        default=1800, ge=-1, description="Recycle connections after this many seconds"
    )
    connect_args: dict[str, Any] = Field(
        default_factory=dict,
        description="Driver-specific connection arguments",
    )

    @field_validator("driver", "host", "name")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        """Reject empty strings before they become malformed connection URLs."""
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @property
    def url(self) -> str:
        """Return a SQLAlchemy URL string built with proper credential escaping."""
        if self.driver.startswith("sqlite") and self.name == ":memory:":
            return f"{self.driver}:///:memory:"
        return self._sqlalchemy_url().render_as_string(hide_password=False)

    def _sqlalchemy_url(self) -> URL:
        """Build a structured SQLAlchemy URL without hand-escaping credentials."""
        if self.driver.startswith("sqlite"):
            database = self.name
            if database != ":memory:":
                is_absolute = (
                    Path(database).is_absolute() or PureWindowsPath(database).is_absolute()
                )
                if not is_absolute and not database.startswith(("./", ".\\")):
                    database = f"./{database}"
            return URL.create(drivername=self.driver, database=database)

        port = self.port
        if port is None:
            if "mysql" in self.driver:
                port = 3306
            elif "postgres" in self.driver:
                port = 5432
            else:
                # Preserve the original fallback for custom network dialects.
                port = 3306

        return URL.create(
            drivername=self.driver,
            username=self.user or None,
            password=self.password if self.user else None,
            host=self.host,
            port=port,
            database=self.name,
        )
