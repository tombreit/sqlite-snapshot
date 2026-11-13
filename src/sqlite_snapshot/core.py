"""
Write a consistent, self-contained copy of a live SQLite database.

A file-based backup (rsync, restic, ...) must not copy the live database file:

- In WAL mode, recent commits live in the ``-wal`` file until a checkpoint
  moves them into the database file, and a checkpoint can run at any time. A
  copy of the database file alone misses commits, and copying the two files
  one after the other is not atomic.
- In rollback-journal mode, "a backup copy of an SQLite database file while it
  is in the middle of a transaction ... might contain some old and some new
  content, and thus be corrupt" (https://www.sqlite.org/howtocorrupt.html).

``VACUUM INTO`` writes "a consistent snapshot of the original database" while
other connections keep reading and writing it
(https://www.sqlite.org/lang_vacuum.html#vacuuminto). Its output is one
file in rollback-journal mode, needs no ``-wal`` file to open, and is
compacted: free pages and deleted content are left out, which the backup API's
byte-for-byte copy would keep.

This is the one place that needs SQL: neither Python's sqlite3 module nor
Django offer ``VACUUM INTO`` or ``integrity_check`` as an API.
"""

import glob
import logging
import os
import sqlite3
import stat
import tempfile
import time
from contextlib import closing
from pathlib import Path

logger = logging.getLogger("sqlite_snapshot")

# A temp file this old is left over from a killed run, not from a running one.
# (A huey worker killed by SIGTERM never reaches its `finally`.)
STALE_TMP_AGE = 24 * 60 * 60  # seconds


class SnapshotError(RuntimeError):
    """The new snapshot failed its integrity check; the previous one is kept."""


def snapshot(source, dest, *, timeout=30):
    """
    Write a consistent copy of the SQLite database ``source`` to ``dest``.

    The copy is built in a temp file next to ``dest``, checked with
    ``PRAGMA integrity_check`` and then renamed over ``dest``. The rename is
    atomic, so a backup copying ``dest`` at any moment sees the previous
    snapshot or the new one, never a half-written file. Every run uses its own
    temp file, so overlapping runs need no lock; the last one wins.

    The snapshot gets the permission bits of ``source``, so it is readable by
    exactly whoever can read the live database. Its owner and group are those
    of the process taking the snapshot (only root could copy them).

    ``timeout`` is the busy timeout in seconds for the connection to
    ``source``. Returns ``dest`` as a ``Path``.
    """
    source = Path(source)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _remove_stale_tmp_files(dest)

    # VACUUM INTO refuses an existing file unless it is empty.
    fd, tmp_name = tempfile.mkstemp(
        dir=dest.parent, prefix=f".{dest.name}.", suffix=".tmp"
    )
    os.close(fd)
    tmp = Path(tmp_name)

    try:
        # mode=rw: a wrong path raises, instead of creating an empty database
        # and taking a snapshot of that. autocommit=True: VACUUM cannot run
        # inside a transaction.
        uri = f"{source.resolve().as_uri()}?mode=rw"
        with closing(
            sqlite3.connect(uri, uri=True, timeout=timeout, autocommit=True)
        ) as connection:
            # VACUUM INTO syncs its output to disk only if the source
            # connection's synchronous setting is NORMAL or FULL.
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("VACUUM INTO ?", (str(tmp),))

        # mkstemp created the file as 0600; set the final mode before the
        # rename, so the snapshot never appears with other permissions.
        os.chmod(tmp, stat.S_IMODE(source.stat().st_mode) & 0o777)

        result = _integrity_check(tmp)
        if result != "ok":
            raise SnapshotError(
                f"Snapshot of {source} failed integrity_check: {result}"
            )

        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)

    logger.info(
        "Snapshot of %s written to %s (%d bytes)", source, dest, dest.stat().st_size
    )
    return dest


def _integrity_check(path):
    """The first row of ``PRAGMA integrity_check``: "ok", or the first problem."""
    uri = f"{Path(path).resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, autocommit=True)) as connection:
        (result,) = connection.execute("PRAGMA integrity_check").fetchone()
    return result


def _remove_stale_tmp_files(dest):
    cutoff = time.time() - STALE_TMP_AGE
    for leftover in dest.parent.glob(f".{glob.escape(dest.name)}.*.tmp"):
        try:
            if leftover.stat().st_mtime < cutoff:
                leftover.unlink()
        except FileNotFoundError:
            pass  # removed by an overlapping run
