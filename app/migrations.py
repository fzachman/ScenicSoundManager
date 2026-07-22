"""One-time startup migrations for the 2026-07 identity rename.

The app's QSettings organization moved from "SoundManager" to "ScenicSound"
(macOS domain com.soundmanager.SoundManager -> com.scenicsound.SoundManager)
and the data directory from Application Support/SoundManager to
.../ScenicSound. Both were too generic to keep — a name collision with any
other app called "SoundManager" would have shared our settings and database.

``run_startup_migrations()`` must run after the QApplication identity is set
and BEFORE anything reads QSettings or opens the database. Both steps are
idempotent. The legacy settings plist is left in place; the database file is
moved (not copied) so there is exactly one live database.
"""

import contextlib
import shutil

from PyQt6.QtCore import QSettings

from . import paths
from .shared.logging import get_logger

logger = get_logger(__name__)

LEGACY_ORG = "SoundManager"
LEGACY_APP = "SoundManager"

# The app's settings groups as of the rename. Frozen deliberately: the
# migration copies the 2026-07 snapshot of settings, nothing more. Filtering
# by group is also load-bearing on macOS, where QSettings.allKeys() merges in
# Apple's NSGlobalDomain (AppleLocale, trackpad gestures, ...) — the raw key
# list is never empty and must never be copied wholesale.
SETTINGS_GROUPS = ("audio", "library", "remote", "soundboard", "ui")


def run_startup_migrations() -> None:
    _migrate_settings(QSettings(LEGACY_ORG, LEGACY_APP), QSettings())
    _migrate_database(
        paths.LEGACY_DATA_DIR / paths.DB_FILENAME,
        paths.DATA_DIR / paths.DB_FILENAME,
    )


def _app_keys(settings: QSettings) -> list[str]:
    return [
        key for key in settings.allKeys() if key.split("/", 1)[0] in SETTINGS_GROUPS
    ]


def _migrate_settings(old: QSettings, new: QSettings) -> bool:
    """Copy the app's settings from the legacy namespace into the current one.

    Runs only while the current namespace holds no app settings, so it fires
    at most once (the first write — including this copy — arms the guard).
    The legacy plist is untouched and stays behind as a fallback.
    """
    if _app_keys(new):
        return False
    keys = _app_keys(old)
    if not keys:
        return False
    for key in keys:
        new.setValue(key, old.value(key))
    new.sync()
    logger.info("settings_migrated", keys=len(keys), file=new.fileName())
    return True


def _migrate_database(old_db, new_db) -> bool:
    """Move the SQLite database (plus any journal siblings) to its new home.

    Keyed on the database FILE, not the directory: the new directory may
    already exist empty (DatabaseConnection mkdirs eagerly), and an existing
    new database must never be overwritten.
    """
    if new_db.exists() or not old_db.exists():
        return False
    new_db.parent.mkdir(parents=True, exist_ok=True)
    # Journal/WAL siblings (soundmanager.db-journal, -wal, -shm) carry
    # not-yet-checkpointed writes; the database is only complete with them.
    for sibling in sorted(old_db.parent.glob(old_db.name + "-*")):
        shutil.move(str(sibling), str(new_db.parent / sibling.name))
    shutil.move(str(old_db), str(new_db))
    logger.info("database_migrated", src=str(old_db), dest=str(new_db))
    # Tidy the legacy dir if the database was its only content.
    with contextlib.suppress(OSError):
        old_db.parent.rmdir()
    return True
