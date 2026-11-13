"""The Django app: snapshot_database(), the management command and the deploy check.

None of these tests use the `db` fixture, so pytest-django leaves the default
database's NAME alone and the tests can point it at a file.
"""

import sqlite3
from io import StringIO

import pytest
from django.core.checks import registry
from django.core.management import CommandError, call_command
from django.db import connections

from sqlite_snapshot.contrib.django import snapshot_database
from sqlite_snapshot.contrib.django.checks import check_wal_reset_bug, has_wal_reset_bug


@pytest.fixture
def default_db_file(wal_database, monkeypatch):
    """Point the default database at a WAL database file."""
    path, _writer = wal_database
    monkeypatch.setitem(connections["default"].settings_dict, "NAME", str(path))
    return path


def test_command_writes_the_snapshot_next_to_the_database(default_db_file, count_items):
    stdout = StringIO()

    call_command("sqlite_snapshot", stdout=stdout)

    dest = default_db_file.with_name("db.snapshot.sqlite3")
    assert count_items(dest) == 100
    assert str(dest) in stdout.getvalue()


def test_setting_sets_the_snapshot_path(
    default_db_file, count_items, settings, tmp_path
):
    settings.SQLITE_SNAPSHOT_PATH = tmp_path / "backup" / "toolbox.sqlite3"

    assert snapshot_database() == tmp_path / "backup" / "toolbox.sqlite3"
    assert count_items(tmp_path / "backup" / "toolbox.sqlite3") == 100


def test_output_option_wins_over_the_setting(
    default_db_file, count_items, settings, tmp_path
):
    settings.SQLITE_SNAPSHOT_PATH = tmp_path / "from-setting.sqlite3"

    call_command(
        "sqlite_snapshot", output=tmp_path / "from-option.sqlite3", stdout=StringIO()
    )

    assert count_items(tmp_path / "from-option.sqlite3") == 100
    assert not (tmp_path / "from-setting.sqlite3").exists()


def test_in_memory_database_is_skipped():
    assert snapshot_database() is None
    with pytest.raises(CommandError, match="not an SQLite file"):
        call_command("sqlite_snapshot")


def test_other_backends_are_skipped(default_db_file, monkeypatch):
    monkeypatch.setattr(connections["default"], "vendor", "postgresql")

    assert snapshot_database() is None
    assert not default_db_file.with_name("db.snapshot.sqlite3").exists()


def test_command_reports_a_missing_database_file(monkeypatch, tmp_path):
    monkeypatch.setitem(
        connections["default"].settings_dict, "NAME", str(tmp_path / "missing.sqlite3")
    )

    with pytest.raises(CommandError, match="unable to open database file"):
        call_command("sqlite_snapshot")


@pytest.mark.parametrize(
    ("version", "affected"),
    [
        ((3, 46, 1), True),  # Debian 13
        ((3, 51, 2), True),
        ((3, 51, 3), False),
        ((3, 54, 1), False),
        ((3, 50, 6), True),
        ((3, 50, 7), False),  # backport
        ((3, 44, 5), True),
        ((3, 44, 6), False),  # backport
        ((3, 45, 0), True),
    ],
)
def test_affected_versions(version, affected):
    assert has_wal_reset_bug(version) is affected


@pytest.mark.parametrize(
    "init_command",
    [
        "PRAGMA journal_mode=WAL;",
        "PRAGMA synchronous=NORMAL; PRAGMA journal_mode = wal;",
    ],
)
def test_check_warns_for_wal_on_an_affected_version(init_command, monkeypatch):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 46, 1))
    monkeypatch.setitem(
        connections["default"].settings_dict, "OPTIONS", {"init_command": init_command}
    )

    (warning,) = check_wal_reset_bug()

    assert warning.id == "sqlite_snapshot.W001"
    assert "3.46.1" in warning.msg


def test_check_is_quiet_on_a_fixed_version(monkeypatch):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 51, 3))
    monkeypatch.setitem(
        connections["default"].settings_dict,
        "OPTIONS",
        {"init_command": "PRAGMA journal_mode=WAL;"},
    )

    assert check_wal_reset_bug() == []


def test_check_is_quiet_without_wal(monkeypatch):
    monkeypatch.setattr(sqlite3, "sqlite_version_info", (3, 46, 1))
    monkeypatch.setitem(
        connections["default"].settings_dict,
        "OPTIONS",
        {"init_command": "PRAGMA synchronous=FULL;"},
    )

    assert check_wal_reset_bug() == []


def test_check_runs_only_on_deploy():
    assert check_wal_reset_bug in registry.registry.get_checks(
        include_deployment_checks=True
    )
    assert check_wal_reset_bug not in registry.registry.get_checks(
        include_deployment_checks=False
    )
