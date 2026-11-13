"""Shared fixtures for sqlite_snapshot tests."""

import sqlite3
from contextlib import closing

import pytest


@pytest.fixture
def wal_database(tmp_path):
    """A WAL database whose 100 commits are all still in the -wal file, with its writer open."""
    path = tmp_path / "db.sqlite3"
    writer = sqlite3.connect(path, autocommit=True)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")  # keep every commit in the -wal file
    writer.execute("CREATE TABLE item (name TEXT)")
    writer.executemany(
        "INSERT INTO item VALUES (?)", [(f"item {n}",) for n in range(100)]
    )
    assert (tmp_path / "db.sqlite3-wal").stat().st_size > 0
    yield path, writer
    writer.close()


@pytest.fixture
def count_items():
    def count(path):
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as reader:
            return reader.execute("SELECT count(*) FROM item").fetchone()[0]

    return count
