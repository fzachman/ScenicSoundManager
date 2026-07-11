"""Tests for ScenePlaylistPlayer - playlist playback within scenes."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.audio.scene_playlist_player import ScenePlaylistPlayer
from app.database import AudioFile, DatabaseConnection, Playlist


@pytest.fixture
def db():
    """Create a temporary database for testing"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = DatabaseConnection(db_path)
    conn.connect()

    yield conn

    conn.close()
    os.unlink(db_path)


@pytest.fixture
def playlist_with_tracks(db):
    """Create a playlist with 5 audio tracks in the database."""
    # Create audio files
    file_ids = []
    for i in range(5):
        af = AudioFile(
            file_path=f"/fake/path/track_{i}.mp3",
            title=f"Track {i}",
            artist="Test Artist",
            duration_seconds=180.0,
        )
        file_ids.append(db.add_audio_file(af))

    # Create playlist
    playlist = Playlist(name="Test Playlist")
    playlist_id = db.add_playlist(playlist)

    # Add tracks
    for i, fid in enumerate(file_ids):
        db.add_track_to_playlist(playlist_id, fid, position=i)

    return playlist_id, file_ids


@pytest.fixture
def mock_engine():
    """Mock AudioEngine that produces mock players."""
    engine = MagicMock()
    engine.available = False  # Prevents VLC calls
    engine.master_volume = 100
    return engine


def _make_player(playlist_id, db, engine, is_shuffle=False, is_repeat=False):
    """Create a ScenePlaylistPlayer with mocked TrackPlayer creation."""
    player = ScenePlaylistPlayer(
        playlist_id=playlist_id,
        db=db,
        engine=engine,
        is_shuffle=is_shuffle,
        is_repeat=is_repeat,
    )
    return player


class TestScenePlaylistPlayerInit:
    def test_loads_tracks_from_db(self, db, playlist_with_tracks, mock_engine):
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)

        assert player.playlist_id == playlist_id
        assert len(player._audio_file_ids) == 5
        assert player._audio_file_ids == file_ids

    def test_empty_playlist(self, db, mock_engine):
        playlist = Playlist(name="Empty")
        playlist_id = db.add_playlist(playlist)

        player = _make_player(playlist_id, db, mock_engine)
        assert len(player._audio_file_ids) == 0
        assert not player.is_playing

    def test_initial_state(self, db, playlist_with_tracks, mock_engine):
        playlist_id, _ = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)

        assert not player.is_playing
        assert player.current_audio_file_id is None


class TestSequentialPlayback:
    def test_get_next_sequential(self, db, playlist_with_tracks, mock_engine):
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)
        player._current_index = 0

        # Sequential: should advance through tracks in order
        next_id = player._get_next_audio_file_id()
        assert next_id == file_ids[1]

        next_id = player._get_next_audio_file_id()
        assert next_id == file_ids[2]

    def test_sequential_reaches_end(self, db, playlist_with_tracks, mock_engine):
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)
        player._current_index = len(file_ids) - 1  # last track

        next_id = player._get_next_audio_file_id()
        assert next_id is None  # end of playlist

    def test_sequential_all_tracks_in_order(
        self, db, playlist_with_tracks, mock_engine
    ):
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)
        player._current_index = 0

        played = [file_ids[0]]  # first track already "playing"
        for _ in range(4):
            next_id = player._get_next_audio_file_id()
            assert next_id is not None
            played.append(next_id)

        assert played == file_ids


class TestShufflePlayback:
    def test_shuffle_initializes_smart_shuffle(
        self, db, playlist_with_tracks, mock_engine
    ):
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine, is_shuffle=True)

        assert player._is_shuffle
        # SmartShuffle should have all track IDs
        assert sorted(player._shuffle.track_ids) == sorted(file_ids)

    def test_shuffle_no_repeats_until_all_played(
        self, db, playlist_with_tracks, mock_engine
    ):
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine, is_shuffle=True)

        played = set()
        # First call to start() would get the first track, then _get_next for the rest
        player._shuffle.reset()
        for _ in range(5):
            next_id = player._shuffle.next()
            assert next_id not in played, f"Track {next_id} repeated before all played"
            played.add(next_id)

        assert played == set(file_ids)

    def test_shuffle_returns_none_when_cycle_complete(
        self, db, playlist_with_tracks, mock_engine
    ):
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine, is_shuffle=True)

        # Exhaust the shuffle cycle
        player._shuffle.reset()
        for _ in range(5):
            player._shuffle.next()

        assert player._shuffle.cycle_complete
        # _get_next_audio_file_id should return None when cycle is complete
        next_id = player._get_next_audio_file_id()
        assert next_id is None

    def test_set_shuffle_during_playback(self, db, playlist_with_tracks, mock_engine):
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine, is_shuffle=False)

        assert not player._is_shuffle
        player.set_shuffle(True)
        assert player._is_shuffle
        assert sorted(player._shuffle.track_ids) == sorted(file_ids)


class TestRepeatBehavior:
    def test_set_repeat(self, db, playlist_with_tracks, mock_engine):
        playlist_id, _ = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine, is_repeat=False)

        assert not player._is_repeat
        player.set_repeat(True)
        assert player._is_repeat

    def test_restart_sequential(self, db, playlist_with_tracks, mock_engine):
        """Test that _restart resets to beginning in sequential mode."""
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine, is_repeat=True)

        # Simulate being at the end
        player._current_index = len(file_ids) - 1
        player._is_playing = True

        # Patch _play_file to capture what gets played
        played_ids = []

        def _fake_play(afid, fade_ms=500):
            played_ids.append(afid)
            return True

        player._play_file = _fake_play

        player._restart()
        assert played_ids == [file_ids[0]]  # Should restart from first track

    def test_restart_shuffle(self, db, playlist_with_tracks, mock_engine):
        """Test that _restart reshuffles in shuffle mode."""
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(
            playlist_id, db, mock_engine, is_shuffle=True, is_repeat=True
        )

        player._is_playing = True

        played_ids = []

        def _fake_play(afid, fade_ms=500):
            played_ids.append(afid)
            return True

        player._play_file = _fake_play

        player._restart()
        assert len(played_ids) == 1
        assert played_ids[0] in file_ids  # Should be one of the tracks


class TestTrackEndHandling:
    def test_on_track_ended_advances(self, db, playlist_with_tracks, mock_engine):
        """Test that _on_track_ended advances to next track."""
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)
        player._is_playing = True
        player._current_index = 0

        played_ids = []

        def _fake_play(afid, fade_ms=500):
            played_ids.append(afid)
            return True

        player._play_file = _fake_play

        player._on_track_ended()
        assert played_ids == [file_ids[1]]

    def test_on_track_ended_stops_at_end_no_repeat(
        self, db, playlist_with_tracks, mock_engine
    ):
        """Test that playback stops at end without repeat."""
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine, is_repeat=False)
        player._is_playing = True
        player._current_index = len(file_ids) - 1

        finished_signals = []
        player.playback_finished.connect(lambda: finished_signals.append(True))

        player._on_track_ended()
        assert not player._is_playing
        assert len(finished_signals) == 1

    def test_on_track_ended_restarts_with_repeat(
        self, db, playlist_with_tracks, mock_engine
    ):
        """Test that playback restarts at end with repeat."""
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine, is_repeat=True)
        player._is_playing = True
        player._current_index = len(file_ids) - 1

        played_ids = []

        def _fake_play(afid, fade_ms=500):
            played_ids.append(afid)
            return True

        player._play_file = _fake_play

        player._on_track_ended()
        assert len(played_ids) == 1
        assert played_ids[0] == file_ids[0]  # Sequential restart goes to first track

    def test_on_track_ended_no_op_when_not_playing(
        self, db, playlist_with_tracks, mock_engine
    ):
        """Test that _on_track_ended does nothing if not playing."""
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)
        player._is_playing = False

        played_ids = []
        player._play_file = lambda afid, fade_ms=500: played_ids.append(afid)

        player._on_track_ended()
        assert len(played_ids) == 0


class TestStartStop:
    def test_start_empty_playlist(self, db, mock_engine):
        """Start on empty playlist should be a no-op."""
        playlist = Playlist(name="Empty")
        playlist_id = db.add_playlist(playlist)

        player = _make_player(playlist_id, db, mock_engine)
        player.start()
        assert not player.is_playing

    def test_start_sets_playing(self, db, playlist_with_tracks, mock_engine):
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)

        played_ids = []

        def _fake_play(afid, fade_ms=500):
            played_ids.append(afid)
            return True

        player._play_file = _fake_play

        player.start()
        assert player.is_playing
        assert played_ids == [file_ids[0]]

    def test_start_shuffle_picks_from_pool(self, db, playlist_with_tracks, mock_engine):
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine, is_shuffle=True)

        played_ids = []

        def _fake_play(afid, fade_ms=500):
            played_ids.append(afid)
            return True

        player._play_file = _fake_play

        player.start()
        assert player.is_playing
        assert len(played_ids) == 1
        assert played_ids[0] in file_ids

    def test_stop_clears_state(self, db, playlist_with_tracks, mock_engine):
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)

        def _fake_play(afid, fade_ms=500):
            return True

        player._play_file = _fake_play
        player.start()
        assert player.is_playing

        player.stop()
        assert not player.is_playing
        assert player.current_audio_file_id is None

    def test_pause_and_resume(self, db, playlist_with_tracks, mock_engine):
        playlist_id, _ = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)

        def _fake_play(afid, fade_ms=500):
            return True

        player._play_file = _fake_play
        player.start()
        assert player.is_playing

        player.pause()
        assert not player.is_playing

        player.resume()
        assert player.is_playing

    def test_fade_out_and_release_detaches_and_fades_inner_player(
        self, db, playlist_with_tracks, mock_engine
    ):
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)
        player._is_playing = True
        player._current_audio_file_id = file_ids[0]
        inner = MagicMock(name="inner_track_player")
        player._player = inner

        player.fade_out_and_release(1500)

        # Signals are cut so the fading track can't advance the playlist or
        # drive the scrubber, then the inner player retires itself.
        inner.end_reached.disconnect.assert_called_once_with(player._on_track_ended)
        inner.position_changed.disconnect.assert_called_once_with(
            player.position_changed
        )
        inner.fade_out_and_release.assert_called_once_with(1500)
        inner.stop.assert_not_called()
        inner.release.assert_not_called()
        assert player._player is None
        assert not player.is_playing
        assert player.current_audio_file_id is None

    def test_fade_out_and_release_without_player_is_safe(
        self, db, playlist_with_tracks, mock_engine
    ):
        playlist_id, _ = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)

        player.fade_out_and_release(1500)  # must not raise

        assert not player.is_playing


class TestNextTrack:
    def test_advances_to_next_sequential(self, db, playlist_with_tracks, mock_engine):
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)
        player._is_playing = True
        player._current_index = 0

        played_ids = []
        player._play_file = lambda afid, fade_ms=500: played_ids.append(afid) or True

        player.next_track()
        assert played_ids == [file_ids[1]]

    def test_at_end_no_repeat_stops_and_finishes(
        self, db, playlist_with_tracks, mock_engine
    ):
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine, is_repeat=False)
        player._is_playing = True
        player._current_index = len(file_ids) - 1
        player._current_audio_file_id = file_ids[-1]

        finished = []
        player.playback_finished.connect(lambda: finished.append(True))

        player.next_track()
        assert not player.is_playing
        assert player.current_audio_file_id is None
        assert finished == [True]

    def test_at_end_with_repeat_restarts(self, db, playlist_with_tracks, mock_engine):
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine, is_repeat=True)
        player._is_playing = True
        player._current_index = len(file_ids) - 1

        played_ids = []
        player._play_file = lambda afid, fade_ms=500: played_ids.append(afid) or True

        player.next_track()
        assert played_ids == [file_ids[0]]  # sequential restart -> first track

    def test_noop_when_not_playing(self, db, playlist_with_tracks, mock_engine):
        playlist_id, _ = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)
        player._is_playing = False

        played_ids = []
        player._play_file = lambda afid, fade_ms=500: played_ids.append(afid) or True

        player.next_track()
        assert played_ids == []

    def test_noop_on_empty_playlist(self, db, mock_engine):
        playlist = Playlist(name="Empty")
        playlist_id = db.add_playlist(playlist)
        player = _make_player(playlist_id, db, mock_engine)
        player._is_playing = True  # force the playing guard past

        # No tracks -> nothing to skip to, no crash.
        player.next_track()
        # _audio_file_ids guard short-circuits before any advance attempt.
        assert player._audio_file_ids == []


class TestSkipSafety:
    def test_next_track_releases_current_when_remaining_missing(
        self, db, playlist_with_tracks, mock_engine
    ):
        # A is playing, every later file is missing: a manual skip must STOP A
        # (not leave it audible) while reporting finished.
        playlist_id, file_ids = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)
        player._is_playing = True
        player._current_index = 0
        player._player = MagicMock()  # the currently-audible track
        finished = []
        player.playback_finished.connect(lambda: finished.append(True))

        player._play_file = lambda afid, fade_ms=500: False  # all missing

        player.next_track()
        assert player._player is None  # current track was released
        assert not player.is_playing
        assert finished == [True]

    def test_released_player_end_signal_does_not_advance(
        self, db, playlist_with_tracks, mock_engine
    ):
        # A manual skip can race a just-posted end-of-media. The old player's
        # queued end_reached must not advance the playlist a second time.
        playlist_id, file_ids = playlist_with_tracks
        with patch("app.audio.scene_playlist_player.os.path.exists", return_value=True):
            player = _make_player(playlist_id, db, mock_engine)
            player._is_playing = True
            assert player._play_file(file_ids[0]) is True
            old = player._player
            assert player._play_file(file_ids[1]) is True  # advance; releases old

            advanced = []
            player._play_file = lambda afid, fade_ms=500: advanced.append(afid) or True
            old.end_reached.emit()  # stale signal from the released player

            assert advanced == []  # no spurious advance


class TestPositionAndSeek:
    def test_get_duration_zero_without_player(
        self, db, playlist_with_tracks, mock_engine
    ):
        playlist_id, _ = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)
        assert player.get_duration() == 0

    def test_set_position_noop_without_player(
        self, db, playlist_with_tracks, mock_engine
    ):
        playlist_id, _ = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)
        player.set_position(1000)  # must not raise

    def test_get_duration_and_set_position_delegate(
        self, db, playlist_with_tracks, mock_engine
    ):
        playlist_id, _ = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)
        player._player = MagicMock()
        player._player.get_duration.return_value = 42000

        assert player.get_duration() == 42000
        player.set_position(12345)
        player._player.set_position.assert_called_once_with(12345)

    def test_position_changed_forwarded_from_inner_player(
        self, db, playlist_with_tracks, mock_engine
    ):
        playlist_id, file_ids = playlist_with_tracks
        with patch("app.audio.scene_playlist_player.os.path.exists", return_value=True):
            player = _make_player(playlist_id, db, mock_engine)
            received = []
            player.position_changed.connect(lambda ms: received.append(ms))

            assert player._play_file(file_ids[0]) is True
            player._player.position_changed.emit(4321)

            assert received == [4321]


class TestMissingFiles:
    def test_skips_missing_track_on_advance(
        self, db, playlist_with_tracks, mock_engine
    ):
        playlist_id, file_ids = playlist_with_tracks
        missing_path = "/fake/path/track_1.mp3"
        with patch(
            "app.audio.scene_playlist_player.os.path.exists",
            side_effect=lambda p: p != missing_path,
        ):
            player = _make_player(playlist_id, db, mock_engine)
            player.start()
            assert player.current_audio_file_id == file_ids[0]
            player._on_track_ended()  # track_1 is missing -> skip to track_2
            assert player.current_audio_file_id == file_ids[2]
            assert player.is_playing

    def test_start_skips_missing_first_track(
        self, db, playlist_with_tracks, mock_engine
    ):
        playlist_id, file_ids = playlist_with_tracks
        with patch(
            "app.audio.scene_playlist_player.os.path.exists",
            side_effect=lambda p: p != "/fake/path/track_0.mp3",
        ):
            player = _make_player(playlist_id, db, mock_engine)
            player.start()
            assert player.current_audio_file_id == file_ids[1]

    def test_all_missing_finishes_cleanly(self, db, playlist_with_tracks, mock_engine):
        playlist_id, file_ids = playlist_with_tracks
        finished = []
        with patch(
            "app.audio.scene_playlist_player.os.path.exists",
            return_value=False,
        ):
            player = _make_player(playlist_id, db, mock_engine)
            player.playback_finished.connect(lambda: finished.append(True))
            player.start()
            assert not player.is_playing
            assert player.current_audio_file_id is None
            assert finished == [True]


class TestFadeToVolume:
    def test_fade_to_volume_ramps_live_player(
        self, db, playlist_with_tracks, mock_engine
    ):
        playlist_id, _ = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)
        inner = MagicMock()
        player._player = inner

        player.fade_to_volume(40, duration_ms=1500)

        assert player._volume == 40
        inner.fade_to_volume.assert_called_once_with(40, 1500)

    def test_fade_to_volume_without_player_just_records_level(
        self, db, playlist_with_tracks, mock_engine
    ):
        # The new level must still stick so the next track starts at it.
        playlist_id, _ = playlist_with_tracks
        player = _make_player(playlist_id, db, mock_engine)
        assert player._player is None

        player.fade_to_volume(30)

        assert player._volume == 30


class TestPerTrackVolume:
    """Entry volume must scale by each track's own stored (normalization)
    volume — the entry slider is a master over the playlist's relative levels.

    Real TrackPlayers are used (engine.available=False keeps them silent), so
    target_volume reflects the full setter/fade retargeting path.
    """

    def _player_with_track_volume(
        self, db, playlist_with_tracks, mock_engine, track_volume, entry_volume
    ):
        playlist_id, _ = playlist_with_tracks
        tracks = db.get_playlist_tracks(playlist_id)
        db.update_playlist_track_volume(tracks[0].id, track_volume)
        player = _make_player(playlist_id, db, mock_engine)
        player.set_volume(entry_volume)
        with patch("app.audio.scene_playlist_player.os.path.exists", return_value=True):
            player.start()
        return player

    def test_play_scales_entry_volume_by_track_volume(
        self, qapp, db, playlist_with_tracks, mock_engine
    ):
        player = self._player_with_track_volume(
            db, playlist_with_tracks, mock_engine, track_volume=0.5, entry_volume=80
        )
        assert player._player.target_volume == 40

    def test_set_volume_rescales_current_track(
        self, qapp, db, playlist_with_tracks, mock_engine
    ):
        player = self._player_with_track_volume(
            db, playlist_with_tracks, mock_engine, track_volume=0.5, entry_volume=100
        )
        assert player._player.target_volume == 50

        player.set_volume(60)
        assert player._player.target_volume == 30

    def test_fade_to_volume_rescales_current_track(
        self, qapp, db, playlist_with_tracks, mock_engine
    ):
        player = self._player_with_track_volume(
            db, playlist_with_tracks, mock_engine, track_volume=0.5, entry_volume=100
        )

        player.fade_to_volume(60, duration_ms=500)
        assert player._player.target_volume == 30

    def test_advance_applies_next_tracks_volume(
        self, qapp, db, playlist_with_tracks, mock_engine
    ):
        playlist_id, _ = playlist_with_tracks
        tracks = db.get_playlist_tracks(playlist_id)
        db.update_playlist_track_volume(tracks[1].id, 0.25)
        player = _make_player(playlist_id, db, mock_engine)
        with patch("app.audio.scene_playlist_player.os.path.exists", return_value=True):
            player.start()
            assert player._player.target_volume == 100  # track 0 default

            player.next_track()
        assert player._player.target_volume == 25
