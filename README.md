# sqlite-snapshot

`sqlite-snapshot` writes a consistent, integrity-checked copy of a live SQLite
database to one file. File-based backups (rsync, restic, ...) copy that file
instead of the live database.

## Why

A file-based backup must not copy a live SQLite database:

- **WAL mode:** recent commits live in the `-wal` file until a checkpoint moves
  them into the database file, and a checkpoint can run at any time. A copy of
  the database file alone misses commits, and copying `db.sqlite3` and
  `db.sqlite3-wal` one after the other is not atomic. Here a snapshot is
  necessary.
- **Rollback-journal mode** (SQLite's default): "Systems that run automatic
  backups in the background might try to make a backup copy of an SQLite
  database file while it is in the middle of a transaction. The backup copy
  then might contain some old and some new content, and thus be corrupt."
  ([How To Corrupt An SQLite Database File](https://www.sqlite.org/howtocorrupt.html),
  section 1.2). The window is short, but a snapshot is still advisable.

## How

[`VACUUM INTO`](https://www.sqlite.org/lang_vacuum.html#vacuuminto) writes "a
consistent snapshot of the original database" while other connections keep
reading and writing it. Compared to the
[online backup API](https://www.sqlite.org/backup.html), its output is
compacted: free pages and deleted content are left out ("no forensic
traces"). The snapshot is a single file in rollback-journal mode and needs no
`-wal` file to open.

`snapshot()`:

1. Writes the copy to a temp file next to the destination. Every run has its
   own temp file, so overlapping runs need no lock.
2. Checks the copy with `PRAGMA integrity_check`; on failure it raises
   `SnapshotError` and keeps the previous snapshot.
3. Renames it over the destination. The rename is atomic: a backup sees the
   previous snapshot or the new one, never a half-written file.

The snapshot is synced to disk, and only readable by its owner (mode 0600).
A source path that doesn't exist raises an error rather than producing a
snapshot of an empty database. Temp files left behind by a killed run are
removed by the first run a day later.

## Requirements

- Python 3.12+
- No runtime dependencies; Django 5.2+ for the optional Django app

## Install

```bash
pip install "sqlite-snapshot[django] @ git+https://github.com/tombreit/sqlite-snapshot.git"
```

Leave out `[django]` for the core function only.

## Usage

### Python

```python
from sqlite_snapshot import snapshot

snapshot("data/db.sqlite3", "data/db.snapshot.sqlite3")
```

### Django

```python
INSTALLED_APPS = [
    # ...
    "sqlite_snapshot.contrib.django",
]

# Optional; default: next to the database, db.sqlite3 -> db.snapshot.sqlite3
SQLITE_SNAPSHOT_PATH = DATA_DIR / "db.snapshot.sqlite3"
```

The app adds the management command:

```bash
./manage.py sqlite_snapshot [--database ALIAS] [--output PATH]
```

The package doesn't schedule anything; that stays with the project. With
[huey](https://huey.readthedocs.io/), add a periodic task to one of your apps' `tasks.py`:

```python
from huey import crontab
from huey.contrib.djhuey import periodic_task
from sqlite_snapshot.contrib.django import snapshot_database


@periodic_task(crontab(minute="15"))
def snapshot_database_task():
    snapshot_database()
```

Without huey, run the command from cron:

```cron
15 * * * *  cd /srv/app && .venv/bin/python manage.py sqlite_snapshot
```

`snapshot_database()` returns None and writes nothing unless the database is
an SQLite file, so the task is harmless on Postgres or with the in-memory test
database. Log messages go to the `sqlite_snapshot` logger.

## Backup and restore

Back up the snapshot. Leave out the live `db.sqlite3`, `db.sqlite3-wal` and
`db.sqlite3-shm`.

To restore:

1. Stop everything that uses the database (web server, task worker).
2. Remove `db.sqlite3`, `db.sqlite3-wal` and `db.sqlite3-shm`.
3. Copy the snapshot to `db.sqlite3`.
4. Start everything again. If the project sets `PRAGMA journal_mode=WAL`, the
   first connection switches the file back to WAL.

## Deploy check `sqlite_snapshot.W001`

SQLite 3.7.0 through 3.51.2 has the
[WAL-reset bug](https://www.sqlite.org/wal.html) (section 11). With two
connections in separate threads or processes that write or checkpoint at the
same instant, it can, rarely, corrupt a WAL database. 3.51.3 fixes it, with
backports in 3.50.7 and 3.44.6. Debian 13's SQLite 3.46.1 is affected.

`manage.py check --deploy` warns for each SQLite database whose
`OPTIONS["init_command"]` enables WAL while the SQLite that Python uses is
affected. If your distribution backported the fix without changing the
version, silence it:

```python
SILENCED_SYSTEM_CHECKS = ["sqlite_snapshot.W001"]
```

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[django,test]"
.venv/bin/pytest
```

## License

[EUPL-1.2](LICENSE)
