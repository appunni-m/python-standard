# Relational databases

`standard-rdbms` adds async relational database helpers under `std.rdbms`.
It supports SQLite files, shared in-memory SQLite, PostgreSQL, and MySQL through
SQLAlchemy's asyncio extension.

## Install

When the integration has been published, install it with:

```console
python -m pip install standard-rdbms
```

The package has its own dependencies and can be built independently from the
core `standard` distribution. It does not make core import SQLAlchemy or a
database driver.

## Configure

`DatabaseConfig` holds the connection and pool settings. Defaults preserve the
existing behavior: `mysql+aiomysql`, host `localhost`, database
`agent_framework`, pool size 5, maximum overflow 10, 30-second pool timeout,
and a 30-minute connection recycle interval.

```python
from std.rdbms import DatabaseConfig, PostgresDatabase

config = DatabaseConfig(
    driver="postgresql+asyncpg",
    host="localhost",
    port=5432,
    user="app",
    password="replace-with-a-secret",
    name="appdb",
)
database = PostgresDatabase(config)
```

The `url` property is built with SQLAlchemy's structured URL type, so reserved
characters in usernames and passwords are escaped correctly. SQLite paths use
SQLAlchemy's slash semantics, including spaces in file names. The URL includes
the password for connection use. `repr(config)` and
`config.model_dump()` omit the password; avoid logging `config.url`.
SQLite relative paths resolve from the current working directory. Use an
absolute path to select a specific file.

Backend managers copy the supplied model before adding backend defaults. They
do not mutate the caller's config or its `connect_args` mapping.

## Use managed sessions

```python
from sqlalchemy import select
from std.rdbms import DatabaseConfig, SQLiteMemDatabase

database = SQLiteMemDatabase(DatabaseConfig(driver="sqlite+aiosqlite"))

async with database.session() as session:
    result = await session.execute(select(MyModel))
    rows = result.scalars().all()
    # The scope commits automatically when it exits successfully.

await database.dispose()
```

Every session context owns one transaction. Normal exit commits. Exceptions,
commit failures, and task cancellation roll back and propagate the original
error. The session closes in every case; a cleanup error is attached to the
original exception instead of replacing it. A session is mutable state and
must not be shared between concurrent asyncio tasks. A disposed manager rejects
new sessions, and repeated `dispose()` calls are safe.

For deterministic application shutdown, use the manager as an async context
manager or call `await database.dispose()` from the app lifecycle. The
`database.engine` property is available for migrations and explicit
SQLAlchemy-level transactions.

## SQLite

```python
from std.rdbms import DatabaseConfig, SQLiteDatabase, SQLiteMemDatabase

file_db = SQLiteDatabase(
    DatabaseConfig(driver="sqlite+aiosqlite", name="./data/app.db")
)
memory_db = SQLiteMemDatabase(
    DatabaseConfig(driver="sqlite+aiosqlite", name=":memory:")
)
```

File-backed SQLite uses `NullPool` and defaults `check_same_thread` to false.
In-memory SQLite uses `StaticPool`, so multiple sessions share the same
database. `SQLiteDatabase` rejects `:memory:` because a new connection could
otherwise see a separate empty database. `SQLiteMemDatabase` forces a private
copy of its settings to `:memory:` and leaves the caller's config unchanged.

## PostgreSQL and MySQL

`PostgresDatabase` uses PostgreSQL async drivers, applies the configured pool
values, enables `pool_pre_ping`, and defaults the server application name to
`standard-rdbms`. `MySQLDatabase` uses MySQL async drivers, applies the same
pool options and health check, and defaults to `utf8mb4` with autocommit off.
Explicit values in `connect_args` take precedence over these defaults.

The distribution installs `asyncpg`, `aiomysql`, and `cryptography` with the
package. `cryptography` lets aiomysql authenticate against MySQL's default
`caching_sha2_password` plugin. Driver names may be changed to another SQLAlchemy
async dialect, but the selected dialect must support `create_async_engine`.

## UTC datetime properties

`ensure_utc` decorates a property getter. It interprets naive datetimes as UTC,
converts aware datetimes to UTC, and passes `None` through. Non-datetime values
raise `TypeError` with a local explanation.

```python
from datetime import datetime
from std.rdbms import ensure_utc

class Event:
    def __init__(self, created_at: datetime | None) -> None:
        self._created_at = created_at

    @ensure_utc
    def created_at(self) -> datetime | None:
        return self._created_at
```

The decorator returns a property, so define a setter with
`@created_at.setter` if the model needs assignment. Stored values are not
rewritten; UTC normalization happens when the property is read.

## Verify

SQLite unit tests cover URL edge cases, SQLite file persistence, shared memory,
transaction commit/rollback, cleanup, and UTC conversion. Container-backed
PostgreSQL and MySQL tests run through Testcontainers:

```console
make test-e2e
```

The database managers follow SQLAlchemy's
[asyncio guidance](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
for per-task sessions and explicit engine disposal. Container fixtures follow
the [Testcontainers PostgreSQL](https://testcontainers-python.readthedocs.io/en/latest/modules/postgres/README.html)
and [MySQL](https://testcontainers-python.readthedocs.io/en/latest/modules/mysql/README.html)
interfaces. E2E tests skip when Docker is unavailable unless
`STD_REQUIRE_DOCKER=1` is set.
