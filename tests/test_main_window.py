"""Characterization tests for MainWindow playback mutual exclusivity."""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEvent, QSettings, Qt
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


# --- Native menu bar -------------------------------------------------------------


def test_menu_bar_has_expected_menus(main_window):
    titles = [a.text() for a in main_window.menuBar().actions()]
    assert titles == [
        "File",
        "Playback",
        "View",
        "Scenes",
        "Playlists",
        "Soundboards",
        "Help",
    ]


def test_dynamic_menus_are_populated_at_startup(main_window):
    # The macOS native menu bar hides empty menus: if these only filled on
    # aboutToShow, the Scenes/Playlists/Soundboards titles would never show.
    assert main_window.scenes_menu.actions()
    assert main_window.playlists_menu.actions()
    assert main_window.soundboards_menu.actions()


def test_scenes_menu_empty_shows_disabled_placeholder(main_window):
    main_window._rebuild_scenes_menu()
    actions = main_window.scenes_menu.actions()
    assert [a.text() for a in actions] == ["No Scenes"]
    assert not actions[0].isEnabled()


def test_scenes_menu_lists_scenes_and_checks_playing(main_window, monkeypatch):
    from app.database import Scene

    id_a = main_window.db.add_scene(Scene(title="Ambush"))
    id_b = main_window.db.add_scene(Scene(title="Tavern"))
    main_window._current_playing_type = "scene"
    main_window._current_scene_id = id_b
    main_window._rebuild_scenes_menu()
    actions = main_window.scenes_menu.actions()
    # Newest-first: add_scene inserts at position 0, same as the sidebar.
    assert [a.text() for a in actions] == ["Tavern", "Ambush"]
    assert [a.text() for a in actions if a.isChecked()] == ["Tavern"]

    # Triggering an entry switches to the Scenes tab and selects the scene.
    seen = []
    main_window.tab_widget.setCurrentWidget(main_window.library_widget)
    monkeypatch.setattr(
        main_window.scenes_widget, "select_scene", lambda i: seen.append(i)
    )
    actions[1].trigger()
    assert main_window.tab_widget.currentWidget() is main_window.scenes_widget
    assert seen == [id_a]


def test_playlists_menu_lists_playlists_and_checks_playing(main_window):
    from app.database import Playlist as PlaylistModel

    id_a = main_window.db.add_playlist(PlaylistModel(name="Battle Mix"))
    main_window._current_playing_type = "playlist"
    main_window._current_playlist_playing_id = id_a
    main_window._rebuild_playlists_menu()
    actions = main_window.playlists_menu.actions()
    assert [a.text() for a in actions] == ["Battle Mix"]
    assert actions[0].isChecked()


def test_soundboards_menu_checks_open_board_and_opens_on_trigger(main_window):
    from app.database import Soundboard

    board_id = main_window.db.add_soundboard(Soundboard(name="SFX"))
    main_window._rebuild_soundboards_menu()
    actions = main_window.soundboards_menu.actions()
    assert [a.text() for a in actions] == ["SFX"]

    main_window.soundboard_dock.set_collapsed(True)
    actions[0].trigger()
    assert main_window.soundboard_dock.collapsed is False
    assert main_window.soundboard_content.current_board_id() == board_id

    # Now that the board is the open one, the rebuilt menu checks it.
    main_window._rebuild_soundboards_menu()
    assert main_window.soundboards_menu.actions()[0].isChecked()


def test_show_scene_switches_tab_and_selects(main_window, monkeypatch):
    seen = []
    monkeypatch.setattr(
        main_window.scenes_widget, "select_scene", lambda i: seen.append(i)
    )
    main_window.tab_widget.setCurrentWidget(main_window.library_widget)
    main_window.show_scene(42)
    assert main_window.tab_widget.currentWidget() is main_window.scenes_widget
    assert seen == [42]


def test_show_playlist_switches_tab_and_selects(main_window, monkeypatch):
    seen = []
    monkeypatch.setattr(
        main_window.playlists_widget, "select_playlist", lambda i: seen.append(i)
    )
    main_window.show_playlist(7)
    assert main_window.tab_widget.currentWidget() is main_window.playlists_widget
    assert seen == [7]


def test_import_files_switches_to_library_and_opens_picker(main_window, monkeypatch):
    calls = _record(monkeypatch, main_window.library_widget, "add_files")
    main_window.tab_widget.setCurrentWidget(main_window.scenes_widget)
    main_window.import_files()
    assert main_window.tab_widget.currentWidget() is main_window.library_widget
    assert len(calls) == 1


def test_import_folder_switches_to_library_and_opens_picker(main_window, monkeypatch):
    calls = _record(monkeypatch, main_window.library_widget, "add_folder")
    main_window.tab_widget.setCurrentWidget(main_window.scenes_widget)
    main_window.import_folder()
    assert main_window.tab_widget.currentWidget() is main_window.library_widget
    assert len(calls) == 1


def test_stop_all_playback_stops_scenes_playlists_and_soundboard(
    main_window, monkeypatch
):
    s = _record(monkeypatch, main_window.scenes_widget, "stop_all_playback")
    p = _record(monkeypatch, main_window.playlists_widget, "stop_all_playback")
    b = _record(monkeypatch, main_window.soundboard_player, "stop")
    main_window.stop_all_playback()
    assert len(s) == 1 and len(p) == 1 and len(b) == 1


def test_view_menu_soundboard_action_tracks_and_toggles_collapse(main_window):
    main_window.soundboard_dock.set_collapsed(True)
    main_window._sync_view_menu()
    assert main_window._soundboard_view_action.isChecked() is False
    # trigger() flips the checkable state to True, expanding the dock.
    main_window._soundboard_view_action.trigger()
    assert main_window.soundboard_dock.collapsed is False
    main_window._sync_view_menu()
    assert main_window._soundboard_view_action.isChecked() is True


def test_restart_remote_server_applies_new_settings(main_window):
    # conftest disables remote, so the window starts without a server.
    assert main_window.remote_server is None
    settings = QSettings()
    settings.beginGroup("remote")
    settings.setValue("enabled", True)
    settings.setValue("port", 0)  # ephemeral: don't depend on 8765 being free
    settings.endGroup()
    try:
        main_window._restart_remote_server()
        assert main_window.remote_server is not None
        assert main_window.remote_server.port > 0
    finally:
        settings.beginGroup("remote")
        settings.setValue("enabled", False)
        settings.endGroup()
        main_window._restart_remote_server()
    assert main_window.remote_server is None


# --- Database backup / restore --------------------------------------------------


def test_file_menu_has_backup_and_restore(main_window):
    file_menu = main_window.menuBar().actions()[0].menu()
    texts = [a.text() for a in file_menu.actions()]
    assert "Back Up Database…" in texts
    assert "Restore Database…" in texts


def test_confirmed_restore_swaps_db_and_relaunches(main_window, monkeypatch):
    import app.main_window as mw
    from app.database import DatabaseConnection as DB

    # Build a distinguishable backup: one audio file vs the empty live DB.
    backup_path = str(Path(main_window.db.db_path).parent / "backup.db")
    source = DB(str(Path(main_window.db.db_path).parent / "source.db"))
    source.connect()
    from app.database import AudioFile

    source.add_audio_file(AudioFile(file_path="/music/a.mp3", title="A"))
    source.backup_to(backup_path)
    source.close()

    relaunches = []
    monkeypatch.setattr(
        mw.QProcess,
        "startDetached",
        staticmethod(lambda *args: relaunches.append(args)),
    )
    main_window._pending_restore = backup_path
    main_window.close()

    live_path = Path(main_window.db.db_path)
    check = DB(str(live_path))
    check.connect()
    try:
        assert len(check.get_all_audio_files()) == 1
    finally:
        check.close()
    safety_copies = list(live_path.parent.glob("*pre-restore*"))
    assert len(safety_copies) == 1
    assert len(relaunches) == 1


def test_plain_close_does_not_restore_or_relaunch(main_window, monkeypatch):
    import app.main_window as mw

    relaunches = []
    monkeypatch.setattr(
        mw.QProcess,
        "startDetached",
        staticmethod(lambda *args: relaunches.append(args)),
    )
    main_window.close()
    assert relaunches == []
    assert not list(Path(main_window.db.db_path).parent.glob("*pre-restore*"))
