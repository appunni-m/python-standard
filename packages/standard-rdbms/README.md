# standard-rdbms

Async SQLAlchemy helpers for the [`standard`](https://pypi.org/project/standard/)
Python library. The package provides `DatabaseConfig`, managed async sessions,
SQLite, PostgreSQL, MySQL, and the `ensure_utc` property decorator under
`std.rdbms`.

After publication, install the integration directly:

```console
python -m pip install standard-rdbms
```

For local development from this repository:

```console
python -m pip install -e packages/standard-rdbms
```

```python
from std.rdbms import DatabaseConfig, SQLiteMemDatabase

database = SQLiteMemDatabase(DatabaseConfig(driver="sqlite+aiosqlite"))
```

See the [RDBMS guide](https://appunni-m.github.io/python-standard/rdbms/)
for transactions, backend configuration, datetime behavior, and test commands.
