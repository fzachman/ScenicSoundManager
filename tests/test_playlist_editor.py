"""Tests for PlaylistEditor playback/highlight behavior.

Focus: the now-playing highlight must light up the *first* track the instant
playback starts. Regression guard for the ordering bug where _start_playback set
self._is_playing = True only AFTER _play_audio_file ran the highlight pass — so
_update_now_playing_highlight (which is gated on _is_playing) found it False and
highlighted nothing until the next auto/manual track advance.

TrackPlayer is stubbed so no real VLC/audio is needed; only the highlight state
(PlaylistTrackItem._now_playing) and the editor's playback flags are asserted.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.audio import TRANSITION_FADE_MS
from app.database import AudioFile, DatabaseConnection, Playlist
from app.playlists.playlist_editor import PlaylistEditor


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
def playlist(db):
    """A playlist with 3 tracks, returned freshly loaded (tracks + audio_file)."""
    file_ids = []
    for i in range(3):
        af = AudioFile(
            file_path=f"/fake/path/track_{i}.mp3",
            title=f"Track {i}",
            artist="Test Artist",
            duration_seconds=120.0,
        )
        file_ids.append(db.add_audio_file(af))

    playlist_id = db.add_playlist(Playlist(name="Test Playlist"))
    for i, fid in enumerate(file_ids):
        db.add_track_to_playlist(playlist_id, fid, position=i)

    return db.get_playlist(playlist_id)


@pytest.fixture
def second_playlist(db):
    """A second playlist with 2 tracks disjoint from the first fixture's."""
    file_ids = []
    for i in range(2):
        af = AudioFile(
            file_path=f"/fake/path/other_{i}.mp3",
            title=f"Other {i}",
            artist="Test Artist",
            duration_seconds=90.0,
        )
        file_ids.append(db.add_audio_file(af))

    playlist_id = db.add_playlist(Playlist(name="Other Playlist"))
    for i, fid in enumerate(file_ids):
        db.add_track_to_playlist(playlist_id, fid, position=i)

    return db.get_playlist(playlist_id)


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.available = False
    engine.master_volume = 100
    return engine


@pytest.fixture
def editor(qapp, db, mock_engine):
    """A PlaylistEditor whose TrackPlayer + file existence are stubbed out."""
    # MagicMock stands in for TrackPlayer: .end_reached.connect / fade_in / stop /
    # release all become no-op mock calls, so _play_audio_file runs to completion
    # (sets _current_audio_file_id and fires the highlight) without touching VLC.
    with (
        patch("app.playlists.playlist_editor.TrackPlayer", MagicMock()),
        patch("app.playlists.playlist_editor.os.path.exists", return_value=True),
    ):
        yield PlaylistEditor(db, mock_engine)


def _highlighted_audio_file_ids(editor):
    return [
        item.track.audio_file_id
        for item in editor._track_items.values()
        if item._now_playing
    ]


class TestStartPlaybackHighlight:
    def test_first_track_highlighted_immediately_on_start(self, editor, playlist):
        editor.load_playlist(playlist)
        assert _highlighted_audio_file_ids(editor) == []  # nothing playing yet

        editor.toggle_playback()  # Space / Play button entry point

        first_audio_file_id = playlist.tracks[0].audio_file_id
        assert editor._is_playing is True
        assert editor._current_audio_file_id == first_audio_file_id
        assert _highlighted_audio_file_ids(editor) == [first_audio_file_id]

    def test_exactly_one_track_highlighted(self, editor, playlist):
        editor.load_playlist(playlist)
        editor.toggle_playback()
        assert len(_highlighted_audio_file_ids(editor)) == 1

    def test_highlight_follows_next_track(self, editor, playlist):
        editor.load_playlist(playlist)
        editor.toggle_playback()
        editor.next_track()

        second_audio_file_id = playlist.tracks[1].audio_file_id
        assert editor._current_audio_file_id == second_audio_file_id
        assert _highlighted_audio_file_ids(editor) == [second_audio_file_id]

    def test_highlight_cleared_when_stopped(self, editor, playlist):
        editor.load_playlist(playlist)
        editor.toggle_playback()
        editor._stop_playback()
        assert _highlighted_audio_file_ids(editor) == []


class TestActivePlaybackState:
    def test_active_playback_lifecycle(self, editor, playlist):
        assert editor.active_playback() is None

        editor.load_playlist(playlist)
        editor.toggle_playback()
        assert editor.active_playback() == (playlist.id, True)

        editor.toggle_playback()  # pause keeps the playlist active
        assert editor.active_playback() == (playlist.id, False)

        editor._stop_playback()
        assert editor.active_playback() is None

    def test_stop_while_paused_emits_state_change(self, editor, playlist):
        # Stopping a PAUSED playlist is a real transition (its resumable state
        # is gone) and must be broadcast — the old guard on _is_playing made
        # this teardown silent, leaving remote clients showing a stale pause.
        editor.load_playlist(playlist)
        editor.toggle_playback()
        editor.toggle_playback()  # now paused
        emissions = []
        editor.playback_state_changed.connect(lambda *args: emissions.append(args))

        editor._stop_playback()

        assert emissions == [(playlist.id, None, False)]

    def test_stop_while_idle_emits_nothing(self, editor, playlist):
        editor.load_playlist(playlist)
        emissions = []
        editor.playback_state_changed.connect(lambda *args: emissions.append(args))

        editor._stop_playback()

        assert emissions == []


class TestSwitchCrossfade:
    """Switching playback to another playlist fades the old track out
    (overlapping the new track's fade-in = crossfade); explicit stop paths
    keep the hard cut."""

    def test_switching_playlists_fades_out_old_player(
        self, editor, playlist, second_playlist
    ):
        editor.load_playlist(playlist)
        editor.toggle_playback()
        # The patched TrackPlayer class is one MagicMock, so old and new
        # "instances" are the same object — reset to isolate the switch.
        player = editor._player
        player.reset_mock()

        editor.load_playlist(second_playlist)
        editor.toggle_playback()

        player.fade_out_and_release.assert_called_once_with(TRANSITION_FADE_MS)
        player.stop.assert_not_called()
        player.release.assert_not_called()

    def test_stop_all_default_is_hard_stop(self, editor, playlist):
        # App close must keep cutting immediately, not fade for 1.5s.
        editor.load_playlist(playlist)
        editor.toggle_playback()
        player = editor._player
        player.reset_mock()

        editor.stop_all()

        player.stop.assert_called_once()
        player.release.assert_called_once()
        player.fade_out_and_release.assert_not_called()


class TestShufflePersistence:
    def test_toggle_persists_to_db(self, editor, playlist, db):
        editor.load_playlist(playlist)

        editor.shuffle_btn.click()
        assert db.get_playlist(playlist.id).is_shuffle is True

        editor.shuffle_btn.click()
        assert db.get_playlist(playlist.id).is_shuffle is False

    def test_load_playlist_reflects_stored_flag(self, editor, playlist, db):
        db.update_playlist_shuffle(playlist.id, True)

        editor.load_playlist(db.get_playlist(playlist.id))
        assert editor.shuffle_btn.isChecked() is True

    def test_shuffle_state_follows_open_playlist(
        self, editor, playlist, second_playlist, db
    ):
        db.update_playlist_shuffle(playlist.id, True)

        editor.load_playlist(db.get_playlist(playlist.id))
        assert editor.shuffle_btn.isChecked() is True

        editor.load_playlist(second_playlist)
        assert editor.shuffle_btn.isChecked() is False

    def test_toggle_while_browsing_leaves_active_playback_alone(
        self, editor, playlist, second_playlist, db
    ):
        editor.load_playlist(playlist)
        editor.toggle_playback()

        editor.load_playlist(second_playlist)
        editor.shuffle_btn.click()

        assert db.get_playlist(second_playlist.id).is_shuffle is True
        assert db.get_playlist(playlist.id).is_shuffle is False
        assert editor._active_playlist.is_shuffle is False

    def test_toggle_on_active_playlist_updates_live_playback(
        self, editor, playlist, db
    ):
        editor.load_playlist(playlist)
        editor.toggle_playback()

        editor.shuffle_btn.click()

        assert editor._active_playlist.is_shuffle is True


class TestActiveOpenDecoupling:
    """Playback must keep operating on the ACTIVE playlist while another
    one is open in the editor (browsing must not hijack the transport)."""

    def test_next_advances_active_playlist_while_browsing(
        self, editor, playlist, second_playlist
    ):
        editor.load_playlist(playlist)
        editor.toggle_playback()

        editor.load_playlist(second_playlist)
        editor.next_track()

        assert editor._current_audio_file_id == playlist.tracks[1].audio_file_id
        assert editor.active_playback() == (playlist.id, True)

    def test_auto_advance_uses_active_playlist_while_browsing(
        self, editor, playlist, second_playlist
    ):
        editor.load_playlist(playlist)
        editor.toggle_playback()

        editor.load_playlist(second_playlist)
        editor._on_track_ended()

        assert editor._current_audio_file_id == playlist.tracks[1].audio_file_id

    def test_shuffled_advance_draws_from_active_playlist(
        self, editor, playlist, second_playlist, db
    ):
        db.update_playlist_shuffle(playlist.id, True)
        editor.load_playlist(db.get_playlist(playlist.id))
        editor.toggle_playback()

        editor.load_playlist(second_playlist)
        active_ids = {t.audio_file_id for t in playlist.tracks}
        for _ in range(4):
            editor.next_track()
            assert editor._current_audio_file_id in active_ids

    def test_next_while_paused_resumes_playback(self, editor, playlist):
        editor.load_playlist(playlist)
        editor.toggle_playback()
        editor.toggle_playback()  # pause
        emissions = []
        editor.playback_state_changed.connect(lambda *args: emissions.append(args))

        editor.next_track()

        assert editor._is_playing is True
        assert editor._current_audio_file_id == playlist.tracks[1].audio_file_id
        assert emissions == [(playlist.id, playlist.name, True)]

    def test_next_while_idle_is_noop(self, editor, playlist):
        editor.load_playlist(playlist)
        emissions = []
        editor.playback_state_changed.connect(lambda *args: emissions.append(args))

        editor.next_track()

        assert editor._is_playing is False
        assert emissions == []

    def test_track_edits_reach_active_playback(self, editor, playlist, db):
        # Removing a track from the OPEN playlist while it is the ACTIVE one
        # must update the copy playback advances over, not just the display.
        editor.load_playlist(playlist)
        editor.toggle_playback()

        editor._remove_track(playlist.tracks[1].id)

        remaining = {t.audio_file_id for t in editor._active_playlist.tracks}
        assert playlist.tracks[1].audio_file_id not in remaining
        editor.next_track()
        assert editor._current_audio_file_id in remaining


class TestDoubleClickJump:
    """Double-clicking a track card makes it the current track."""

    def test_card_double_click_emits_play_requested(self, qapp, editor, playlist):
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest

        editor.load_playlist(playlist)
        item = editor._track_items[playlist.tracks[1].id]
        received = []
        item.play_requested.connect(received.append)

        QTest.mouseDClick(item, Qt.MouseButton.LeftButton)

        assert received == [playlist.tracks[1].id]

    def test_jump_while_playing_switches_current_track(self, editor, playlist):
        editor.load_playlist(playlist)
        editor.toggle_playback()

        editor._on_track_play_requested(playlist.tracks[2].id)

        jumped_id = playlist.tracks[2].audio_file_id
        assert editor._is_playing is True
        assert editor._current_audio_file_id == jumped_id
        assert _highlighted_audio_file_ids(editor) == [jumped_id]

    def test_jump_while_stopped_starts_playlist_at_that_track(self, editor, playlist):
        editor.load_playlist(playlist)

        editor._on_track_play_requested(playlist.tracks[1].id)

        assert editor.active_playback() == (playlist.id, True)
        assert editor._current_audio_file_id == playlist.tracks[1].audio_file_id
        # Sequential playback continues from the jumped-to position.
        editor.next_track()
        assert editor._current_audio_file_id == playlist.tracks[2].audio_file_id

    def test_jump_while_paused_resumes(self, editor, playlist):
        editor.load_playlist(playlist)
        editor.toggle_playback()
        editor.toggle_playback()  # pause
        emissions = []
        editor.playback_state_changed.connect(lambda *args: emissions.append(args))

        editor._on_track_play_requested(playlist.tracks[1].id)

        assert editor._is_playing is True
        assert editor._current_audio_file_id == playlist.tracks[1].audio_file_id
        assert emissions == [(playlist.id, playlist.name, True)]

    def test_jump_in_browsed_playlist_takes_over_playback(
        self, editor, playlist, second_playlist
    ):
        editor.load_playlist(playlist)
        editor.toggle_playback()

        editor.load_playlist(second_playlist)
        editor._on_track_play_requested(second_playlist.tracks[1].id)

        assert editor.active_playback() == (second_playlist.id, True)
        assert editor._current_audio_file_id == second_playlist.tracks[1].audio_file_id

    def test_shuffle_jump_counts_as_played_in_cycle(self, editor, playlist, db):
        db.update_playlist_shuffle(playlist.id, True)
        editor.load_playlist(db.get_playlist(playlist.id))

        editor._on_track_play_requested(playlist.tracks[1].id)

        played = [editor._current_audio_file_id]
        for _ in range(2):  # exhaust the 3-track cycle
            editor.next_track()
            played.append(editor._current_audio_file_id)
        assert set(played) == {t.audio_file_id for t in playlist.tracks}


class TestPerTrackVolume:
    """Per-track volume: card slider persists and follows live playback."""

    def test_card_slider_reflects_stored_volume(self, editor, playlist, db):
        db.update_playlist_track_volume(playlist.tracks[0].id, 0.4)

        editor.load_playlist(db.get_playlist(playlist.id))

        item = editor._track_items[playlist.tracks[0].id]
        assert item.volume_slider.slider.value() == 40

    def test_slider_commit_persists_and_updates_model(self, editor, playlist, db):
        editor.load_playlist(playlist)
        item = editor._track_items[playlist.tracks[0].id]

        item.volume_slider.slider.setValue(35)  # discrete change -> commit

        assert db.get_playlist(playlist.id).tracks[0].volume == 0.35
        assert item.track.volume == 0.35

    def test_playback_starts_at_track_volume(self, editor, playlist, db):
        db.update_playlist_track_volume(playlist.tracks[0].id, 0.5)
        editor.load_playlist(db.get_playlist(playlist.id))

        editor.toggle_playback()

        assert editor._player.target_volume == 50

    def test_live_volume_follows_playing_cards_slider(self, editor, playlist):
        editor.load_playlist(playlist)
        editor.toggle_playback()

        editor._track_items[playlist.tracks[0].id].volume_slider.slider.setValue(25)

        assert editor._player.target_volume == 25

    def test_other_cards_slider_leaves_playback_alone(self, editor, playlist):
        editor.load_playlist(playlist)
        editor.toggle_playback()

        editor._track_items[playlist.tracks[1].id].volume_slider.slider.setValue(10)

        assert editor._player.target_volume == 100  # track 0's own volume

    def test_edited_volume_applies_when_track_is_reached(self, editor, playlist):
        editor.load_playlist(playlist)
        editor.toggle_playback()
        editor._track_items[playlist.tracks[1].id].volume_slider.slider.setValue(20)

        editor.next_track()

        assert editor._player.target_volume == 20


class TestTrackScrubber:
    """Scrubber row: live only on the playing card, drives seeks by fraction."""

    def test_scrubber_enabled_only_on_playing_card(self, editor, playlist):
        editor.load_playlist(playlist)
        assert all(
            not item.scrubber.slider.isEnabled()
            for item in editor._track_items.values()
        )

        editor.toggle_playback()

        playing_id = playlist.tracks[0].id
        for track_id, item in editor._track_items.items():
            assert item.scrubber.slider.isEnabled() is (track_id == playing_id)

    def test_position_updates_drive_playing_scrubber(self, editor, playlist):
        editor.load_playlist(playlist)
        editor.toggle_playback()
        editor._player.get_duration.return_value = 120_000

        editor._on_player_position(60_000)

        item = editor._track_items[playlist.tracks[0].id]
        assert item.scrubber.slider.value() == 500
        assert item.scrubber.position_label.text() == "1:00"
        assert item.scrubber.duration_label.text() == "2:00"

    def test_scrubber_resets_when_track_advances(self, editor, playlist):
        editor.load_playlist(playlist)
        editor.toggle_playback()
        editor._player.get_duration.return_value = 120_000
        editor._on_player_position(30_000)
        first = editor._track_items[playlist.tracks[0].id]
        assert first.scrubber.slider.value() == 250

        editor.next_track()

        assert first.scrubber.slider.value() == 0
        assert first.scrubber.slider.isEnabled() is False

    def test_seek_maps_fraction_to_ms(self, editor, playlist):
        editor.load_playlist(playlist)
        editor.toggle_playback()
        editor._player.get_duration.return_value = 120_000

        editor._track_items[playlist.tracks[0].id].scrubber.seek.emit(0.5)

        editor._player.set_position.assert_called_once_with(60_000)

    def test_seek_falls_back_to_metadata_duration(self, editor, playlist):
        # VLC reports 0 before the media is parsed; the fixture files carry
        # 120s of metadata duration.
        editor.load_playlist(playlist)
        editor.toggle_playback()
        editor._player.get_duration.return_value = 0

        editor._track_items[playlist.tracks[0].id].scrubber.seek.emit(0.25)

        editor._player.set_position.assert_called_once_with(30_000)

    def test_seek_on_non_playing_card_is_ignored(self, editor, playlist):
        editor.load_playlist(playlist)
        editor.toggle_playback()
        editor._player.get_duration.return_value = 120_000

        editor._track_items[playlist.tracks[1].id].scrubber.seek.emit(0.5)

        editor._player.set_position.assert_not_called()
