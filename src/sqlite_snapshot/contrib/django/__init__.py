"""
Django app: snapshots of the project's SQLite database.

Add ``"sqlite_snapshot.contrib.django"`` to ``INSTALLED_APPS`` for the
``sqlite_snapshot`` management command and the ``sqlite_snapshot.W001``
deploy check. Scheduling stays with the project, e.g. a huey periodic task::

    from huey import crontab
    from huey.contrib.djhuey import periodic_task
    from sqlite_snapshot.contrib.django import snapshot_database

    @periodic_task(crontab(minute="15"))
    def snapshot_database_task():
        snapshot_database()

Importing this package requires Django; install the optional extra with::

    pip install "sqlite-snapshot[django]"
"""

import logging
from pathlib import Path

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, connections

from sqlite_snapshot import snapshot

logger = logging.getLogger("sqlite_snapshot")


def snapshot_database(using=DEFAULT_DB_ALIAS, dest=None):
    """
    Snapshot the SQLite database ``using`` and return the snapshot's path.

    The snapshot goes to ``dest``. Without it, the default database goes to
    ``settings.SQLITE_SNAPSHOT_PATH``; otherwise, and for every other database,
    it goes next to the database file as ``<name>.snapshot<suffix>``
    (``db.sqlite3`` -> ``db.snapshot.sqlite3``).

    Returns None, and writes nothing, unless ``using`` is a file-based SQLite
    database: another backend, or the in-memory test database.
    """
    connection = connections[using]
    if connection.vendor != "sqlite" or connection.is_in_memory_db():
        logger.info("Database %r is not an SQLite file, no snapshot written.", using)
        return None

    source = Path(connection.settings_dict["NAME"])
    if dest is None and using == DEFAULT_DB_ALIAS:
        dest = getattr(settings, "SQLITE_SNAPSHOT_PATH", None)
    if dest is None:
        dest = source.with_name(f"{source.stem}.snapshot{source.suffix}")
    return snapshot(source, dest)
