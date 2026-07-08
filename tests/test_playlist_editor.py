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
