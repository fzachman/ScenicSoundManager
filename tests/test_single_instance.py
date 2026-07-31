"""Tests for the single-instance lock (app/single_instance.py)."""

import pytest

import app.paths
from app.single_instance import LOCK_FILENAME, acquire_instance_lock


@pytest.fixture
def lock_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(app.paths, "DATA_DIR", tmp_path)
    return tmp_path


def test_first_instance_acquires(qapp, lock_dir):
    lock = acquire_instance_lock(timeout_ms=50)
    assert lock is not None
    assert (lock_dir / LOCK_FILENAME).exists()
    lock.unlock()


def test_second_instance_refused_while_held(qapp, lock_dir):
    first = acquire_instance_lock(timeout_ms=50)
    assert first is not None
    second = acquire_instance_lock(timeout_ms=50)
    assert second is None
    first.unlock()


def test_lock_reacquirable_after_release(qapp, lock_dir):
    first = acquire_instance_lock(timeout_ms=50)
    assert first is not None
    first.unlock()
    second = acquire_instance_lock(timeout_ms=50)
    assert second is not None
    second.unlock()


def test_stale_lock_from_dead_process_is_reclaimed(qapp, lock_dir):
    # QLockFile's on-disk format: pid, appname, hostname (empty hostname =
    # this machine; a FOREIGN hostname is never reclaimed since the PID
    # can't be checked). PID 4000000 is beyond macOS's pid range, so the
    # owner is definitely dead.
    (lock_dir / LOCK_FILENAME).write_text("4000000\nSoundManager\n\n")
    lock = acquire_instance_lock(timeout_ms=50)
    assert lock is not None
    lock.unlock()


def test_creates_data_dir_if_missing(qapp, lock_dir, monkeypatch):
    missing = lock_dir / "not-yet-created"
    monkeypatch.setattr(app.paths, "DATA_DIR", missing)
    lock = acquire_instance_lock(timeout_ms=50)
    assert lock is not None
    assert missing.is_dir()
    lock.unlock()
