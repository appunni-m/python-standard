"""Async PostgreSQL database manager using SQLAlchemy's async dialect."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from std.rdbms.config import DatabaseConfig
from std.rdbms.database import Database


class PostgresDatabase(Database):
    """Manage PostgreSQL connections with health checks and configured pooling."""

    def __init__(self, config: DatabaseConfig) -> None:
        """Copy settings and provide a recognizable PostgreSQL application name."""
        settings = config.model_copy(deep=True)
        if not settings.driver.startswith(("postgresql+", "postgres+")):
            raise ValueError("PostgresDatabase requires a PostgreSQL async driver")
        settings.connect_args.setdefault("server_settings", {"application_name": "standard-rdbms"})
        super().__init__(settings)

    def _create_engine(self) -> AsyncEngine:
        """Create a pooled PostgreSQL engine with pre-ping enabled."""
        return create_async_engine(
            self.settings.url,
            echo=self.settings.echo,
            pool_size=self.settings.pool_size,
            max_overflow=self.settings.max_overflow,
            pool_timeout=self.settings.pool_timeout,
            pool_recycle=self.settings.pool_recycle,
            pool_pre_ping=True,
            connect_args=self.settings.connect_args,
        )
