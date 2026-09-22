"""Tests for the per-platform data and log locations (app/paths.py).

Every platform is exercised on any host by passing ``platform`` explicitly.
The macOS paths are pinned literally: beta users' databases and logs live
there, so any change orphans existing installs.
"""

from pathlib import Path

import pytest

import app.shared.logging as app_logging
from app import paths


@pytest.fixture
def home(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    return fake_home


def test_macos_data_dir_is_pinned(home):
    assert paths.data_dir("darwin") == (
        home / "Library" / "Application Support" / "ScenicSound"
    )


def test_macos_log_dir_is_pinned(home):
    assert paths.log_dir("darwin") == home / "Library" / "Logs" / "ScenicSound"


def test_macos_ignores_other_platforms_env_vars(home, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", "/elsewhere/Local")
    monkeypatch.setenv("XDG_DATA_HOME", "/elsewhere/share")
    monkeypatch.setenv("XDG_STATE_HOME", "/elsewhere/state")
    assert paths.data_dir("darwin").is_relative_to(home)
    assert paths.log_dir("darwin").is_relative_to(home)


def test_windows_uses_local_appdata(home, monkeypatch, tmp_path):
    local = tmp_path / "AppData-Local"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    assert paths.data_dir("win32") == local / "ScenicSound"
    assert paths.log_dir("win32") == local / "ScenicSound" / "Logs"


@pytest.mark.parametrize("value", [None, ""])
def test_windows_falls_back_when_local_appdata_missing(home, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
    else:
        monkeypatch.setenv("LOCALAPPDATA", value)
    local = home / "AppData" / "Local"
    assert paths.data_dir("win32") == local / "ScenicSound"
    assert paths.log_dir("win32") == local / "ScenicSound" / "Logs"


def test_other_platforms_use_xdg_dirs(home, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert paths.data_dir("linux") == tmp_path / "share" / "ScenicSound"
    assert paths.log_dir("linux") == tmp_path / "state" / "ScenicSound"


def test_other_platforms_fall_back_to_xdg_defaults(home, monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    assert paths.data_dir("linux") == home / ".local" / "share" / "ScenicSound"
    assert paths.log_dir("linux") == home / ".local" / "state" / "ScenicSound"


def test_constants_resolve_for_the_running_platform():
    assert paths.data_dir() == paths.DATA_DIR
    assert paths.log_dir() == paths.LOG_DIR
    assert app_logging.LOG_DIR == paths.LOG_DIR
