"""Tests for the 2026-07 identity-rename startup migrations.

The settings migration is exercised through scratch QSettings namespaces
(never the real "SoundManager" org or the shared SoundManagerTests one,
which conftest pre-populates); the database migration through tmp_path.
"""

import pytest
from PyQt6.QtCore import QSettings

from app.migrations import _app_keys, _migrate_database, _migrate_settings

OLD_NS = ("SoundManagerTestsMigOld", "MigOld")
NEW_NS = ("SoundManagerTestsMigNew", "MigNew")


@pytest.fixture
def old_settings(qapp):
    settings = QSettings(*OLD_NS)
    settings.clear()
    yield settings
    settings.clear()


@pytest.fixture
def new_settings(qapp):
    settings = QSettings(*NEW_NS)
    settings.clear()
    yield settings
    settings.clear()


class TestSettingsMigration:
    def test_copies_all_keys_once(self, old_settings, new_settings):
        old_settings.setValue("audio/master_volume", 87)
        old_settings.setValue("remote/enabled", True)
        old_settings.setValue("ui/active_tab", 2)

        assert _migrate_settings(old_settings, new_settings) is True
        assert new_settings.value("audio/master_volume", type=int) == 87
        assert new_settings.value("remote/enabled", type=bool) is True
        assert new_settings.value("ui/active_tab", type=int) == 2
        # Legacy namespace is untouched (kept as a fallback).
        assert old_settings.value("audio/master_volume", type=int) == 87

    def test_noop_when_new_namespace_has_any_key(self, old_settings, new_settings):
        old_settings.setValue("audio/master_volume", 87)
        new_settings.setValue("ui/active_tab", 1)

        assert _migrate_settings(old_settings, new_settings) is False
        # Nothing copied over the existing namespace.
        assert new_settings.value("audio/master_volume") is None

    def test_noop_when_no_legacy_settings(self, old_settings, new_settings):
        assert _migrate_settings(old_settings, new_settings) is False
        assert _app_keys(new_settings) == []

    def test_ignores_macos_global_domain_noise(self, old_settings, new_settings):
        # macOS merges NSGlobalDomain (AppleLocale etc.) into allKeys(); only
        # the app's own groups may count toward the guard or get copied.
        old_settings.setValue("audio/master_volume", 87)
        assert _migrate_settings(old_settings, new_settings) is True
        copied = _app_keys(new_settings)
        assert copied == ["audio/master_volume"]
        assert "AppleLocale" not in copied

    def test_idempotent_after_migration(self, old_settings, new_settings):
        old_settings.setValue("audio/master_volume", 87)
        assert _migrate_settings(old_settings, new_settings) is True
        old_settings.setValue("audio/master_volume", 12)  # later legacy write
        assert _migrate_settings(old_settings, new_settings) is False
        assert new_settings.value("audio/master_volume", type=int) == 87


class TestDatabaseMigration:
    def test_moves_db_and_removes_empty_legacy_dir(self, tmp_path):
        old_dir = tmp_path / "SoundManager"
        old_dir.mkdir()
        old_db = old_dir / "soundmanager.db"
        old_db.write_bytes(b"sqlite-bytes")
        new_db = tmp_path / "ScenicSound" / "soundmanager.db"

        assert _migrate_database(old_db, new_db) is True
        assert new_db.read_bytes() == b"sqlite-bytes"
        assert not old_db.exists()
        assert not old_dir.exists()  # emptied dir is tidied away

    def test_moves_journal_siblings(self, tmp_path):
        old_dir = tmp_path / "SoundManager"
        old_dir.mkdir()
        (old_dir / "soundmanager.db").write_bytes(b"db")
        (old_dir / "soundmanager.db-wal").write_bytes(b"wal")
        (old_dir / "soundmanager.db-shm").write_bytes(b"shm")
        new_db = tmp_path / "ScenicSound" / "soundmanager.db"

        assert _migrate_database(old_dir / "soundmanager.db", new_db) is True
        assert (new_db.parent / "soundmanager.db-wal").read_bytes() == b"wal"
        assert (new_db.parent / "soundmanager.db-shm").read_bytes() == b"shm"

    def test_never_overwrites_existing_new_db(self, tmp_path):
        old_dir = tmp_path / "SoundManager"
        old_dir.mkdir()
        old_db = old_dir / "soundmanager.db"
        old_db.write_bytes(b"legacy")
        new_db = tmp_path / "ScenicSound" / "soundmanager.db"
        new_db.parent.mkdir()
        new_db.write_bytes(b"current")

        assert _migrate_database(old_db, new_db) is False
        assert new_db.read_bytes() == b"current"
        assert old_db.exists()

    def test_migrates_even_when_new_dir_exists_empty(self, tmp_path):
        # DatabaseConnection mkdirs the new dir eagerly; an empty new dir
        # must not fool the migration into skipping (or nesting the move).
        old_dir = tmp_path / "SoundManager"
        old_dir.mkdir()
        old_db = old_dir / "soundmanager.db"
        old_db.write_bytes(b"legacy")
        new_dir = tmp_path / "ScenicSound"
        new_dir.mkdir()
        new_db = new_dir / "soundmanager.db"

        assert _migrate_database(old_db, new_db) is True
        assert new_db.read_bytes() == b"legacy"

    def test_noop_for_fresh_install(self, tmp_path):
        old_db = tmp_path / "SoundManager" / "soundmanager.db"
        new_db = tmp_path / "ScenicSound" / "soundmanager.db"
        assert _migrate_database(old_db, new_db) is False
        assert not new_db.parent.exists()

    def test_leftover_legacy_files_keep_dir(self, tmp_path):
        old_dir = tmp_path / "SoundManager"
        old_dir.mkdir()
        old_db = old_dir / "soundmanager.db"
        old_db.write_bytes(b"db")
        (old_dir / "notes.txt").write_bytes(b"keep me")
        new_db = tmp_path / "ScenicSound" / "soundmanager.db"

        assert _migrate_database(old_db, new_db) is True
        assert (old_dir / "notes.txt").exists()  # rmdir must not force-delete
