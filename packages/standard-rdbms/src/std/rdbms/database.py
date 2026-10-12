"""Async SQLAlchemy database lifecycle and transaction management."""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from std.rdbms.config import DatabaseConfig


class Database(ABC):
    """Own an async engine and provide commit-on-success session scopes.

    Each session is intended for one asyncio task at a time. A successful
    ``session()`` scope commits; any exception, including cancellation, rolls
    back and re-raises. The session is closed in either case.
    """

    def __init__(self, settings: DatabaseConfig) -> None:
        """Create the engine and its session factory without opening a connection."""
        self.settings = settings
        self._engine = self._create_engine()
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        self._disposed = False

    @property
    def engine(self) -> AsyncEngine:
        """Return the SQLAlchemy engine for migrations and explicit transactions."""
        return self._engine

    @abstractmethod
    def _create_engine(self) -> AsyncEngine:
        """Create the backend-specific async SQLAlchemy engine."""
        raise NotImplementedError

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session that commits on success and rolls back on failure."""
        if self._disposed:
            raise RuntimeError("Database has been disposed")

        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except BaseException as error:
            try:
                await session.rollback()
            except BaseException as rollback_error:
                error.add_note(
                    "Session rollback also failed: "
                    f"{type(rollback_error).__name__}: {rollback_error}"
                )
            raise
        finally:
            active_error = sys.exception()
            try:
                await session.close()
            except BaseException as close_error:
                if active_error is None:
                    raise
                active_error.add_note(
                    f"Session close also failed: {type(close_error).__name__}: {close_error}"
                )

    async def dispose(self) -> None:
        """Close pooled connections; calling this more than once is safe."""
        if self._disposed:
            return
        await self._engine.dispose()
        self._disposed = True

    async def __aenter__(self) -> Database:
        """Return this database for use as an async resource context manager."""
        if self._disposed:
            raise RuntimeError("Database has been disposed")
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Dispose the engine when leaving an async resource context."""
        await self.dispose()
