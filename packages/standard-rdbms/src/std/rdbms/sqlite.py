"""Async SQLite managers for persistent files and isolated in-memory databases."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from std.rdbms.config import DatabaseConfig
from std.rdbms.database import Database


def _sqlite_settings(config: DatabaseConfig) -> DatabaseConfig:
    """Copy and validate SQLite settings without mutating the caller's model."""
    settings = config.model_copy(deep=True)
    if not settings.driver.startswith("sqlite+aiosqlite"):
        raise ValueError("SQLite managers require the sqlite+aiosqlite driver")
    settings.connect_args.setdefault("check_same_thread", False)
    return settings


class SQLiteDatabase(Database):
    """Manage a file-backed SQLite database with a fresh connection per checkout."""

    def __init__(self, config: DatabaseConfig) -> None:
        """Create a file-backed database; use ``SQLiteMemDatabase`` for memory."""
        if config.name == ":memory:":
            raise ValueError("Use SQLiteMemDatabase for an in-memory SQLite database")
        super().__init__(_sqlite_settings(config))

    def _create_engine(self) -> AsyncEngine:
        """Create a file-backed engine with ``NullPool`` and configured connect args."""
        return create_async_engine(
            self.settings.url,
            echo=self.settings.echo,
            poolclass=NullPool,
            connect_args=self.settings.connect_args,
        )


class SQLiteMemDatabase(Database):
    """Manage one shared in-memory SQLite database for the lifetime of its engine."""

    def __init__(self, config: DatabaseConfig) -> None:
        """Force this manager's copied settings to use one shared in-memory database."""
        settings = config.model_copy(deep=True)
        if not settings.driver.startswith("sqlite+aiosqlite"):
            raise ValueError("SQLite managers require the sqlite+aiosqlite driver")
        settings.name = ":memory:"
        settings.connect_args.setdefault("check_same_thread", False)
        super().__init__(settings)

    def _create_engine(self) -> AsyncEngine:
        """Create an engine with ``StaticPool`` so sessions see the same memory DB."""
        return create_async_engine(
            self.settings.url,
            echo=self.settings.echo,
            poolclass=StaticPool,
            connect_args=self.settings.connect_args,
        )
