"""Unit and SQLite integration coverage for the std.rdbms public API."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import Integer, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool, StaticPool

from std.rdbms import (
    DatabaseConfig,
    MySQLDatabase,
    PostgresDatabase,
    SQLiteDatabase,
    SQLiteMemDatabase,
    ensure_utc,
)


class _ModelBase(DeclarativeBase):
    """Base metadata for SQLite behavior tests."""


class _Record(_ModelBase):
    """Simple persisted row for transaction and SQLite checks."""

    __tablename__ = "std_rdbms_test_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[str] = mapped_column(String(100), unique=True)


class _DateHolder:
    """Object that exposes an optionally naive datetime property."""

    def __init__(self, value: datetime | None) -> None:
        self._value = value

    @ensure_utc
    def value(self) -> datetime | None:
        return self._value

    @value.setter
    def value(self, value: datetime | None) -> None:
        self._value = value


class _TrackingSession:
    """Minimal session spy for cleanup behavior independent of database errors."""

    def __init__(
        self,
        *,
        commit_error: BaseException | None = None,
        rollback_error: BaseException | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        self.events: list[str] = []
        self.commit_error = commit_error
        self.rollback_error = rollback_error
        self.close_error = close_error

    async def commit(self) -> None:
        self.events.append("commit")
        if self.commit_error is not None:
            raise self.commit_error

    async def rollback(self) -> None:
        self.events.append("rollback")
        if self.rollback_error is not None:
            raise self.rollback_error

    async def close(self) -> None:
        self.events.append("close")
        if self.close_error is not None:
            raise self.close_error


def test_config_defaults_and_computed_url() -> None:
    config = DatabaseConfig()

    assert config.driver == "mysql+aiomysql"
    assert config.host == "localhost"
    assert config.port is None
    assert config.user is None
    assert config.password is None
    assert config.name == "agent_framework"
    assert config.echo is False
    assert config.pool_size == 5
    assert config.max_overflow == 10
    assert config.pool_timeout == 30.0
    assert config.pool_recycle == 1800
    assert config.connect_args == {}
    assert config.url == "mysql+aiomysql://localhost:3306/agent_framework"


@pytest.mark.parametrize(
    ("driver", "port", "expected"),
    [
        ("mysql+aiomysql", None, 3306),
        ("mysql+aiomysql", 3307, 3307),
        ("postgresql+asyncpg", None, 5432),
        ("postgresql+asyncpg", 5433, 5433),
        ("postgresql+psycopg", None, 5432),
        ("custom+async", None, 3306),
    ],
)
def test_network_url_default_and_explicit_ports(
    driver: str, port: int | None, expected: int
) -> None:
    config = DatabaseConfig(
        driver=driver,
        host="db.internal",
        port=port,
        user="service",
        password="secret",
        name="app",
    )

    assert config.url == f"{driver}://service:secret@db.internal:{expected}/app"


def test_url_escapes_credentials_and_ipv6_host() -> None:
    config = DatabaseConfig(
        driver="postgresql+asyncpg",
        host="2001:db8::1",
        user="api@service",
        password="p@ss:/word%",
        name="app db",
    )

    assert config.url == (
        "postgresql+asyncpg://api%40service:p%40ss%3A%2Fword%25@[2001:db8::1]:5432/app db"
    )


def test_url_supports_username_without_password_and_no_user() -> None:
    assert (
        DatabaseConfig(driver="mysql+aiomysql", user="root", password=None, name="app").url
        == "mysql+aiomysql://root@localhost:3306/app"
    )
    assert (
        DatabaseConfig(driver="mysql+aiomysql", user=None, password="ignored", name="app").url
        == "mysql+aiomysql://localhost:3306/app"
    )


def test_sqlite_urls_cover_memory_relative_and_absolute_paths(tmp_path: Path) -> None:
    assert DatabaseConfig(driver="sqlite+aiosqlite", name=":memory:").url == (
        "sqlite+aiosqlite:///:memory:"
    )
    assert DatabaseConfig(driver="sqlite+aiosqlite", name="data/app.db").url == (
        "sqlite+aiosqlite:///./data/app.db"
    )
    absolute = tmp_path / "app database.sqlite"
    assert DatabaseConfig(driver="sqlite+aiosqlite", name=str(absolute)).url == (
        f"sqlite+aiosqlite:///{absolute}"
    )


def test_config_url_tracks_assignment_and_hides_password_from_repr_and_dump() -> None:
    config = DatabaseConfig(user="app", password="very-secret", name="first")
    first_url = config.url
    config.name = "second"

    assert "first" in first_url
    assert "second" in config.url
    assert "very-secret" not in repr(config)
    assert "very-secret" not in str(config.model_dump())
    assert "password" not in config.model_dump()
    assert "url" not in config.model_dump()


def test_config_copies_default_connect_args_per_instance() -> None:
    first = DatabaseConfig()
    second = DatabaseConfig()

    first.connect_args["timeout"] = 7

    assert second.connect_args == {}


@pytest.mark.parametrize(
    "values",
    [
        {"driver": ""},
        {"host": "  "},
        {"name": ""},
        {"port": 0},
        {"port": 65536},
        {"pool_size": -1},
        {"max_overflow": -2},
        {"pool_timeout": -0.1},
        {"pool_recycle": -2},
        {"unknown_field": True},
    ],
)
def test_config_rejects_invalid_values(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DatabaseConfig(**values)


def test_sqlite_file_engine_uses_null_pool_and_copied_defaults(tmp_path: Path) -> None:
    config = DatabaseConfig(driver="sqlite+aiosqlite", name=str(tmp_path / "data.db"))
    database = SQLiteDatabase(config)

    assert isinstance(database.engine.pool, NullPool)
    assert database.settings.connect_args == {"check_same_thread": False}
    assert config.connect_args == {}
    asyncio.run(database.dispose())


def test_sqlite_file_engine_preserves_explicit_connect_args(tmp_path: Path) -> None:
    config = DatabaseConfig(
        driver="sqlite+aiosqlite",
        name=str(tmp_path / "data.db"),
        connect_args={"check_same_thread": True, "timeout": 4},
    )
    database = SQLiteDatabase(config)

    assert database.settings.connect_args == {"check_same_thread": True, "timeout": 4}
    assert config.connect_args == {"check_same_thread": True, "timeout": 4}
    asyncio.run(database.dispose())


def test_sqlite_file_manager_rejects_memory_database() -> None:
    with pytest.raises(ValueError, match="SQLiteMemDatabase"):
        SQLiteDatabase(DatabaseConfig(driver="sqlite+aiosqlite", name=":memory:"))


def test_sqlite_memory_manager_forces_private_memory_settings() -> None:
    config = DatabaseConfig(driver="sqlite+aiosqlite", name="file.db")
    database = SQLiteMemDatabase(config)

    assert isinstance(database.engine.pool, StaticPool)
    assert database.settings.name == ":memory:"
    assert database.settings.connect_args == {"check_same_thread": False}
    assert config.name == "file.db"
    assert config.connect_args == {}
    asyncio.run(database.dispose())


def test_sqlite_managers_reject_non_sqlite_drivers() -> None:
    config = DatabaseConfig(driver="postgresql+asyncpg")

    with pytest.raises(ValueError, match=r"sqlite\+aiosqlite"):
        SQLiteDatabase(config)
    with pytest.raises(ValueError, match=r"sqlite\+aiosqlite"):
        SQLiteMemDatabase(config)


@pytest.mark.parametrize(
    ("manager_type", "driver"),
    [
        (PostgresDatabase, "postgresql+asyncpg"),
        (MySQLDatabase, "mysql+aiomysql"),
    ],
)
def test_network_engines_apply_pool_and_backend_defaults(
    manager_type: type[PostgresDatabase] | type[MySQLDatabase], driver: str
) -> None:
    config = DatabaseConfig(
        driver=driver,
        pool_size=3,
        max_overflow=4,
        pool_timeout=12.0,
        pool_recycle=900,
        connect_args={"custom": "preserved"},
    )
    database = manager_type(config)
    pool = database.engine.sync_engine.pool

    assert pool.size() == 3
    assert pool._max_overflow == 4
    assert pool._timeout == 12.0
    assert pool._recycle == 900
    assert pool._pre_ping is True
    assert database.settings.connect_args["custom"] == "preserved"
    if manager_type is PostgresDatabase:
        assert database.settings.connect_args["server_settings"] == {
            "application_name": "standard-rdbms"
        }
    else:
        assert database.settings.connect_args["charset"] == "utf8mb4"
        assert database.settings.connect_args["autocommit"] is False
    assert config.connect_args == {"custom": "preserved"}
    asyncio.run(database.dispose())


def test_backend_defaults_do_not_override_explicit_connection_args() -> None:
    postgres = PostgresDatabase(
        DatabaseConfig(
            driver="postgresql+asyncpg",
            connect_args={"server_settings": {"application_name": "custom"}},
        )
    )
    mysql = MySQLDatabase(
        DatabaseConfig(
            driver="mysql+aiomysql",
            connect_args={"charset": "latin1", "autocommit": True},
        )
    )

    assert postgres.settings.connect_args["server_settings"] == {"application_name": "custom"}
    assert mysql.settings.connect_args == {"charset": "latin1", "autocommit": True}
    asyncio.run(postgres.dispose())
    asyncio.run(mysql.dispose())


def test_backend_managers_reject_the_wrong_database_family() -> None:
    config = DatabaseConfig(driver="sqlite+aiosqlite")

    with pytest.raises(ValueError, match="PostgreSQL"):
        PostgresDatabase(config)
    with pytest.raises(ValueError, match="MySQL"):
        MySQLDatabase(config)


def test_session_commits_and_closes_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    database = SQLiteMemDatabase(DatabaseConfig(driver="sqlite+aiosqlite"))
    tracker = _TrackingSession()
    monkeypatch.setattr(database, "_session_factory", lambda: tracker)

    async def scenario() -> None:
        async with database.session() as session:
            assert session is tracker
        await database.dispose()

    asyncio.run(scenario())

    assert tracker.events == ["commit", "close"]


def test_session_rolls_back_and_closes_on_base_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = SQLiteMemDatabase(DatabaseConfig(driver="sqlite+aiosqlite"))
    tracker = _TrackingSession()
    monkeypatch.setattr(database, "_session_factory", lambda: tracker)

    async def scenario() -> None:
        with pytest.raises(asyncio.CancelledError):
            async with database.session():
                raise asyncio.CancelledError
        await database.dispose()

    asyncio.run(scenario())

    assert tracker.events == ["rollback", "close"]


def test_commit_failure_rolls_back_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    database = SQLiteMemDatabase(DatabaseConfig(driver="sqlite+aiosqlite"))
    tracker = _TrackingSession(commit_error=RuntimeError("commit failed"))
    monkeypatch.setattr(database, "_session_factory", lambda: tracker)

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="commit failed"):
            async with database.session():
                pass
        await database.dispose()

    asyncio.run(scenario())

    assert tracker.events == ["commit", "rollback", "close"]


def test_rollback_and_close_failures_are_attached_to_original_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = SQLiteMemDatabase(DatabaseConfig(driver="sqlite+aiosqlite"))
    tracker = _TrackingSession(
        rollback_error=RuntimeError("rollback failed"),
        close_error=RuntimeError("close failed"),
    )
    monkeypatch.setattr(database, "_session_factory", lambda: tracker)

    async def scenario() -> None:
        with pytest.raises(ValueError, match="work failed") as raised:
            async with database.session():
                raise ValueError("work failed")
        await database.dispose()
        return raised.value

    raised = asyncio.run(scenario())

    assert tracker.events == ["rollback", "close"]
    assert any("rollback failed" in note for note in raised.__notes__)
    assert any("close failed" in note for note in raised.__notes__)


def test_close_failure_after_success_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    database = SQLiteMemDatabase(DatabaseConfig(driver="sqlite+aiosqlite"))
    tracker = _TrackingSession(close_error=RuntimeError("close failed"))
    monkeypatch.setattr(database, "_session_factory", lambda: tracker)

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="close failed"):
            async with database.session():
                pass
        await database.dispose()

    asyncio.run(scenario())

    assert tracker.events == ["commit", "close"]


def test_dispose_is_idempotent_and_rejects_new_sessions() -> None:
    database = SQLiteMemDatabase(DatabaseConfig(driver="sqlite+aiosqlite"))

    async def scenario() -> None:
        await database.dispose()
        await database.dispose()
        with pytest.raises(RuntimeError, match="disposed"):
            async with database.session():
                pass

    asyncio.run(scenario())


def test_async_context_manager_disposes_engine() -> None:
    database = SQLiteMemDatabase(DatabaseConfig(driver="sqlite+aiosqlite"))

    async def scenario() -> None:
        async with database as managed:
            assert managed is database
        with pytest.raises(RuntimeError, match="disposed"):
            async with database:
                pass

    asyncio.run(scenario())


def test_memory_sqlite_shares_data_and_rolls_back_failed_work() -> None:
    database = SQLiteMemDatabase(DatabaseConfig(driver="sqlite+aiosqlite"))

    async def scenario() -> None:
        async with database.engine.begin() as connection:
            await connection.run_sync(_ModelBase.metadata.create_all)

        async with database.session() as session:
            session.add(_Record(value="committed"))

        with pytest.raises(RuntimeError, match="force rollback"):
            async with database.session() as session:
                session.add(_Record(value="rolled back"))
                raise RuntimeError("force rollback")

        async with database.session() as session:
            values = (await session.scalars(select(_Record.value))).all()
            assert values == ["committed"]
        await database.dispose()

    asyncio.run(scenario())


def test_memory_sqlite_disposal_discards_database() -> None:
    config = DatabaseConfig(driver="sqlite+aiosqlite", name=":memory:")
    first = SQLiteMemDatabase(config)

    async def write_and_dispose() -> None:
        async with first.engine.begin() as connection:
            await connection.run_sync(_ModelBase.metadata.create_all)
        async with first.session() as session:
            session.add(_Record(value="temporary"))
        await first.dispose()

    asyncio.run(write_and_dispose())
    second = SQLiteMemDatabase(config)

    async def verify_empty() -> None:
        async with second.engine.begin() as connection:
            await connection.run_sync(_ModelBase.metadata.create_all)
        async with second.session() as session:
            assert (await session.scalars(select(_Record))).all() == []
        await second.dispose()

    asyncio.run(verify_empty())


def test_file_sqlite_persists_data_between_engine_instances(tmp_path: Path) -> None:
    config = DatabaseConfig(
        driver="sqlite+aiosqlite",
        name=str(tmp_path / "file database.sqlite"),
    )
    first = SQLiteDatabase(config)

    async def write_and_dispose() -> None:
        async with first.engine.begin() as connection:
            await connection.run_sync(_ModelBase.metadata.create_all)
        async with first.session() as session:
            session.add(_Record(value="persistent"))
        await first.dispose()

    asyncio.run(write_and_dispose())
    second = SQLiteDatabase(config)

    async def verify_persisted() -> None:
        async with second.session() as session:
            values = (await session.scalars(select(_Record.value))).all()
            assert values == ["persistent"]
        await second.dispose()

    asyncio.run(verify_persisted())


def test_file_sqlite_commit_error_rolls_back_and_connection_is_reusable(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(
        DatabaseConfig(driver="sqlite+aiosqlite", name=str(tmp_path / "unique.sqlite"))
    )

    async def scenario() -> None:
        async with database.engine.begin() as connection:
            await connection.run_sync(_ModelBase.metadata.create_all)
        async with database.session() as session:
            session.add(_Record(value="unique"))
        with pytest.raises(IntegrityError):
            async with database.session() as session:
                session.add(_Record(value="unique"))
        async with database.session() as session:
            values = (await session.scalars(select(_Record.value))).all()
            assert values == ["unique"]
        await database.dispose()

    asyncio.run(scenario())


def test_ensure_utc_passes_none_and_assumes_utc_for_naive_datetime() -> None:
    naive = datetime(2026, 10, 12, 12, 30)

    assert _DateHolder(None).value is None
    assert _DateHolder(naive).value == naive.replace(tzinfo=UTC)


@pytest.mark.parametrize(
    ("offset", "expected_hour"),
    [(timedelta(hours=-5), 17), (timedelta(hours=9), 3)],
)
def test_ensure_utc_converts_aware_datetime(offset: timedelta, expected_hour: int) -> None:
    local = datetime(2026, 10, 12, 12, tzinfo=timezone(offset))

    value = _DateHolder(local).value

    assert value is not None
    assert value.tzinfo is UTC
    assert value.hour == expected_hour


def test_ensure_utc_property_keeps_setter_behavior() -> None:
    holder = _DateHolder(None)
    expected = datetime(2026, 1, 2, 3)

    holder.value = expected

    assert holder.value == expected.replace(tzinfo=UTC)


def test_ensure_utc_rejects_non_datetime_getter_values() -> None:
    class InvalidDateHolder:
        """Object whose property violates the datetime contract."""

        @ensure_utc
        def value(self) -> Any:
            return "not a datetime"

    with pytest.raises(TypeError, match="datetime or None"):
        _ = InvalidDateHolder().value
