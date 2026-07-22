"""Database backup/restore file operations (File menu).

Backing up goes through SQLite's online-backup API (see
``DatabaseConnection.backup_to``), so it is safe while the app is running.
Restoring swaps database FILES and therefore must only run after the live
connection is closed — MainWindow performs it during shutdown and relaunches.
"""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from .. import APP_DISPLAY_NAME
from ..shared.logging import get_logger

logger = get_logger(__name__)

# Tables any real backup must contain; their absence means the file is a
# SQLite database but not ours.
REQUIRED_TABLES = {"audio_files", "tags", "scenes", "playlists", "soundboards"}


def validate_backup(path: str) -> str | None:
    """Check that ``path`` is a restorable backup.

    Returns None when valid, else a short human-readable reason.
    """
    if not Path(path).is_file():
        return "The file does not exist."
    try:
        # mode=ro so validation can never touch the file.
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if result is None or result[0] != "ok":
                return "The database failed its integrity check."
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            if REQUIRED_TABLES - tables:
                return f"This is not a {APP_DISPLAY_NAME} database."
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return "This is not a valid database file."
    return None


def swap_database(current_db: Path, backup: Path) -> Path:
    """Replace ``current_db`` with a copy of ``backup``.

    The current database is renamed to a timestamped ``-pre-restore-`` file
    beside it (never deleted); the backup file itself is left untouched.
    Returns the safety-copy path. Caller must have closed the database first.
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safety_copy = current_db.with_name(
        f"{current_db.stem}-pre-restore-{timestamp}{current_db.suffix}"
    )
    if current_db.exists():
        current_db.rename(safety_copy)
    shutil.copy2(backup, current_db)
    logger.info(
        "database_restored",
        backup=str(backup),
        safety_copy=str(safety_copy),
    )
    return safety_copy
