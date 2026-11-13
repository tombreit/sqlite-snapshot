"""
Deploy check for SQLite's WAL-reset bug (https://www.sqlite.org/wal.html, section 11).

The bug is in SQLite 3.7.0 through 3.51.2 and fixed in 3.51.3, with backports
to 3.44.6 and 3.50.7. It needs WAL mode and two connections in separate
threads or processes that write or checkpoint at the same instant, e.g. web
server and task worker. It is rare, but can corrupt the database.
"""

import re
import sqlite3

from django.core import checks
from django.db import connections

FIXED_IN = (3, 51, 3)
# [first fixed, end of that release line) for the backports.
BACKPORTS = [((3, 44, 6), (3, 45, 0)), ((3, 50, 7), (3, 51, 0))]

_ENABLES_WAL = re.compile(r"journal_mode\s*=\s*['\"]?wal\b", re.IGNORECASE)


def has_wal_reset_bug(version):
    """Whether the SQLite ``version`` tuple, e.g. (3, 46, 1), has the bug."""
    if version >= FIXED_IN:
        return False
    return not any(first <= version < end for first, end in BACKPORTS)


def check_wal_reset_bug(app_configs=None, **kwargs):
    version = sqlite3.sqlite_version_info
    if not has_wal_reset_bug(version):
        return []

    return [
        checks.Warning(
            f"SQLite {'.'.join(map(str, version))} has the WAL-reset bug, "
            f"which can corrupt the database '{alias}' in WAL mode.",
            hint=(
                "Upgrade SQLite to 3.51.3 or later, or to 3.50.7 or 3.44.6. "
                "If your distribution backported the fix without changing the "
                "version, add 'sqlite_snapshot.W001' to SILENCED_SYSTEM_CHECKS. "
                "See https://www.sqlite.org/wal.html, section 11."
            ),
            id="sqlite_snapshot.W001",
        )
        for alias in connections
        if connections[alias].vendor == "sqlite"
        and _ENABLES_WAL.search(
            str(connections[alias].settings_dict["OPTIONS"].get("init_command", ""))
        )
    ]
