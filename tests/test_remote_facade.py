"""Tests for RemoteControlFacade — the remote-command → UI seam (Plan 007)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import app.main_window as main_window_module
from app.database import DatabaseConnection, Playlist, Scene
from app.remote import RemoteError


@pytest.fixture
def main_window(qapp, tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(
        main_window_module, "DatabaseConnection", lambda: DatabaseConnection(db_path)
    )
    window = main_window_module.MainWindow()
    yield window
    window.db.close()


@pytest.fixture
def facade(main_window):
    return main_window.remote_facade


def _record(monkeypatch, obj, name):
    calls = []
    monkeypatch.setattr(obj, name, lambda *a, **k: calls.append(a))
    return calls


# --- queries ---------------------------------------------------------------


def test_get_scenes_maps_title_to_name(main_window, facade):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    assert {"id": scene_id, "name": "Tavern"} in facade.get_scenes()


def test_get_playlists_returns_id_and_name(main_window, facade):
    playlist_id = main_window.db.add_playlist(Playlist(name="Battle Mix"))
    assert {"id": playlist_id, "name": "Battle Mix"} in facade.get_playlists()


def test_get_state_idle(main_window, facade):
    state = facade.get_state()
    assert state["playing"] is None
    assert state["master_volume"] == main_window.audio_engine.master_volume


def test_get_state_reflects_playing_scene(main_window, facade, qapp):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    main_window.scenes_widget.playback_state_changed.emit(scene_id, "Tavern", True)
    qapp.processEvents()
    assert facade.get_state()["playing"] == {
        "type": "scene",
        "id": scene_id,
        "name": "Tavern",
    }


def test_get_state_reflects_playing_playlist(main_window, facade, qapp):
    playlist_id = main_window.db.add_playlist(Playlist(name="Battle Mix"))
    main_window.playlists_widget.playback_state_changed.emit(
        playlist_id, "Battle Mix", True
    )
    qapp.processEvents()
    assert facade.get_state()["playing"] == {
        "type": "playlist",
        "id": playlist_id,
        "name": "Battle Mix",
    }


def test_get_state_name_is_none_for_id_missing_from_db(main_window, facade, qapp):
    # Defensive: playing id not resolvable (e.g. deleted mid-playback).
    main_window.scenes_widget.playback_state_changed.emit(999, "Ghost", True)
    qapp.processEvents()
    playing = facade.get_state()["playing"]
    assert playing["id"] == 999
    assert playing["name"] is None


# --- play_scene / play_playlist ---------------------------------------------


def test_play_scene_switches_tab_selects_and_plays(main_window, facade, monkeypatch):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    selected = _record(monkeypatch, main_window.scenes_widget, "select_scene")
    played = _record(monkeypatch, main_window.scenes_widget, "play_current")
    facade.play_scene(scene_id)
    assert main_window.tab_widget.currentWidget() is main_window.scenes_widget
    assert selected == [(scene_id,)]
    assert len(played) == 1


def test_play_scene_unknown_id_raises_not_found(main_window, facade, monkeypatch):
    played = _record(monkeypatch, main_window.scenes_widget, "play_current")
    with pytest.raises(RemoteError) as exc:
        facade.play_scene(999)
    assert exc.value.code == "not_found"
    assert played == []


@pytest.mark.parametrize("bad_id", ["3", 3.5, True, None])
def test_play_scene_rejects_non_int_ids(facade, bad_id):
    with pytest.raises(RemoteError) as exc:
        facade.play_scene(bad_id)
    assert exc.value.code == "invalid_params"


def test_play_playlist_switches_tab_selects_and_plays(main_window, facade, monkeypatch):
    playlist_id = main_window.db.add_playlist(Playlist(name="Battle Mix"))
    selected = _record(monkeypatch, main_window.playlists_widget, "select_playlist")
    played = _record(monkeypatch, main_window.playlists_widget, "play_current")
    facade.play_playlist(playlist_id)
    assert main_window.tab_widget.currentWidget() is main_window.playlists_widget
    assert selected == [(playlist_id,)]
    assert len(played) == 1


def test_play_playlist_unknown_id_raises_not_found(main_window, facade):
    with pytest.raises(RemoteError) as exc:
        facade.play_playlist(999)
    assert exc.value.code == "not_found"


# --- transport delegation ----------------------------------------------------


def test_toggle_play_pause_delegates_to_window(main_window, facade, monkeypatch):
    calls = _record(monkeypatch, main_window, "toggle_play_pause")
    facade.toggle_play_pause()
    assert len(calls) == 1


def test_next_track_delegates_to_window(main_window, facade, monkeypatch):
    calls = _record(monkeypatch, main_window, "next_track")
    facade.next_track()
    assert len(calls) == 1


# --- master volume -----------------------------------------------------------


def test_set_master_volume_applies_everywhere(main_window, facade):
    applied = facade.set_master_volume(42)
    assert applied == 42
    assert main_window.master_slider.value() == 42
    assert main_window.audio_engine.master_volume == 42
    assert main_window.master_value_label.text() == "42%"


@pytest.mark.parametrize("value,expected", [(150, 100), (-5, 0), (0, 0), (100, 100)])
def test_set_master_volume_clamps(main_window, facade, value, expected):
    assert facade.set_master_volume(value) == expected
    assert main_window.master_slider.value() == expected


@pytest.mark.parametrize("bad_value", ["50", 3.5, True, None])
def test_set_master_volume_rejects_non_ints(facade, bad_value):
    with pytest.raises(RemoteError) as exc:
        facade.set_master_volume(bad_value)
    assert exc.value.code == "invalid_params"


# --- state_changed event -------------------------------------------------------


def test_state_changed_on_scene_playback_sees_updated_state(main_window, facade):
    # Connection order matters: MainWindow's slot must run before the facade's
    # so the snapshot reflects the new now-playing state, not the old one.
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    snapshots = []
    facade.state_changed.connect(snapshots.append)
    main_window.scenes_widget.playback_state_changed.emit(scene_id, "Tavern", True)
    assert snapshots
    assert snapshots[-1]["playing"] == {
        "type": "scene",
        "id": scene_id,
        "name": "Tavern",
    }


def test_state_changed_on_stop_reports_idle(main_window, facade):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    main_window.scenes_widget.playback_state_changed.emit(scene_id, "Tavern", True)
    snapshots = []
    facade.state_changed.connect(snapshots.append)
    main_window.scenes_widget.playback_state_changed.emit(scene_id, "Tavern", False)
    assert snapshots[-1]["playing"] is None


def test_state_changed_on_volume_change(main_window, facade):
    main_window.master_slider.setValue(37)
    snapshots = []
    facade.state_changed.connect(snapshots.append)
    facade.set_master_volume(64)
    assert snapshots
    assert snapshots[-1]["master_volume"] == 64


def test_no_state_changed_when_volume_unchanged(main_window, facade):
    # QSlider.setValue with the same value doesn't fire valueChanged; the
    # facade inherits that (no redundant broadcasts to clients).
    facade.set_master_volume(50)
    snapshots = []
    facade.state_changed.connect(snapshots.append)
    facade.set_master_volume(50)
    assert snapshots == []
