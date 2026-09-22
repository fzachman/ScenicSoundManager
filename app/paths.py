"""Filesystem locations for user data and logs (stdlib-only, no Qt).

No Qt on purpose: configure_logging() needs LOG_DIR before the QApplication
exists, and QStandardPaths would append an app-name subfolder that doesn't
match the macOS layout existing installs already use.
"""

import os
import sys
from pathlib import Path

# Renamed from the legacy "SoundManager" folder in 2026-07 alongside the
# QSettings org rename (one-shot migration since removed; see commit 6458079
# if a future rename needs the pattern).
APP_DIR_NAME = "ScenicSound"
DB_FILENAME = "soundmanager.db"


def data_dir(platform: str = sys.platform) -> Path:
    """Home of the SQLite database (plus its lock file and backups)."""
    home = Path.home()
    if platform == "darwin":
        # Beta users' databases live here: moving it needs a migration.
        return home / "Library" / "Application Support" / APP_DIR_NAME
    if platform == "win32":
        # Local, not Roaming: the library stores absolute paths to audio
        # files on this machine, so it is meaningless on another one.
        return _env_dir("LOCALAPPDATA", home / "AppData" / "Local") / APP_DIR_NAME
    return _env_dir("XDG_DATA_HOME", home / ".local" / "share") / APP_DIR_NAME


def log_dir(platform: str = sys.platform) -> Path:
    """Home of the rotated log files."""
    home = Path.home()
    if platform == "darwin":
        return home / "Library" / "Logs" / APP_DIR_NAME
    if platform == "win32":
        return (
            _env_dir("LOCALAPPDATA", home / "AppData" / "Local") / APP_DIR_NAME / "Logs"
        )
    return _env_dir("XDG_STATE_HOME", home / ".local" / "state") / APP_DIR_NAME


def _env_dir(name: str, fallback: Path) -> Path:
    """The directory named by env var ``name``, or ``fallback`` if unset/empty."""
    value = os.environ.get(name)
    return Path(value) if value else fallback


DATA_DIR = data_dir()
LOG_DIR = log_dir()
