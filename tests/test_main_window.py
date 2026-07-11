"""Characterization tests for MainWindow playback mutual exclusivity."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QLineEdit,
    QPushButton,
    QSlider,
    QWidget,
)

import app.main_window as main_window_module
from app.audio import TRANSITION_FADE_MS
from app.database import DatabaseConnection, Playlist


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
    # The teardown of the losing side must fade (crossfade), not hard-cut.
    stopped = []
    monkeypatch.setattr(
        main_window.scenes_widget,
        "stop_all_playback",
        lambda fade_ms=0: stopped.append(fade_ms),
    )
    main_window.scenes_widget.playback_state_changed.emit(3, "Tavern", True)
    main_window.playlists_widget.playback_state_changed.emit(7, "Battle Mix", True)
    qapp.processEvents()
    assert stopped == [TRANSITION_FADE_MS]
    assert main_window._current_playing_type == "playlist"
    assert main_window.current_scene_btn.text() == "Playlist: Battle Mix"


def test_scene_start_stops_active_playlist(main_window, qapp, monkeypatch):
    stopped = []
    monkeypatch.setattr(
        main_window.playlists_widget,
        "stop_all_playback",
        lambda fade_ms=0: stopped.append(fade_ms),
    )
    main_window.playlists_widget.playback_state_changed.emit(7, "Battle Mix", True)
    main_window.scenes_widget.playback_state_changed.emit(3, "Tavern", True)
    qapp.processEvents()
    assert stopped == [TRANSITION_FADE_MS]
    assert main_window._current_playing_type == "scene"
    assert main_window.current_scene_btn.text() == "Scene: Tavern"


def test_playlist_start_stops_paused_scene(main_window, qapp, monkeypatch):
    # A PAUSED scene has _current_playing_type None but still holds resumable
    # players — starting a playlist must tear it down too (loophole fix).
    editor = main_window.scenes_widget.scene_editor
    editor._active_scene_id = 3
    editor._scene_playing = False
    stopped = []
    monkeypatch.setattr(
        main_window.scenes_widget,
        "stop_all_playback",
        lambda fade_ms=0: stopped.append(fade_ms),
    )
    main_window.playlists_widget.playback_state_changed.emit(7, "Battle Mix", True)
    qapp.processEvents()
    assert stopped == [TRANSITION_FADE_MS]
    assert main_window._current_playing_type == "playlist"


def test_scene_start_stops_paused_playlist(main_window, qapp, monkeypatch):
    editor = main_window.playlists_widget.playlist_editor
    editor._active_playlist = Playlist(id=7, name="Battle Mix")
    editor._is_playing = False
    stopped = []
    monkeypatch.setattr(
        main_window.playlists_widget,
        "stop_all_playback",
        lambda fade_ms=0: stopped.append(fade_ms),
    )
    main_window.scenes_widget.playback_state_changed.emit(3, "Tavern", True)
    qapp.processEvents()
    assert stopped == [TRANSITION_FADE_MS]
    assert main_window._current_playing_type == "scene"


def test_scene_stop_emits_only_when_active(main_window, qapp):
    # stop_all_playback on an idle scene editor must be silent (it is now
    # called unconditionally on every playlist start); once a scene is active
    # (playing or paused) the same call must broadcast exactly one stop.
    emissions = []
    main_window.scenes_widget.playback_state_changed.connect(
        lambda *args: emissions.append(args)
    )
    main_window.scenes_widget.stop_all_playback()
    assert emissions == []

    editor = main_window.scenes_widget.scene_editor
    editor._active_scene_id = 3
    editor._scene_playing = False  # paused still counts as active
    main_window.scenes_widget.stop_all_playback()
    assert emissions == [(None, None, False)]


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


# --- Keyboard shortcut dispatch -------------------------------------------------


def _record(monkeypatch, obj, name):
    calls = []
    monkeypatch.setattr(obj, name, lambda *a, **k: calls.append((a, k)))
    return calls


# Space (toggle play / pause)


def test_space_pauses_active_scene(main_window, monkeypatch):
    calls = _record(monkeypatch, main_window.scenes_widget, "pause_active")
    main_window._current_playing_type = "scene"
    main_window.toggle_play_pause()
    assert len(calls) == 1


def test_space_pauses_active_playlist(main_window, monkeypatch):
    calls = _record(monkeypatch, main_window.playlists_widget, "pause_active")
    main_window._current_playing_type = "playlist"
    main_window.toggle_play_pause()
    assert len(calls) == 1


def test_space_idle_starts_open_scene_on_scenes_tab(main_window, monkeypatch):
    calls = _record(monkeypatch, main_window.scenes_widget, "toggle_playback")
    main_window._current_playing_type = None
    main_window.tab_widget.setCurrentWidget(main_window.scenes_widget)
    main_window.toggle_play_pause()
    assert len(calls) == 1


def test_space_idle_starts_open_playlist_on_playlists_tab(main_window, monkeypatch):
    calls = _record(monkeypatch, main_window.playlists_widget, "toggle_playback")
    main_window._current_playing_type = None
    main_window.tab_widget.setCurrentWidget(main_window.playlists_widget)
    main_window.toggle_play_pause()
    assert len(calls) == 1


def test_space_idle_on_library_tab_is_noop(main_window, monkeypatch):
    s = _record(monkeypatch, main_window.scenes_widget, "toggle_playback")
    p = _record(monkeypatch, main_window.playlists_widget, "toggle_playback")
    main_window._current_playing_type = None
    main_window.tab_widget.setCurrentWidget(main_window.library_widget)
    main_window.toggle_play_pause()
    assert s == [] and p == []


# Right (next track)


def test_right_advances_playing_playlist(main_window, monkeypatch):
    calls = _record(monkeypatch, main_window.playlists_widget, "next_track")
    main_window._current_playing_type = "playlist"
    main_window.next_track()
    assert len(calls) == 1


def test_right_noop_when_scene_playing(main_window, monkeypatch):
    calls = _record(monkeypatch, main_window.playlists_widget, "next_track")
    main_window._current_playing_type = "scene"
    main_window.next_track()
    assert calls == []


def test_right_noop_when_idle(main_window, monkeypatch):
    calls = _record(monkeypatch, main_window.playlists_widget, "next_track")
    main_window._current_playing_type = None
    main_window.next_track()
    assert calls == []


# Ctrl+Left / Ctrl+Right (step scene / playlist, inherit play state)


def test_ctrl_right_selects_next_without_playing_when_idle(main_window, monkeypatch):
    # select_relative returns a truthy id; the "inherit play" branch is gated on
    # play state, which is idle here.
    monkeypatch.setattr(main_window.scenes_widget, "select_relative", lambda d: 5)
    played = _record(monkeypatch, main_window.scenes_widget, "play_current")
    main_window._current_playing_type = None
    main_window.tab_widget.setCurrentWidget(main_window.scenes_widget)
    main_window._shortcut_step_item(1)
    assert played == []  # idle -> selection only, no playback


def test_ctrl_right_plays_next_when_something_was_playing(main_window, monkeypatch):
    seen = []
    monkeypatch.setattr(
        main_window.scenes_widget, "select_relative", lambda d: seen.append(d) or 5
    )
    played = _record(monkeypatch, main_window.scenes_widget, "play_current")
    main_window._current_playing_type = "scene"
    main_window.tab_widget.setCurrentWidget(main_window.scenes_widget)
    main_window._shortcut_step_item(1)
    assert seen == [1]
    assert len(played) == 1


def test_ctrl_left_steps_backward(main_window, monkeypatch):
    seen = []
    monkeypatch.setattr(
        main_window.playlists_widget, "select_relative", lambda d: seen.append(d) or 9
    )
    main_window._current_playing_type = None
    main_window.tab_widget.setCurrentWidget(main_window.playlists_widget)
    main_window._shortcut_step_item(-1)
    assert seen == [-1]


def test_step_at_list_edge_does_not_play(main_window, monkeypatch):
    # select_relative returns None at the edge -> no playback even when playing.
    monkeypatch.setattr(main_window.scenes_widget, "select_relative", lambda d: None)
    played = _record(monkeypatch, main_window.scenes_widget, "play_current")
    main_window._current_playing_type = "scene"
    main_window.tab_widget.setCurrentWidget(main_window.scenes_widget)
    main_window._shortcut_step_item(1)
    assert played == []


def test_step_on_library_tab_is_noop(main_window, monkeypatch):
    s = _record(monkeypatch, main_window.scenes_widget, "select_relative")
    p = _record(monkeypatch, main_window.playlists_widget, "select_relative")
    main_window.tab_widget.setCurrentWidget(main_window.library_widget)
    main_window._shortcut_step_item(1)
    assert s == [] and p == []


NO_MOD = Qt.KeyboardModifier.NoModifier
CTRL = Qt.KeyboardModifier.ControlModifier  # ⌘ on macOS
KEYPAD = Qt.KeyboardModifier.KeypadModifier  # macOS sets this on arrow keys


def _key_event(key, modifiers=NO_MOD, autorepeat=False):
    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers, "", autorepeat, 1)


# _handle_transport_key: dispatch + focus exemptions


def test_space_toggles_on_neutral_focus(main_window, monkeypatch, qapp):
    calls = _record(monkeypatch, main_window, "toggle_play_pause")
    handled = main_window._handle_transport_key(Qt.Key.Key_Space, NO_MOD, QWidget())
    assert handled is True
    assert len(calls) == 1


def test_space_yields_to_button(main_window, monkeypatch, qapp):
    calls = _record(monkeypatch, main_window, "toggle_play_pause")
    handled = main_window._handle_transport_key(Qt.Key.Key_Space, NO_MOD, QPushButton())
    assert handled is False  # button keeps Space (activates)
    assert calls == []


def test_space_yields_to_text_input(main_window, monkeypatch, qapp):
    calls = _record(monkeypatch, main_window, "toggle_play_pause")
    handled = main_window._handle_transport_key(Qt.Key.Key_Space, NO_MOD, QLineEdit())
    assert handled is False
    assert calls == []


def test_right_advances_on_neutral_focus(main_window, monkeypatch, qapp):
    calls = _record(monkeypatch, main_window, "next_track")
    handled = main_window._handle_transport_key(Qt.Key.Key_Right, NO_MOD, QWidget())
    assert handled is True
    assert len(calls) == 1


def test_right_yields_to_slider(main_window, monkeypatch, qapp):
    # A focused volume/scrubber slider must keep Right to nudge its value.
    calls = _record(monkeypatch, main_window, "next_track")
    handled = main_window._handle_transport_key(Qt.Key.Key_Right, NO_MOD, QSlider())
    assert handled is False
    assert calls == []


def test_right_yields_to_text_input(main_window, monkeypatch, qapp):
    calls = _record(monkeypatch, main_window, "next_track")
    handled = main_window._handle_transport_key(Qt.Key.Key_Right, NO_MOD, QLineEdit())
    assert handled is False
    assert calls == []


def test_ctrl_right_steps_next(main_window, monkeypatch, qapp):
    seen = []
    monkeypatch.setattr(main_window, "_shortcut_step_item", lambda d: seen.append(d))
    handled = main_window._handle_transport_key(Qt.Key.Key_Right, CTRL, QWidget())
    assert handled is True
    assert seen == [1]


def test_ctrl_left_steps_prev(main_window, monkeypatch, qapp):
    seen = []
    monkeypatch.setattr(main_window, "_shortcut_step_item", lambda d: seen.append(d))
    handled = main_window._handle_transport_key(Qt.Key.Key_Left, CTRL, QWidget())
    assert handled is True
    assert seen == [-1]


def test_ctrl_right_yields_to_text_input(main_window, monkeypatch, qapp):
    # Ctrl+Right is word-navigation inside a text field.
    seen = []
    monkeypatch.setattr(main_window, "_shortcut_step_item", lambda d: seen.append(d))
    handled = main_window._handle_transport_key(Qt.Key.Key_Right, CTRL, QLineEdit())
    assert handled is False
    assert seen == []


def test_plain_left_is_not_handled(main_window, qapp):
    # Previous-track was deferred: bare Left does nothing.
    assert (
        main_window._handle_transport_key(Qt.Key.Key_Left, NO_MOD, QWidget()) is False
    )


def test_unrelated_key_is_not_handled(main_window, qapp):
    assert main_window._handle_transport_key(Qt.Key.Key_A, NO_MOD, QWidget()) is False


# macOS tags arrow keys with KeypadModifier — it must be ignored, or the arrows
# appear dead (Space, which has no keypad flag, works regardless).


def test_right_with_keypad_modifier_still_advances(main_window, monkeypatch, qapp):
    calls = _record(monkeypatch, main_window, "next_track")
    handled = main_window._handle_transport_key(
        Qt.Key.Key_Right, NO_MOD | KEYPAD, QWidget()
    )
    assert handled is True
    assert len(calls) == 1


def test_ctrl_right_with_keypad_modifier_still_steps(main_window, monkeypatch, qapp):
    seen = []
    monkeypatch.setattr(main_window, "_shortcut_step_item", lambda d: seen.append(d))
    handled = main_window._handle_transport_key(
        Qt.Key.Key_Right, CTRL | KEYPAD, QWidget()
    )
    assert handled is True
    assert seen == [1]


def test_ctrl_left_with_keypad_modifier_still_steps(main_window, monkeypatch, qapp):
    seen = []
    monkeypatch.setattr(main_window, "_shortcut_step_item", lambda d: seen.append(d))
    handled = main_window._handle_transport_key(
        Qt.Key.Key_Left, CTRL | KEYPAD, QWidget()
    )
    assert handled is True
    assert seen == [-1]


def test_event_filter_ignores_autorepeat(main_window, monkeypatch):
    calls = _record(monkeypatch, main_window, "toggle_play_pause")
    main_window.eventFilter(main_window, _key_event(Qt.Key.Key_Space, autorepeat=True))
    assert calls == []


# Tab focus: returning to a Scenes/Playlists tab focuses its list (so the order
# button doesn't hold focus and swallow Space).


def test_switch_to_scenes_tab_focuses_list(main_window, qapp, monkeypatch):
    calls = _record(monkeypatch, main_window.scenes_widget, "focus_list")
    main_window.tab_widget.setCurrentWidget(main_window.library_widget)
    qapp.processEvents()
    calls.clear()
    main_window.tab_widget.setCurrentWidget(main_window.scenes_widget)
    qapp.processEvents()  # fire the deferred singleShot
    assert len(calls) == 1


def test_switch_to_playlists_tab_focuses_list(main_window, qapp, monkeypatch):
    calls = _record(monkeypatch, main_window.playlists_widget, "focus_list")
    main_window.tab_widget.setCurrentWidget(main_window.library_widget)
    qapp.processEvents()
    calls.clear()
    main_window.tab_widget.setCurrentWidget(main_window.playlists_widget)
    qapp.processEvents()
    assert len(calls) == 1


def test_switch_to_library_does_not_focus_play_lists(main_window, qapp, monkeypatch):
    s = _record(monkeypatch, main_window.scenes_widget, "focus_list")
    p = _record(monkeypatch, main_window.playlists_widget, "focus_list")
    main_window.tab_widget.setCurrentWidget(main_window.scenes_widget)
    qapp.processEvents()
    s.clear()
    p.clear()
    main_window.tab_widget.setCurrentWidget(main_window.library_widget)
    qapp.processEvents()
    assert s == [] and p == []
