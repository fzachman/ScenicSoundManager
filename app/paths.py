"""Filesystem locations for user data (stdlib-only, no Qt)."""

from pathlib import Path

APP_SUPPORT = Path.home() / "Library" / "Application Support"

# Data home (SQLite database). Renamed from the legacy "SoundManager" folder
# in 2026-07 alongside the QSettings org rename; app/migrations.py moves the
# database over on startup.
DATA_DIR = APP_SUPPORT / "ScenicSound"
LEGACY_DATA_DIR = APP_SUPPORT / "SoundManager"
DB_FILENAME = "soundmanager.db"
