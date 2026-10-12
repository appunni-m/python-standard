"""Testcontainers coverage for PostgreSQL and MySQL session behavior."""

from __future__ import annotations

import asyncio
import os
import socket
import time
from collections.abc import Iterator

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, insert, select
from sqlalchemy.engine import make_url

from std.rdbms import DatabaseConfig, MySQLDatabase, PostgresDatabase


def _require_docker() -> None:
    """Skip without Docker locally, but fail when CI explicitly requires it."""
    import docker

    try:
        docker.from_env().ping()
    except Exception as error:
        if os.environ.get("STD_REQUIRE_DOCKER") == "1":
            pytest.fail(f"Docker is required for RDBMS E2E: {type(error).__name__}", pytrace=False)
        pytest.skip(f"Docker is unavailable: {type(error).__name__}")


def _wait_for_tcp_port(host: str, port: int) -> None:
    """Wait until Docker's published host port accepts a connection."""
    deadline = time.monotonic() + 10
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as error:
            last_error = error
            time.sleep(0.1)

    raise TimeoutError(
        f"Database container port {host}:{port} did not become reachable"
    ) from last_error


@pytest.fixture(scope="module")
def postgres_config() -> Iterator[DatabaseConfig]:
    """Start PostgreSQL with Testcontainers and return async-driver settings."""
    from testcontainers.community.postgres import PostgresContainer

    _require_docker()
    with PostgresContainer(
        "postgres:16-alpine",
        username="standard_test",
        password="standard_test_password",
        dbname="standard_test",
        driver=None,
    ) as container:
        parsed_url = make_url(container.get_connection_url())
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(5432))
        _wait_for_tcp_port(host, port)
        yield DatabaseConfig(
            driver="postgresql+asyncpg",
            host=host,
            port=port,
            user=parsed_url.username,
            password=parsed_url.password,
            name=parsed_url.database or "standard_test",
        )


@pytest.fixture(scope="module")
def mysql_config() -> Iterator[DatabaseConfig]:
    """Start MySQL with Testcontainers and return async-driver settings."""
    from testcontainers.community.mysql import MySqlContainer

    _require_docker()
    with MySqlContainer(
        "mysql:8.4",
        dialect="pymysql",
        username="standard_test",
        password="standard_test_password",
        dbname="standard_test",
    ) as container:
        parsed_url = make_url(container.get_connection_url())
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(3306))
        _wait_for_tcp_port(host, port)
        yield DatabaseConfig(
            driver="mysql+aiomysql",
            host=host,
            port=port,
            user=parsed_url.username,
            password=parsed_url.password,
            name=parsed_url.database or "standard_test",
        )


def _transaction_table(database_name: str) -> tuple[MetaData, Table]:
    """Build a small isolated table used by each container test."""
    metadata = MetaData()
    table = Table(
        database_name,
        metadata,
        Column("id", Integer, primary_key=True),
        Column("value", String(100), nullable=False, unique=True),
    )
    return metadata, table


@pytest.mark.e2e
@pytest.mark.integration
def test_postgres_sessions_commit_rollback_and_release_connections(
    postgres_config: DatabaseConfig,
) -> None:
    """Verify PostgreSQL sessions commit successful scopes and roll back failures."""
    database = PostgresDatabase(postgres_config)
    metadata, table = _transaction_table("std_rdbms_postgres_records")

    async def scenario() -> None:
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(metadata.create_all)

            async with database.session() as session:
                await session.execute(insert(table).values(value="committed"))

            with pytest.raises(RuntimeError, match="force rollback"):
                async with database.session() as session:
                    await session.execute(insert(table).values(value="rolled back"))
                    raise RuntimeError("force rollback")

            async with database.session() as session:
                values = (await session.scalars(select(table.c.value))).all()
                assert values == ["committed"]
        finally:
            try:
                async with database.engine.begin() as connection:
                    await connection.run_sync(metadata.drop_all)
            finally:
                await database.dispose()

    asyncio.run(scenario())


@pytest.mark.e2e
@pytest.mark.integration
def test_mysql_sessions_commit_rollback_and_release_connections(
    mysql_config: DatabaseConfig,
) -> None:
    """Verify MySQL sessions commit successful scopes and roll back failures."""
    database = MySQLDatabase(mysql_config)
    metadata, table = _transaction_table("std_rdbms_mysql_records")

    async def scenario() -> None:
        try:
            async with database.engine.begin() as connection:
                await connection.run_sync(metadata.create_all)

            async with database.session() as session:
                await session.execute(insert(table).values(value="committed"))

            with pytest.raises(RuntimeError, match="force rollback"):
                async with database.session() as session:
                    await session.execute(insert(table).values(value="rolled back"))
                    raise RuntimeError("force rollback")

            async with database.session() as session:
                values = (await session.scalars(select(table.c.value))).all()
                assert values == ["committed"]
        finally:
            try:
                async with database.engine.begin() as connection:
                    await connection.run_sync(metadata.drop_all)
            finally:
                await database.dispose()

    asyncio.run(scenario())
