"""Saving, reopening, backups and opening the wrong kind of file."""

import sqlite3
from datetime import date, timedelta

import pytest

from truck_tms.database import Database, Driver, Load, Truck, ValidationError, auto_backup, backups_folder


def test_data_is_saved_to_disk_immediately(tmp_path):
    path = tmp_path / "tms.db"
    db = Database(path)
    db.add_truck(Truck(unit_number="101"))
    db.add_driver(Driver(name="Ann"))
    # read the file with a separate connection while the app still has it open
    other = sqlite3.connect(path)
    assert other.execute("SELECT unit_number FROM trucks").fetchone()[0] == "101"
    other.close()
    db.close()
    reopened = Database(path)
    assert [tr.unit_number for tr in reopened.list_trucks()] == ["101"]
    assert [d.name for d in reopened.list_drivers()] == ["Ann"]
    reopened.close()


def test_change_count_moves_on_every_save(tmp_path):
    db = Database(tmp_path / "tms.db")
    before = db.change_count
    db.add_load(Load(rate=100))
    assert db.change_count > before
    db.close()


def test_backup_copy(tmp_path):
    db = Database(tmp_path / "tms.db")
    db.add_truck(Truck(plate="ABC1"))
    target = db.backup_to(tmp_path / "copies" / "backup.db")
    copy = Database(target)
    assert copy.find_truck("ABC1") is not None
    copy.close()
    with pytest.raises(ValidationError) as exc:
        db.backup_to(tmp_path / "tms.db")  # never overwrite the open file
    assert exc.value.key == "file.backup_same"
    db.close()


def test_auto_backup_once_a_day_and_keeps_14(tmp_path):
    path = tmp_path / "tms.db"
    db = Database(path)
    db.add_truck(Truck(plate="X1"))
    db.close()
    start = date(2026, 1, 1)
    for i in range(20):
        auto_backup(path, today=start + timedelta(days=i))
    auto_backup(path, today=start + timedelta(days=19))  # same day again: no new copy
    copies = sorted(p.name for p in backups_folder(path).iterdir())
    assert len(copies) == 14
    assert copies[-1] == "tms_2026-01-20.db"
    assert copies[0] == "tms_2026-01-07.db"
    restored = Database(backups_folder(path) / copies[-1])
    assert restored.find_truck("X1") is not None
    restored.close()


def test_auto_backup_skips_missing_or_memory(tmp_path):
    assert auto_backup(":memory:") is None
    assert auto_backup(tmp_path / "does_not_exist.db") is None


def test_opening_a_non_database_file_is_refused(tmp_path):
    bad = tmp_path / "notes.db"
    bad.write_text("this is not a database " * 50)
    with pytest.raises(ValidationError) as exc:
        Database(bad)
    assert exc.value.key == "file.not_valid"
