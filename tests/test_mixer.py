"""Tests for SceneMixer - managing multiple TrackPlayers for a scene.

TrackPlayer is patched with a MagicMock factory so the mixer is isolated
from real audio/VLC. Each patched instantiation returns a fresh MagicMock,
letting us assert delegation and control is_playing() return values.
"""

from unittest.mock import patch, MagicMock

import pytest

from app.audio.mixer import SceneMixer
from app.audio.player import TrackPlayer


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.available = False
    engine.master_volume = 100
    return engine


@pytest.fixture
def patched_track_player(qapp):
    # qapp: a live QApplication is required to construct real TrackPlayer
    # QObjects (and for any QTimer machinery they set up internally).
    """Patch SceneMixer's TrackPlayer with a factory.

    The factory records the (file_path, engine) args of each instantiation
    and returns a distinct MagicMock per call (with is_playing() defaulting
    to False) so the mixer's behavior can be observed.
    """
    instances = []

    def _factory(file_path, engine):
        # The track_added signal is typed pyqtSignal(int, TrackPlayer); PyQt
        # enforces that the emitted object is a genuine, fully-constructed
        # TrackPlayer (QObject). Build a real instance — safe because the mock
        # engine has available=False, so __init__ makes no VLC calls — then
        # replace its methods with MagicMocks to observe the mixer's delegation.
        player = TrackPlayer(file_path, engine)
        player.fade_in = MagicMock(name="fade_in")
        player.fade_out = MagicMock(name="fade_out")
        player.stop = MagicMock(name="stop")
        player.release = MagicMock(name="release")
        player.is_playing = MagicMock(name="is_playing", return_value=False)
        instances.append(player)
        return player

    with patch("app.audio.mixer.TrackPlayer", side_effect=_factory) as mock_cls:
        mock_cls.instances = instances
        yield mock_cls


@pytest.fixture
def mixer(mock_engine, patched_track_player):
    return SceneMixer(engine=mock_engine)


class TestAddTrack:
    def test_instantiates_player_with_path_and_engine(self, mixer, mock_engine, patched_track_player):
        player = mixer.add_track(1, "/fake/a.mp3")

        patched_track_player.assert_called_once_with("/fake/a.mp3", mock_engine)
        assert player is patched_track_player.instances[0]
        assert player.file_path == "/fake/a.mp3"
        assert player.engine is mock_engine

    def test_stores_player_under_track_id_and_returns_it(self, mixer):
        player = mixer.add_track(7, "/fake/a.mp3")

        assert mixer.get_player(7) is player

    def test_emits_track_added_with_id_and_player(self, mixer):
        received = []
        mixer.track_added.connect(lambda tid, p: received.append((tid, p)))

        player = mixer.add_track(3, "/fake/a.mp3")

        assert received == [(3, player)]

    def test_existing_id_removes_prior_player_first(self, mixer, patched_track_player):
        first = mixer.add_track(5, "/fake/old.mp3")

        removed = []
        mixer.track_removed.connect(lambda tid: removed.append(tid))

        second = mixer.add_track(5, "/fake/new.mp3")

        # Old player released and a track_removed emitted before the new add
        first.release.assert_called_once()
        assert removed == [5]
        # New player is the stored one and distinct from the first
        assert second is not first
        assert mixer.get_player(5) is second
        assert second.file_path == "/fake/new.mp3"


class TestRemoveTrack:
    def test_pops_releases_and_emits(self, mixer):
        player = mixer.add_track(2, "/fake/a.mp3")
        removed = []
        mixer.track_removed.connect(lambda tid: removed.append(tid))

        mixer.remove_track(2)

        player.release.assert_called_once()
        assert mixer.get_player(2) is None
        assert removed == [2]

    def test_absent_id_is_noop_no_emit(self, mixer):
        removed = []
        mixer.track_removed.connect(lambda tid: removed.append(tid))

        mixer.remove_track(999)  # never added

        assert removed == []


class TestGetters:
    def test_get_player_returns_stored_or_none(self, mixer):
        player = mixer.add_track(1, "/fake/a.mp3")
        assert mixer.get_player(1) is player
        assert mixer.get_player(42) is None

    def test_get_all_players_returns_copy(self, mixer):
        p1 = mixer.add_track(1, "/fake/a.mp3")
        p2 = mixer.add_track(2, "/fake/b.mp3")

        snapshot = mixer.get_all_players()
        assert snapshot == {1: p1, 2: p2}

        # Mutating the returned dict must not affect mixer internal state
        snapshot.clear()
        snapshot[99] = "garbage"
        assert mixer.get_all_players() == {1: p1, 2: p2}
        assert mixer.get_player(1) is p1


class TestPlaybackControls:
    def test_play_all_fades_in_every_player(self, mixer):
        p1 = mixer.add_track(1, "/fake/a.mp3")
        p2 = mixer.add_track(2, "/fake/b.mp3")

        mixer.play_all(2500)

        p1.fade_in.assert_called_once_with(2500)
        p2.fade_in.assert_called_once_with(2500)

    def test_play_all_uses_default_duration_when_omitted(self, mixer):
        p1 = mixer.add_track(1, "/fake/a.mp3")

        mixer.play_all()  # default fade_duration_ms == 1000

        p1.fade_in.assert_called_once_with(1000)

    def test_play_all_empty_is_noop(self, mixer):
        # No players: must not raise (covers the empty-iteration branch).
        mixer.play_all(1000)

    def test_pause_all_fades_out_with_pause_after(self, mixer):
        p1 = mixer.add_track(1, "/fake/a.mp3")
        p2 = mixer.add_track(2, "/fake/b.mp3")

        mixer.pause_all(1500)

        p1.fade_out.assert_called_once_with(1500, pause_after=True)
        p2.fade_out.assert_called_once_with(1500, pause_after=True)

    def test_stop_all_stops_every_player_and_emits(self, mixer):
        p1 = mixer.add_track(1, "/fake/a.mp3")
        p2 = mixer.add_track(2, "/fake/b.mp3")

        stopped_signals = []
        mixer.all_stopped.connect(lambda: stopped_signals.append(True))

        mixer.stop_all()

        p1.stop.assert_called_once_with()
        p2.stop.assert_called_once_with()
        assert stopped_signals == [True]


class TestIsAnyPlaying:
    def test_true_when_some_player_playing(self, mixer):
        p1 = mixer.add_track(1, "/fake/a.mp3")
        p2 = mixer.add_track(2, "/fake/b.mp3")
        p1.is_playing.return_value = False
        p2.is_playing.return_value = True

        assert mixer.is_any_playing() is True

    def test_false_when_all_players_stopped(self, mixer):
        p1 = mixer.add_track(1, "/fake/a.mp3")
        p2 = mixer.add_track(2, "/fake/b.mp3")
        p1.is_playing.return_value = False
        p2.is_playing.return_value = False

        assert mixer.is_any_playing() is False

    def test_false_when_empty(self, mixer):
        assert mixer.is_any_playing() is False


class TestPerTrackSettings:
    def test_set_track_volume_sets_target_volume(self, mixer):
        player = mixer.add_track(1, "/fake/a.mp3")

        mixer.set_track_volume(1, 42)

        assert player.target_volume == 42

    def test_set_track_volume_clamps_to_real_property_bounds(self, mixer):
        # target_volume is a real clamping property (max(0, min(100, value))).
        # Driving it through the mixer exercises that production clamp.
        player = mixer.add_track(1, "/fake/a.mp3")

        mixer.set_track_volume(1, 150)
        assert player.target_volume == 100

        mixer.set_track_volume(1, -25)
        assert player.target_volume == 0

    def test_set_track_volume_absent_does_not_touch_other_players(self, mixer):
        # Must not raise on unknown id, and must not mutate existing players.
        existing = mixer.add_track(1, "/fake/a.mp3")
        existing.target_volume = 30

        mixer.set_track_volume(999, 50)

        assert existing.target_volume == 30  # untouched

    def test_set_track_repeat_sets_repeat(self, mixer):
        player = mixer.add_track(1, "/fake/a.mp3")
        assert player.repeat is False  # real default before mutation

        mixer.set_track_repeat(1, True)
        assert player.repeat is True

        # And can be turned back off (covers the False branch of the value).
        mixer.set_track_repeat(1, False)
        assert player.repeat is False

    def test_set_track_repeat_absent_does_not_touch_other_players(self, mixer):
        existing = mixer.add_track(1, "/fake/a.mp3")
        existing.repeat = True

        mixer.set_track_repeat(999, True)  # unknown id: no-op, no raise

        assert existing.repeat is True


class TestMasterVolume:
    def test_getter_delegates_to_engine(self, mixer, mock_engine):
        mock_engine.master_volume = 73
        assert mixer.master_volume == 73

    def test_setter_assigns_to_engine(self, mixer, mock_engine):
        mixer.master_volume = 25
        assert mock_engine.master_volume == 25


class TestClearAndRelease:
    def test_clear_removes_and_releases_all(self, mixer):
        p1 = mixer.add_track(1, "/fake/a.mp3")
        p2 = mixer.add_track(2, "/fake/b.mp3")

        removed = []
        mixer.track_removed.connect(lambda tid: removed.append(tid))

        mixer.clear()

        p1.release.assert_called_once()
        p2.release.assert_called_once()
        assert mixer.get_all_players() == {}
        assert sorted(removed) == [1, 2]

    def test_release_clears_all_tracks(self, mixer):
        p1 = mixer.add_track(1, "/fake/a.mp3")

        mixer.release()

        p1.release.assert_called_once()
        assert mixer.get_all_players() == {}
