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
    assert {
        "id": scene_id,
        "name": "Tavern",
        "active_preset": 1,
        "presets": [
            {"slot": 1, "name": None},
            {"slot": 2, "name": None},
            {"slot": 3, "name": None},
        ],
    } in facade.get_scenes()


def test_get_scenes_includes_preset_names_and_active_slot(main_window, facade):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    main_window.db.rename_scene_preset(scene_id, 2, "Combat")
    main_window.db.set_active_preset_slot(scene_id, 2)
    (scene,) = [s for s in facade.get_scenes() if s["id"] == scene_id]
    assert scene["active_preset"] == 2
    assert scene["presets"][1] == {"slot": 2, "name": "Combat"}


def test_get_playlists_returns_id_and_name(main_window, facade):
    playlist_id = main_window.db.add_playlist(Playlist(name="Battle Mix"))
    assert {"id": playlist_id, "name": "Battle Mix"} in facade.get_playlists()


def test_get_state_idle(main_window, facade):
    state = facade.get_state()
    assert state["playing"] is None
    assert state["paused"] is None
    assert state["master_volume"] == main_window.audio_engine.master_volume


def test_get_state_reflects_playing_scene(main_window, facade, qapp):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    main_window.scenes_widget.playback_state_changed.emit(scene_id, "Tavern", True)
    qapp.processEvents()
    assert facade.get_state()["playing"] == {
        "type": "scene",
        "id": scene_id,
        "name": "Tavern",
        "preset": {"slot": 1, "name": None},
    }


def test_get_state_playing_scene_reports_named_active_preset(main_window, facade, qapp):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    main_window.db.rename_scene_preset(scene_id, 3, "Night")
    main_window.db.set_active_preset_slot(scene_id, 3)
    main_window.scenes_widget.playback_state_changed.emit(scene_id, "Tavern", True)
    qapp.processEvents()
    assert facade.get_state()["playing"]["preset"] == {"slot": 3, "name": "Night"}


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
        "preset": None,
    }


def _set_scene_editor_active(main_window, scene_id: int, is_playing: bool):
    """Put the real scene editor into an active (playing/paused) state."""
    editor = main_window.scenes_widget.scene_editor
    editor._active_scene_id = scene_id
    editor._scene_playing = is_playing


def _set_playlist_editor_active(main_window, playlist_id: int, is_playing: bool):
    editor = main_window.playlists_widget.playlist_editor
    editor._active_playlist = Playlist(id=playlist_id)
    editor._is_playing = is_playing


def test_get_state_reports_paused_scene(main_window, facade):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    _set_scene_editor_active(main_window, scene_id, is_playing=False)
    state = facade.get_state()
    assert state["playing"] is None
    assert state["paused"] == {
        "type": "scene",
        "id": scene_id,
        "name": "Tavern",
        "preset": {"slot": 1, "name": None},
    }


def test_get_state_reports_paused_playlist(main_window, facade):
    playlist_id = main_window.db.add_playlist(Playlist(name="Battle Mix"))
    _set_playlist_editor_active(main_window, playlist_id, is_playing=False)
    state = facade.get_state()
    assert state["playing"] is None
    assert state["paused"] == {
        "type": "playlist",
        "id": playlist_id,
        "name": "Battle Mix",
        "preset": None,
    }


def test_get_state_paused_is_none_while_active_item_is_playing(main_window, facade):
    # An editor reporting active-and-playing must not surface as paused.
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    _set_scene_editor_active(main_window, scene_id, is_playing=True)
    state = facade.get_state()
    assert state["paused"] is None


def test_get_state_playing_suppresses_paused(main_window, facade, qapp):
    # Defensive: if editor state were ever stale while something plays,
    # `playing` wins — the two fields stay mutually exclusive on the wire.
    playlist_id = main_window.db.add_playlist(Playlist(name="Battle Mix"))
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    _set_playlist_editor_active(main_window, playlist_id, is_playing=False)
    main_window.scenes_widget.playback_state_changed.emit(scene_id, "Tavern", True)
    qapp.processEvents()
    state = facade.get_state()
    assert state["playing"]["id"] == scene_id
    assert state["paused"] is None


def test_get_state_name_is_none_for_id_missing_from_db(main_window, facade, qapp):
    # Defensive: playing id not resolvable (e.g. deleted mid-playback).
    main_window.scenes_widget.playback_state_changed.emit(999, "Ghost", True)
    qapp.processEvents()
    playing = facade.get_state()["playing"]
    assert playing["id"] == 999
    assert playing["name"] is None
    assert playing["preset"] is None


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


# --- presets -------------------------------------------------------------------


def _record_named(monkeypatch, obj, events, *names):
    """Monkeypatch each method to append (name, args) to one shared list."""
    for name in names:
        monkeypatch.setattr(obj, name, lambda *a, _n=name: events.append((_n, a)))


def test_play_scene_with_preset_switches_before_playing(
    main_window, facade, monkeypatch
):
    # Ordering matters: the preset must be active before playback starts so
    # the scene comes up directly in it (no start-then-transition blip).
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    events = []
    _record_named(
        monkeypatch,
        main_window.scenes_widget,
        events,
        "select_scene",
        "switch_preset",
        "play_current",
    )
    facade.play_scene(scene_id, preset=2)
    assert events == [
        ("select_scene", (scene_id,)),
        ("switch_preset", (2,)),
        ("play_current", ()),
    ]


def test_play_scene_without_preset_does_not_touch_presets(
    main_window, facade, monkeypatch
):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    switched = _record(monkeypatch, main_window.scenes_widget, "switch_preset")
    facade.play_scene(scene_id)
    assert switched == []


@pytest.mark.parametrize("bad_preset", ["2", 2.5, True, 0, 4, -1])
def test_play_scene_rejects_bad_presets(main_window, facade, monkeypatch, bad_preset):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    played = _record(monkeypatch, main_window.scenes_widget, "play_current")
    with pytest.raises(RemoteError) as exc:
        facade.play_scene(scene_id, preset=bad_preset)
    assert exc.value.code == "invalid_params"
    assert played == []


def test_set_preset_targets_the_active_scene(main_window, facade, monkeypatch):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    _set_scene_editor_active(main_window, scene_id, is_playing=True)
    events = []
    _record_named(
        monkeypatch,
        main_window.scenes_widget,
        events,
        "select_scene",
        "switch_preset",
        "play_current",
    )
    facade.set_preset(3)
    assert main_window.tab_widget.currentWidget() is main_window.scenes_widget
    assert events == [("select_scene", (scene_id,)), ("switch_preset", (3,))]


def test_set_preset_works_on_a_paused_scene(main_window, facade, monkeypatch):
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    _set_scene_editor_active(main_window, scene_id, is_playing=False)
    switched = _record(monkeypatch, main_window.scenes_widget, "switch_preset")
    facade.set_preset(2)
    assert switched == [(2,)]


def test_set_preset_errors_when_no_scene_is_active(main_window, facade, monkeypatch):
    switched = _record(monkeypatch, main_window.scenes_widget, "switch_preset")
    with pytest.raises(RemoteError) as exc:
        facade.set_preset(2)
    assert exc.value.code == "no_active_scene"
    assert switched == []


def test_set_preset_errors_while_a_playlist_plays(main_window, facade, monkeypatch):
    # A playing playlist means no scene is active — presets are scene-only.
    playlist_id = main_window.db.add_playlist(Playlist(name="Battle Mix"))
    _set_playlist_editor_active(main_window, playlist_id, is_playing=True)
    with pytest.raises(RemoteError) as exc:
        facade.set_preset(2)
    assert exc.value.code == "no_active_scene"


@pytest.mark.parametrize("bad_preset", ["2", 2.5, True, 0, 4, None])
def test_set_preset_rejects_bad_slots(facade, bad_preset):
    with pytest.raises(RemoteError) as exc:
        facade.set_preset(bad_preset)
    assert exc.value.code == "invalid_params"


def test_preset_change_broadcasts_updated_state(main_window, facade, qapp):
    # An in-app preset click must reach remote clients: the widget's
    # preset_changed signal triggers a fresh snapshot with the new slot.
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    main_window.scenes_widget.playback_state_changed.emit(scene_id, "Tavern", True)
    qapp.processEvents()
    main_window.db.set_active_preset_slot(scene_id, 2)
    snapshots = []
    facade.state_changed.connect(snapshots.append)
    main_window.scenes_widget.preset_changed.emit(scene_id, 2)
    assert snapshots
    assert snapshots[-1]["playing"]["preset"]["slot"] == 2


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
        "preset": {"slot": 1, "name": None},
    }


def test_state_changed_on_pause_reports_paused(main_window, facade):
    # Pausing emits is_playing=False with the id still set; the snapshot built
    # off that event must show the item as paused, not vanished.
    scene_id = main_window.db.add_scene(Scene(title="Tavern"))
    main_window.scenes_widget.playback_state_changed.emit(scene_id, "Tavern", True)
    _set_scene_editor_active(main_window, scene_id, is_playing=False)
    snapshots = []
    facade.state_changed.connect(snapshots.append)
    main_window.scenes_widget.playback_state_changed.emit(scene_id, "Tavern", False)
    assert snapshots[-1]["playing"] is None
    assert snapshots[-1]["paused"] == {
        "type": "scene",
        "id": scene_id,
        "name": "Tavern",
        "preset": {"slot": 1, "name": None},
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
