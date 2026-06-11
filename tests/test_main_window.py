"""Characterization tests for MainWindow playback mutual exclusivity."""

import os
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

from app.database import DatabaseConnection
import app.main_window as main_window_module


@pytest.fixture(scope="session")
def qapp():
    QCoreApplication.setOrganizationName("SoundManagerTests")
    QCoreApplication.setApplicationName("SoundManagerTests")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(
        main_window_module, "DatabaseConnection", lambda: DatabaseConnection(db_path)
    )
    window = main_window_module.MainWindow()
    yield window
    window.db.close()


def test_window_constructs(main_window):
    assert main_window.db is not None


def test_scene_playing_sets_state_and_indicator(main_window, qapp):
    main_window.scenes_widget.playback_state_changed.emit(3, "Tavern", True)
    qapp.processEvents()
    assert main_window._current_playing_type == "scene"
    assert main_window.current_scene_btn.text() == "Scene: Tavern"
    assert not main_window.currently_playing_widget.isHidden()


def test_scene_stop_clears_state(main_window, qapp):
    main_window.scenes_widget.playback_state_changed.emit(3, "Tavern", True)
    main_window.scenes_widget.playback_state_changed.emit(3, "Tavern", False)
    qapp.processEvents()
    assert main_window._current_playing_type is None
    assert main_window.currently_playing_widget.isHidden()


def test_playlist_start_stops_active_scene(main_window, qapp, monkeypatch):
    stopped = []
    monkeypatch.setattr(
        main_window.scenes_widget, "stop_all_playback", lambda: stopped.append(True)
    )
    main_window.scenes_widget.playback_state_changed.emit(3, "Tavern", True)
    main_window.playlists_widget.playback_state_changed.emit(7, "Battle Mix", True)
    qapp.processEvents()
    assert stopped == [True]
    assert main_window._current_playing_type == "playlist"
    assert main_window.current_scene_btn.text() == "Playlist: Battle Mix"


def test_scene_start_stops_active_playlist(main_window, qapp, monkeypatch):
    stopped = []
    monkeypatch.setattr(
        main_window.playlists_widget, "stop_all_playback", lambda: stopped.append(True)
    )
    main_window.playlists_widget.playback_state_changed.emit(7, "Battle Mix", True)
    main_window.scenes_widget.playback_state_changed.emit(3, "Tavern", True)
    qapp.processEvents()
    assert stopped == [True]
    assert main_window._current_playing_type == "scene"
    assert main_window.current_scene_btn.text() == "Scene: Tavern"


def test_stale_playlist_stop_does_not_clear_scene_state(main_window, qapp):
    # A playlist's stop signal arriving while a scene is active must not
    # clear the scene's now-playing state.
    main_window.scenes_widget.playback_state_changed.emit(3, "Tavern", True)
    main_window.playlists_widget.playback_state_changed.emit(7, None, False)
    qapp.processEvents()
    assert main_window._current_playing_type == "scene"
    assert not main_window.currently_playing_widget.isHidden()


def test_untitled_scene_fallback_label(main_window, qapp):
    main_window.scenes_widget.playback_state_changed.emit(3, None, True)
    qapp.processEvents()
    assert main_window.current_scene_btn.text() == "Scene: Untitled Scene"
