"""sqlite_snapshot: consistent, copyable snapshots of a live SQLite database."""

from sqlite_snapshot.core import SnapshotError, snapshot

__all__ = ["SnapshotError", "snapshot"]
