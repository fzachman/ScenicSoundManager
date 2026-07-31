"""Single-instance guard: a QLockFile next to the database.

Two instances sharing the database is unsafe around schema upgrades: the
``user_version`` downgrade guard only runs at connect(), so an
already-running older version keeps writing after a newer one migrates
the file underneath it, and the pre-upgrade backup could snapshot the
database mid-write. Simplest fix is to never allow two instances.
"""

from PyQt6.QtCore import QLockFile

from . import paths

LOCK_FILENAME = "soundmanager.lock"


def acquire_instance_lock(timeout_ms: int = 2000) -> QLockFile | None:
    """Try to become the single running instance.

    Returns the held lock — keep a reference for the app's lifetime — or
    None if another live instance holds it. Locks left by crashed
    processes are detected (dead PID) and reclaimed automatically.

    The default timeout covers the restore-database relaunch: the old
    instance may still be shutting down when the relaunched process gets
    here, so we wait briefly rather than refusing.
    """
    paths.DATA_DIR.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(paths.DATA_DIR / LOCK_FILENAME))
    # Age-based staleness would let a second instance steal the lock from
    # a healthy long-running app; disable it. Dead owners are still
    # detected by PID.
    lock.setStaleLockTime(0)
    if lock.tryLock(timeout_ms):
        return lock
    return None
