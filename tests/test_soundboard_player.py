"""Tests for SoundboardPlayer - the single-slot one-shot player (Plan 008).

TrackPlayer is patched with a factory (pattern from test_mixer.py): each
instantiation returns a real TrackPlayer QObject (safe: the mock engine has
available=False so no VLC is touched) with its playback methods replaced by
MagicMocks, so the slot's create/reuse/release behavior is observable and
end_reached can be emitted as a real signal.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.audio.player import TrackPlayer
from app.audio.soundboard_player import SoundboardPlayer


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.available = False
    engine.master_volume = 100
    return engine


@pytest.fixture
def patched_track_player(qapp):
    instances = []

    def _factory(file_path, engine):
        player = TrackPlayer(file_path, engine)
        player.play = MagicMock(name="play")
        player.stop = MagicMock(name="stop")
        player.release = MagicMock(name="release")
        player.is_playing = MagicMock(name="is_playing", return_value=False)
        instances.append(player)
        return player

    with patch(
        "app.audio.soundboard_player.TrackPlayer", side_effect=_factory
    ) as mock_cls:
        mock_cls.instances = instances
        yield mock_cls


@pytest.fixture(autouse=True)
def existing_files(monkeypatch):
    """Button file paths exist unless a test says otherwise."""
    monkeypatch.setattr("app.audio.soundboard_player.os.path.exists", lambda path: True)


@pytest.fixture
def player(mock_engine, patched_track_player):
    return SoundboardPlayer(engine=mock_engine)


@pytest.fixture
def events(player):
    """Ordered log of (signal, button_id) emissions."""
    log = []
    player.button_started.connect(lambda bid: log.append(("started", bid)))
    player.button_stopped.connect(lambda bid: log.append(("stopped", bid)))
    return log


class TestTrigger:
    def test_trigger_plays_with_button_volume(
        self, player, patched_track_player, events
    ):
        player.trigger(5, "/sfx/sword.mp3", volume=0.29)
        assert patched_track_player.call_count == 1
        instance = patched_track_player.instances[0]
        assert instance.file_path == "/sfx/sword.mp3"
        assert instance.target_volume == 29
        instance.play.assert_called_once()
        assert player.current_button_id == 5
        assert events == [("started", 5)]

    def test_trigger_defaults_to_full_volume(self, player, patched_track_player):
        player.trigger(5, "/sfx/sword.mp3")
        assert patched_track_player.instances[0].target_volume == 100

    def test_missing_file_is_skipped(
        self, player, patched_track_player, events, monkeypatch
    ):
        monkeypatch.setattr(
            "app.audio.soundboard_player.os.path.exists", lambda path: False
        )
        player.trigger(5, "/gone/sword.mp3")
        assert patched_track_player.call_count == 0
        assert player.current_button_id is None
        assert events == []


class TestCutOver:
    def test_different_button_stops_old_and_plays_new(
        self, player, patched_track_player, events
    ):
        player.trigger(5, "/sfx/sword.mp3")
        old = patched_track_player.instances[0]
        old.is_playing.return_value = True

        player.trigger(9, "/sfx/thunder.mp3")

        old.release.assert_called_once()
        assert patched_track_player.call_count == 2
        patched_track_player.instances[1].play.assert_called_once()
        assert player.current_button_id == 9
        # Old button's stopped lands before the new button's started.
        assert events == [("started", 5), ("stopped", 5), ("started", 9)]


class TestSameButton:
    def test_second_press_stops(self, player, patched_track_player, events):
        player.trigger(5, "/sfx/sword.mp3")
        instance = patched_track_player.instances[0]
        instance.is_playing.return_value = True

        player.trigger(5, "/sfx/sword.mp3")

        instance.release.assert_called_once()
        assert patched_track_player.call_count == 1  # no new player
        assert player.current_button_id is None
        assert not player.is_playing()
        assert events == [("started", 5), ("stopped", 5)]

    def test_press_after_natural_end_plays_again(
        self, player, patched_track_player, events
    ):
        player.trigger(5, "/sfx/sword.mp3")
        patched_track_player.instances[0].end_reached.emit()

        player.trigger(5, "/sfx/sword.mp3")

        assert patched_track_player.call_count == 2
        patched_track_player.instances[1].play.assert_called_once()
        assert events == [("started", 5), ("stopped", 5), ("started", 5)]


class TestNaturalEnd:
    def test_end_reached_empties_slot_and_signals(
        self, player, patched_track_player, events
    ):
        player.trigger(5, "/sfx/sword.mp3")
        instance = patched_track_player.instances[0]

        instance.end_reached.emit()

        instance.release.assert_called_once()
        assert player.current_button_id is None
        assert events == [("started", 5), ("stopped", 5)]


class TestStopAndClear:
    def test_stop_releases_and_signals(self, player, patched_track_player, events):
        player.trigger(5, "/sfx/sword.mp3")
        player.stop()
        patched_track_player.instances[0].release.assert_called_once()
        assert player.current_button_id is None
        assert events == [("started", 5), ("stopped", 5)]

    def test_stop_when_idle_is_silent(self, player, events):
        player.stop()
        assert events == []

    def test_clear_releases_without_signals(self, player, patched_track_player, events):
        player.trigger(5, "/sfx/sword.mp3")
        player.clear()
        patched_track_player.instances[0].release.assert_called_once()
        assert player.current_button_id is None
        assert events == [("started", 5)]  # no stopped signal on teardown

    def test_release_disconnects_end_reached(self, player, patched_track_player):
        # A late end_reached from a released player must not signal or touch
        # the slot the next sound occupies.
        player.trigger(5, "/sfx/sword.mp3")
        old = patched_track_player.instances[0]
        player.trigger(9, "/sfx/thunder.mp3")

        old.end_reached.emit()

        assert player.current_button_id == 9


class TestVolume:
    def test_set_current_volume_applies_to_playing_button(
        self, player, patched_track_player
    ):
        player.trigger(5, "/sfx/sword.mp3")
        player.set_current_volume(5, 0.5)
        assert patched_track_player.instances[0].target_volume == 50

    def test_set_current_volume_ignores_other_buttons(
        self, player, patched_track_player
    ):
        player.trigger(5, "/sfx/sword.mp3", volume=0.8)
        player.set_current_volume(9, 0.1)
        assert patched_track_player.instances[0].target_volume == 80

    def test_set_current_volume_when_idle_is_noop(self, player):
        player.set_current_volume(5, 0.5)  # must not raise


class TestIsPlaying:
    def test_delegates_to_player(self, player, patched_track_player):
        assert not player.is_playing()
        player.trigger(5, "/sfx/sword.mp3")
        patched_track_player.instances[0].is_playing.return_value = True
        assert player.is_playing()
