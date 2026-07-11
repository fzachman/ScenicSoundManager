"""Tests for SceneEditor preset behavior.

Covers the three preset buttons (enable/check/name sync), preset switching in
every playback state (stopped, playing, paused), the no-write-back guarantee
of the silent card setters, and right-click rename.

The AudioEngine is a MagicMock with available=False, so TrackPlayers are
real objects with working fade state machines but no VLC. os.path.exists is
patched True so the editor creates players for the fake file paths.
"""

import os
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QPoint

from app.audio.player import _retiring_players
from app.database import AudioFile, DatabaseConnection, Playlist, Scene
from app.scenes.scene_editor import SceneEditor
from tests.control_helpers import record


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = DatabaseConnection(db_path)
    conn.connect()
    yield conn
    conn.close()
    os.unlink(db_path)


@pytest.fixture
def scene(db):
    """A scene with two tracks and one single-track playlist entry."""
    scene_id = db.add_scene(Scene(title="Preset Scene"))
    track_ids = []
    for i in range(2):
        file_id = db.add_audio_file(
            AudioFile(
                file_path=f"/fake/scene_{i}.mp3",
                title=f"Scene Track {i}",
                duration_seconds=60.0,
            )
        )
        track_ids.append(db.add_track_to_scene(scene_id, file_id, position=i))

    playlist_id = db.add_playlist(Playlist(name="Scene Playlist"))
    playlist_file_id = db.add_audio_file(
        AudioFile(
            file_path="/fake/playlist_0.mp3",
            title="Playlist Track 0",
            duration_seconds=60.0,
        )
    )
    db.add_track_to_playlist(playlist_id, playlist_file_id, position=0)
    entry_id = db.add_playlist_to_scene(scene_id, playlist_id)

    return SimpleNamespace(scene_id=scene_id, track_ids=track_ids, entry_id=entry_id)


@pytest.fixture
def editor(qapp, db):
    engine = MagicMock()
    engine.available = False
    engine.master_volume = 100
    with patch("app.scenes.scene_editor.os.path.exists", return_value=True):
        editor = SceneEditor(db, engine)
        yield editor
        editor.stop_all()


@pytest.fixture
def second_scene(db):
    """A second scene with a single track (no playlist entry)."""
    scene_id = db.add_scene(Scene(title="Other Scene"))
    file_id = db.add_audio_file(
        AudioFile(
            file_path="/fake/other_0.mp3",
            title="Other Track 0",
            duration_seconds=60.0,
        )
    )
    db.add_track_to_scene(scene_id, file_id, position=0)
    return SimpleNamespace(scene_id=scene_id)


def _load(editor, db, scene_id):
    editor.load_scene(db.get_scene(scene_id))


def _drive_fade_to_completion(player):
    for _ in range(100):
        if not player._is_fading():
            break
        player._fade_step()


class TestSceneSwitchCrossfade:
    """Starting another scene fades the old scene's tracks out (overlapping
    the new tracks' fade-in = crossfade); the default stop stays a hard cut."""

    def test_switching_scenes_fades_out_old_players(
        self, editor, db, scene, second_scene
    ):
        _load(editor, db, scene.scene_id)
        editor._toggle_scene_play()
        old_players = list(editor.mixer.get_all_players().values())
        assert old_players
        # No VLC in tests (media_player is None, is_playing() False), so the
        # retiring fade would short-circuit to an immediate release — fake an
        # audibly-playing player.
        for p in old_players:
            p.media_player = MagicMock()
            p.is_playing = MagicMock(return_value=True)

        _load(editor, db, second_scene.scene_id)
        editor._toggle_scene_play()

        # Old players left the mixer but are still fading toward release,
        # held alive by the retiring set (the engine registry is weak).
        assert editor._active_scene_id == second_scene.scene_id
        remaining = editor.mixer.get_all_players().values()
        for p in old_players:
            assert p not in remaining
            assert p._is_fading()
            assert p in _retiring_players
            _drive_fade_to_completion(p)
            assert p not in _retiring_players

    def test_stop_all_default_is_hard_cut(self, editor, db, scene):
        # App close must keep cutting immediately, not fade for 1.5s.
        _load(editor, db, scene.scene_id)
        editor._toggle_scene_play()
        old_players = list(editor.mixer.get_all_players().values())
        for p in old_players:
            p.is_playing = MagicMock(return_value=True)

        editor.stop_all()

        assert editor.mixer.get_all_players() == {}
        for p in old_players:
            assert not p._is_fading()
            assert p not in _retiring_players


class TestPresetButtons:
    def test_buttons_disabled_until_scene_loaded(self, editor):
        for btn in editor._preset_buttons.values():
            assert btn.isEnabled() is False

    def test_load_scene_enables_and_checks_active_slot(self, editor, db, scene):
        db.rename_scene_preset(scene.scene_id, 2, "Bar Fight")
        db.set_active_preset_slot(scene.scene_id, 2)

        _load(editor, db, scene.scene_id)

        assert all(btn.isEnabled() for btn in editor._preset_buttons.values())
        assert editor._preset_buttons[2].isChecked() is True
        assert editor._preset_buttons[2].text() == "Bar Fight"
        assert editor._preset_buttons[1].isChecked() is False
        assert editor._preset_buttons[1].text() == "Preset 1"

    def test_clear_disables_and_resets_buttons(self, editor, db, scene):
        db.rename_scene_preset(scene.scene_id, 3, "Custom")
        db.set_active_preset_slot(scene.scene_id, 3)
        _load(editor, db, scene.scene_id)

        editor.clear()

        for slot, btn in editor._preset_buttons.items():
            assert btn.isEnabled() is False
            assert btn.text() == f"Preset {slot}"
        assert editor._preset_slot == 1

    def test_click_same_slot_is_noop_and_stays_checked(self, editor, db, scene):
        _load(editor, db, scene.scene_id)

        editor._preset_buttons[1].click()

        assert editor._preset_buttons[1].isChecked() is True
        assert editor._preset_slot == 1
        assert db.get_scene(scene.scene_id).active_preset_slot == 1

    def test_rename_preset_persists_and_updates_button(self, editor, db, scene):
        _load(editor, db, scene.scene_id)
        dialog = MagicMock()
        dialog.exec.return_value = True
        dialog.get_text.return_value = "Ambush!"

        with patch("app.scenes.scene_editor.TextInputDialog", return_value=dialog):
            editor._rename_preset(3)

        assert db.get_scene_preset_names(scene.scene_id) == {3: "Ambush!"}
        assert editor._preset_buttons[3].text() == "Ambush!"

    def test_right_click_routes_rename_through_a_menu(self, editor, db, scene):
        # The rename dialog must open from a QMenu action, never directly
        # inside the customContextMenuRequested handler — the modal exec
        # mid-right-press left the mouse grab stuck and froze the whole UI.
        _load(editor, db, scene.scene_id)
        dialog = MagicMock()
        dialog.exec.return_value = True
        dialog.get_text.return_value = "Night Watch"
        menu = MagicMock()
        action = MagicMock()
        menu.addAction.return_value = action

        with (
            patch("app.scenes.scene_editor.QMenu", return_value=menu),
            patch("app.scenes.scene_editor.TextInputDialog", return_value=dialog),
        ):
            editor._show_preset_menu(2, QPoint(0, 0))
            # Only the popup menu ran; the dialog waits for the action.
            menu.exec.assert_called_once()
            dialog.exec.assert_not_called()

            trigger = action.triggered.connect.call_args[0][0]
            trigger()

        assert db.get_scene_preset_names(scene.scene_id) == {2: "Night Watch"}
        assert editor._preset_buttons[2].text() == "Night Watch"

    def test_rename_cancelled_changes_nothing(self, editor, db, scene):
        _load(editor, db, scene.scene_id)
        dialog = MagicMock()
        dialog.exec.return_value = False

        with patch("app.scenes.scene_editor.TextInputDialog", return_value=dialog):
            editor._rename_preset(2)

        assert db.get_scene_preset_names(scene.scene_id) == {}
        assert editor._preset_buttons[2].text() == "Preset 2"


class TestSwitchWhileStopped:
    def test_switch_updates_cards_and_persists_slot(self, editor, db, scene):
        track_id = scene.track_ids[0]
        db.update_scene_track_setting(
            track_id, volume=0.3, is_repeat=True, play_mode=False, slot=2
        )
        db.update_scene_playlist_entry_setting(
            scene.entry_id, volume=0.7, is_shuffle=True, slot=2
        )
        _load(editor, db, scene.scene_id)

        editor._preset_buttons[2].click()

        assert db.get_scene(scene.scene_id).active_preset_slot == 2
        control = editor._track_controls[track_id]
        assert control.volume_slider.value() == 30
        assert control._repeat_mode is True
        assert control._play_mode is False
        entry_control = editor._playlist_entry_controls[scene.entry_id]
        assert entry_control.volume_slider.value() == 70
        assert entry_control._shuffle_mode is True

    def test_switch_writes_nothing_back_to_the_incoming_preset(self, editor, db, scene):
        # If the card sync used the emitting paths, applying preset 2's values
        # would immediately persist them again — masking real regressions and
        # corrupting slots. Verify slot values are untouched by the switch.
        track_id = scene.track_ids[0]
        db.update_scene_track_setting(track_id, volume=0.3, slot=2)
        _load(editor, db, scene.scene_id)

        editor._preset_buttons[2].click()
        editor._preset_buttons[1].click()  # and switch back

        assert db.get_scene_tracks(scene.scene_id, slot=2)[0].volume == 0.3
        assert db.get_scene_tracks(scene.scene_id, slot=1)[0].volume == 1.0

    def test_switch_emits_no_card_setting_signals(self, editor, db, scene):
        db.update_scene_track_setting(
            scene.track_ids[0], volume=0.3, is_repeat=True, play_mode=False, slot=2
        )
        _load(editor, db, scene.scene_id)
        control = editor._track_controls[scene.track_ids[0]]
        emissions = []
        for signal in (
            control.volume_changed,
            control.volume_committed,
            control.repeat_changed,
            control.play_mode_changed,
        ):
            emissions.append(record(signal))

        editor._preset_buttons[2].click()

        assert all(rec == [] for rec in emissions)

    def test_switch_updates_in_memory_scene(self, editor, db, scene):
        db.update_scene_track_setting(scene.track_ids[0], volume=0.25, slot=3)
        _load(editor, db, scene.scene_id)

        editor._preset_buttons[3].click()

        track = editor._current_scene.tracks[0]
        assert track.volume == 0.25
        assert editor._current_scene.active_preset_slot == 3

    def test_edits_after_switch_land_in_the_new_slot(self, editor, db, scene):
        track_id = scene.track_ids[0]
        _load(editor, db, scene.scene_id)
        editor._preset_buttons[2].click()

        control = editor._track_controls[track_id]
        control.volume_slider.setValue(15)  # discrete change -> commit

        assert db.get_scene_tracks(scene.scene_id, slot=2)[0].volume == 0.15
        assert db.get_scene_tracks(scene.scene_id, slot=1)[0].volume == 1.0


class TestSwitchWhilePlaying:
    def test_track_staying_on_ramps_to_preset_volume(self, editor, db, scene):
        track_id = scene.track_ids[0]
        db.update_scene_track_setting(track_id, volume=0.2, is_repeat=True, slot=2)
        _load(editor, db, scene.scene_id)
        editor.toggle_playback()

        editor._preset_buttons[2].click()

        player = editor.mixer.get_player(track_id)
        assert player is not None
        assert player.target_volume == 20
        assert player.repeat is True
        assert player._is_fading()
        _drive_fade_to_completion(player)
        assert player._current_volume == 20

    def test_track_turning_off_fades_out(self, editor, db, scene):
        track_id = scene.track_ids[0]
        db.update_scene_track_setting(track_id, play_mode=False, slot=2)
        _load(editor, db, scene.scene_id)
        editor.toggle_playback()
        player = editor.mixer.get_player(track_id)

        editor._preset_buttons[2].click()

        assert player._is_fading()
        _drive_fade_to_completion(player)
        assert player._current_volume == 0

    def test_track_turning_on_fades_in(self, editor, db, scene):
        track_id = scene.track_ids[0]
        db.update_scene_track_setting(track_id, play_mode=False, slot=1)
        db.update_scene_track_setting(track_id, volume=0.6, slot=2)
        _load(editor, db, scene.scene_id)
        editor.toggle_playback()
        assert editor.mixer.get_player(track_id) is None  # off in slot 1

        editor._preset_buttons[2].click()

        player = editor.mixer.get_player(track_id)
        assert player is not None
        assert player.target_volume == 60
        assert player._is_fading()

    def test_playlist_entry_ramps_to_preset_volume(self, editor, db, scene):
        db.update_scene_playlist_entry_setting(scene.entry_id, volume=0.35, slot=2)
        _load(editor, db, scene.scene_id)
        editor.toggle_playback()
        entry_player = editor._playlist_players[scene.entry_id]

        editor._preset_buttons[2].click()

        assert entry_player._volume == 35
        assert entry_player._player.target_volume == 35

    def test_playlist_entry_turning_off_pauses(self, editor, db, scene):
        db.update_scene_playlist_entry_setting(scene.entry_id, play_mode=False, slot=2)
        _load(editor, db, scene.scene_id)
        editor.toggle_playback()
        entry_player = editor._playlist_players[scene.entry_id]
        assert entry_player.is_playing is True

        editor._preset_buttons[2].click()

        assert entry_player.is_playing is False


class TestSwitchWhilePaused:
    def test_settings_pushed_into_silent_players(self, editor, db, scene):
        track_id = scene.track_ids[0]
        db.update_scene_track_setting(track_id, volume=0.45, is_repeat=True, slot=2)
        _load(editor, db, scene.scene_id)
        editor.toggle_playback()
        editor.toggle_playback()  # pause
        player = editor.mixer.get_player(track_id)

        editor._preset_buttons[2].click()

        assert player.target_volume == 45
        assert player.repeat is True
        # Resume comes up in the new preset
        editor.toggle_playback()
        assert player.target_volume == 45


class TestEndedTrackRevive:
    """A non-repeat track that finished must be revivable (bug: it stayed
    dead — Ended VLC players ignore set_time and never fire another end
    event for the repeat flag to act on)."""

    def _end_track(self, editor, track_id):
        player = editor.mixer.get_player(track_id)
        assert player is not None
        player._handle_end_reached()
        assert player.has_ended is True
        return player

    def test_repeat_toggle_revives_ended_track_while_playing(self, editor, db, scene):
        _load(editor, db, scene.scene_id)
        editor.toggle_playback()
        track_id = scene.track_ids[0]
        player = self._end_track(editor, track_id)

        editor._on_track_repeat_changed(track_id, True)

        assert player.has_ended is False
        assert player.repeat is True
        assert player._position_timer.isActive()

    def test_repeat_toggle_does_not_revive_while_paused(self, editor, db, scene):
        _load(editor, db, scene.scene_id)
        editor.toggle_playback()
        track_id = scene.track_ids[0]
        player = self._end_track(editor, track_id)
        editor.toggle_playback()  # pause the scene

        editor._on_track_repeat_changed(track_id, True)

        assert player.has_ended is True

    def test_repeat_toggle_off_leaves_ended_track_alone(self, editor, db, scene):
        _load(editor, db, scene.scene_id)
        editor.toggle_playback()
        track_id = scene.track_ids[0]
        player = self._end_track(editor, track_id)

        editor._on_track_repeat_changed(track_id, False)

        assert player.has_ended is True

    def test_preset_switch_to_repeat_on_revives_ended_track(self, editor, db, scene):
        track_id = scene.track_ids[0]
        db.update_scene_track_setting(track_id, is_repeat=True, slot=2)
        _load(editor, db, scene.scene_id)
        editor.toggle_playback()
        player = self._end_track(editor, track_id)

        editor._preset_buttons[2].click()

        assert player.has_ended is False
        assert player.repeat is True
