import sqlite3
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS

from sqlite_snapshot import SnapshotError
from sqlite_snapshot.contrib.django import snapshot_database


class Command(BaseCommand):
    help = (
        "Write a consistent, integrity-checked snapshot of a live SQLite "
        "database, for backups to copy instead of the database file."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help="Database alias to snapshot (default: %(default)s).",
        )
        parser.add_argument(
            "--output",
            type=Path,
            help=(
                "Snapshot file. Default: SQLITE_SNAPSHOT_PATH for the default "
                "database, else <name>.snapshot<suffix> next to the database."
            ),
        )

    def handle(self, *args, database, output, **options):
        try:
            path = snapshot_database(using=database, dest=output)
        except (SnapshotError, sqlite3.Error) as error:
            raise CommandError(error) from error

        if path is None:
            raise CommandError(f"Database '{database}' is not an SQLite file.")
        self.stdout.write(f"{path} ({path.stat().st_size} bytes)")
