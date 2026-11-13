from django.apps import AppConfig
from django.core import checks


class SqliteSnapshotConfig(AppConfig):
    name = "sqlite_snapshot.contrib.django"
    label = "sqlite_snapshot"
    verbose_name = "SQLite snapshot"

    def ready(self):
        from .checks import check_wal_reset_bug

        # Deploy only: the warning stays relevant until SQLite is upgraded,
        # once per `check --deploy` is reminder enough.
        checks.register(check_wal_reset_bug, "sqlite_snapshot", deploy=True)
