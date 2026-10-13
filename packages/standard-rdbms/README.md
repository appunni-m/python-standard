# standard-rdbms

Async SQLAlchemy helpers for the [`standard`](https://pypi.org/project/standard/)
Python library. The package provides `DatabaseConfig`, managed async sessions,
SQLite, PostgreSQL, MySQL, and the `ensure_utc` property decorator under
`std.rdbms`.

Install the integration directly or select it with the `standard[rdbms]`
extra. It shares the core distribution's release version:

```console
python -m pip install standard-rdbms
python -m pip install 'standard[rdbms]'
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
