"""The core snapshot(), without Django."""

import os
import sqlite3
import time
from contextlib import closing

import pytest

import sqlite_snapshot.core
from sqlite_snapshot import SnapshotError, snapshot


def _leftover_tmp_files(directory):
    return sorted(p.name for p in directory.glob(".*.tmp"))


def test_snapshot_contains_the_commits_still_in_the_wal(wal_database, count_items):
    path, _writer = wal_database
    dest = path.with_name("db.snapshot.sqlite3")

    assert snapshot(path, dest) == dest

    assert count_items(dest) == 100


def test_snapshot_is_a_single_file_in_rollback_journal_mode(wal_database):
    path, _writer = wal_database
    dest = path.with_name("db.snapshot.sqlite3")

    snapshot(path, dest)

    with closing(sqlite3.connect(dest)) as reader:
        assert reader.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert sorted(p.name for p in path.parent.iterdir()) == [
        "db.snapshot.sqlite3",
        "db.sqlite3",
        "db.sqlite3-shm",
        "db.sqlite3-wal",
    ]


def test_snapshot_of_a_rollback_journal_database(tmp_path, count_items):
    path = tmp_path / "db.sqlite3"
    with closing(sqlite3.connect(path, autocommit=True)) as writer:
        writer.execute("CREATE TABLE item (name TEXT)")
        writer.execute("INSERT INTO item VALUES ('only item')")

    snapshot(path, tmp_path / "db.snapshot.sqlite3")

    assert count_items(tmp_path / "db.snapshot.sqlite3") == 1


def test_snapshot_replaces_the_previous_one(wal_database, count_items):
    path, writer = wal_database
    dest = path.with_name("db.snapshot.sqlite3")
    snapshot(path, dest)

    writer.execute("INSERT INTO item VALUES ('item 100')")
    snapshot(path, dest)

    assert count_items(dest) == 101
    assert _leftover_tmp_files(path.parent) == []


def test_snapshot_creates_the_destination_directory(wal_database, count_items):
    path, _writer = wal_database
    dest = path.parent / "backup" / "nightly" / "db.sqlite3"

    snapshot(path, dest)

    assert count_items(dest) == 100


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o600])
def test_snapshot_has_the_permissions_of_the_source(wal_database, mode):
    path, _writer = wal_database
    path.chmod(mode)
    dest = path.with_name("db.snapshot.sqlite3")

    snapshot(path, dest)

    assert dest.stat().st_mode & 0o777 == mode


def test_stale_temp_files_are_removed_and_fresh_ones_kept(wal_database):
    path, _writer = wal_database
    dest = path.with_name("db.snapshot.sqlite3")
    stale = path.with_name(".db.snapshot.sqlite3.killed.tmp")
    fresh = path.with_name(".db.snapshot.sqlite3.running.tmp")
    stale.write_bytes(b"left over from a killed run")
    fresh.write_bytes(b"a run in progress")
    two_days_ago = time.time() - 2 * 24 * 60 * 60
    os.utime(stale, (two_days_ago, two_days_ago))

    snapshot(path, dest)

    assert _leftover_tmp_files(path.parent) == [fresh.name]


def test_missing_source_raises_and_creates_nothing(tmp_path):
    source = tmp_path / "missing.sqlite3"
    dest = tmp_path / "missing.snapshot.sqlite3"

    with pytest.raises(sqlite3.OperationalError):
        snapshot(source, dest)

    assert list(tmp_path.iterdir()) == []


def test_failed_integrity_check_keeps_the_previous_snapshot(
    wal_database, count_items, monkeypatch
):
    path, writer = wal_database
    dest = path.with_name("db.snapshot.sqlite3")
    snapshot(path, dest)
    writer.execute("INSERT INTO item VALUES ('item 100')")
    monkeypatch.setattr(
        sqlite_snapshot.core,
        "_integrity_check",
        lambda path: "*** in database main ***",
    )

    with pytest.raises(SnapshotError, match="integrity_check"):
        snapshot(path, dest)

    assert count_items(dest) == 100
    assert _leftover_tmp_files(path.parent) == []
