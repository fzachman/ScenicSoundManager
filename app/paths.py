"""Filesystem locations for user data (stdlib-only, no Qt)."""

from pathlib import Path

APP_SUPPORT = Path.home() / "Library" / "Application Support"

# Data home (SQLite database). Renamed from the legacy "SoundManager" folder
# in 2026-07 alongside the QSettings org rename (one-shot migration since
# removed; see commit 6458079 if a future rename needs the pattern).
DATA_DIR = APP_SUPPORT / "ScenicSound"
DB_FILENAME = "soundmanager.db"
