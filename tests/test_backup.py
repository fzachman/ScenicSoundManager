"""Tests for database backup/restore (app/database/backup.py + backup_to)."""

import sqlite3

import pytest

from app import APP_DISPLAY_NAME
from app.database import (
    AudioFile,
    DatabaseConnection,
    swap_database,
    validate_backup,
)


@pytest.fixture
def db(tmp_path):
    conn = DatabaseConnection(str(tmp_path / "live.db"))
    conn.connect()
    yield conn
    conn.close()


def _file_count(path) -> int:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT COUNT(*) FROM audio_files").fetchone()[0]
    finally:
        conn.close()


class TestBackupTo:
    def test_snapshot_while_connection_is_live(self, db, tmp_path):
        db.add_audio_file(AudioFile(file_path="/music/a.mp3", title="A"))
        db.add_audio_file(AudioFile(file_path="/music/b.mp3", title="B"))
        dest = tmp_path / "backup.db"

        db.backup_to(str(dest))

        assert _file_count(dest) == 2
        # The live connection stays usable afterwards.
        db.add_audio_file(AudioFile(file_path="/music/c.mp3", title="C"))
        assert len(db.get_all_audio_files()) == 3

    def test_overwrites_existing_destination(self, db, tmp_path):
        dest = tmp_path / "backup.db"
        db.add_audio_file(AudioFile(file_path="/music/a.mp3", title="A"))
        db.backup_to(str(dest))
        db.add_audio_file(AudioFile(file_path="/music/b.mp3", title="B"))

        db.backup_to(str(dest))

        assert _file_count(dest) == 2

    def test_backup_is_restorable(self, db, tmp_path):
        db.add_audio_file(AudioFile(file_path="/music/a.mp3", title="A"))
        dest = tmp_path / "backup.db"
        db.backup_to(str(dest))
        assert validate_backup(str(dest)) is None


class TestValidateBackup:
    def test_missing_file(self, tmp_path):
        assert validate_backup(str(tmp_path / "nope.db")) is not None

    def test_garbage_file(self, tmp_path):
        garbage = tmp_path / "garbage.db"
        garbage.write_bytes(b"this is not sqlite at all" * 100)
        assert validate_backup(str(garbage)) is not None

    def test_foreign_sqlite_database(self, tmp_path):
        foreign = tmp_path / "foreign.db"
        conn = sqlite3.connect(foreign)
        conn.execute("CREATE TABLE stuff (id INTEGER)")
        conn.commit()
        conn.close()
        error = validate_backup(str(foreign))
        assert error is not None
        assert APP_DISPLAY_NAME in error

    def test_validation_never_modifies_file(self, db, tmp_path):
        dest = tmp_path / "backup.db"
        db.backup_to(str(dest))
        before = dest.read_bytes()
        validate_backup(str(dest))
        assert dest.read_bytes() == before


class TestSwapDatabase:
    def test_swaps_and_keeps_safety_copy(self, tmp_path):
        current = tmp_path / "soundmanager.db"
        current.write_bytes(b"current-data")
        backup = tmp_path / "backup.db"
        backup.write_bytes(b"backup-data")

        safety = swap_database(current, backup)

        assert current.read_bytes() == b"backup-data"
        assert safety.read_bytes() == b"current-data"
        assert "pre-restore" in safety.name
        # The source backup file is untouched (copied, not moved).
        assert backup.read_bytes() == b"backup-data"

    def test_swap_without_existing_current(self, tmp_path):
        current = tmp_path / "soundmanager.db"
        backup = tmp_path / "backup.db"
        backup.write_bytes(b"backup-data")

        swap_database(current, backup)

        assert current.read_bytes() == b"backup-data"
