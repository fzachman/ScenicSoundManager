"""Tests for TrackPlayer behavior."""

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QCoreApplication

from app.audio.engine import vlc
from app.audio.player import TrackPlayer


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.available = True
    engine.master_volume = 100
    return engine


@pytest.fixture
def unavailable_engine():
    engine = MagicMock()
    engine.available = False
    engine.master_volume = 100
    return engine


def _make_player(engine, file_path="/fake/track.mp3"):
    return TrackPlayer(file_path, engine=engine)


# ---------------------------------------------------------------------------
# Release (existing tests retained)
# ---------------------------------------------------------------------------


class TestRelease:
    @pytest.mark.skipif(vlc is None, reason="python-vlc not importable")
    def test_release_detaches_all_attached_events(self, mock_engine):
        player = TrackPlayer("/fake/track.mp3", engine=mock_engine)
        events = player.media_player.event_manager.return_value
        attached_types = {c.args[0] for c in events.event_attach.call_args_list}
        media_player = player.media_player

        player.release()

        detached_types = {c.args[0] for c in events.event_detach.call_args_list}
        assert detached_types == attached_types
        assert len(attached_types) == 4
        media_player.release.assert_called_once()
        assert player.media_player is None
        mock_engine.unregister_player.assert_called_once_with(player)

    @pytest.mark.skipif(vlc is None, reason="python-vlc not importable")
    def test_release_is_idempotent(self, mock_engine):
        player = TrackPlayer("/fake/track.mp3", engine=mock_engine)
        player.release()
        player.release()  # second call must not raise


# ---------------------------------------------------------------------------
# Construction wiring
# ---------------------------------------------------------------------------


@pytest.mark.skipif(vlc is None, reason="python-vlc not importable")
class TestConstruction:
    def test_registers_with_engine_on_construction(self, mock_engine):
        player = _make_player(mock_engine)
        mock_engine.register_player.assert_called_once_with(player)

    def test_sets_media_and_applies_initial_volume(self, mock_engine):
        # create_media returns a distinct mock so we can assert it was set
        media = MagicMock()
        mock_engine.create_media.return_value = media
        player = _make_player(mock_engine)
        player.media_player.set_media.assert_called_once_with(media)
        # initial _current_volume is 100, master 100 -> audio_set_volume(100)
        player.media_player.audio_set_volume.assert_any_call(100)

    def test_unavailable_when_create_player_returns_none(self, mock_engine):
        # engine.available True but factory yields no player -> degrade gracefully
        mock_engine.create_player.return_value = None
        player = _make_player(mock_engine)
        assert player.available is False
        assert player.media_player is None
        assert player.media is None
        # never registers a dead player
        mock_engine.register_player.assert_not_called()


# ---------------------------------------------------------------------------
# Volume properties and scaling math
# ---------------------------------------------------------------------------


@pytest.mark.skipif(vlc is None, reason="python-vlc not importable")
class TestVolume:
    def test_target_volume_clamps_high(self, mock_engine):
        player = _make_player(mock_engine)
        player.target_volume = 250
        assert player.target_volume == 100

    def test_target_volume_clamps_low(self, mock_engine):
        player = _make_player(mock_engine)
        player.target_volume = -50
        assert player.target_volume == 0

    def test_target_volume_applies_immediately_when_not_fading(self, mock_engine):
        player = _make_player(mock_engine)
        player.media_player.audio_set_volume.reset_mock()
        player.target_volume = 80
        # master_volume=100 -> effective == base
        player.media_player.audio_set_volume.assert_called_once_with(80)
        assert player._current_volume == 80

    def test_repeat_round_trips(self, mock_engine):
        player = _make_player(mock_engine)
        assert player.repeat is False
        player.repeat = True
        assert player.repeat is True
        player.repeat = False
        assert player.repeat is False

    def test_apply_volume_scales_by_master(self, mock_engine):
        mock_engine.master_volume = 50
        player = _make_player(mock_engine)
        player.media_player.audio_set_volume.reset_mock()
        player._apply_volume(80)
        # int(80 * 50 / 100) == 40
        player.media_player.audio_set_volume.assert_called_once_with(40)

    def test_apply_master_volume_reapplies_current_at_new_scale(self, mock_engine):
        player = _make_player(mock_engine)
        # set a known current volume at master 100
        player.target_volume = 60
        assert player._current_volume == 60
        # master volume changes, then re-apply
        mock_engine.master_volume = 50
        player.media_player.audio_set_volume.reset_mock()
        player.apply_master_volume()
        # int(60 * 50 / 100) == 30
        player.media_player.audio_set_volume.assert_called_once_with(30)


# ---------------------------------------------------------------------------
# Transport: play / pause / stop and position timer
# ---------------------------------------------------------------------------


@pytest.mark.skipif(vlc is None, reason="python-vlc not importable")
class TestTransport:
    def test_play_calls_media_player_and_starts_timer(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player.play()
        player.media_player.play.assert_called_once()
        assert player._position_timer.isActive()

    def test_pause_calls_media_player_and_stops_timer(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player.play()
        assert player._position_timer.isActive()
        player.pause()
        player.media_player.pause.assert_called_once()
        assert not player._position_timer.isActive()

    def test_stop_calls_media_player_and_stops_timer(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player.play()
        assert player._position_timer.isActive()
        player.stop()
        player.media_player.stop.assert_called_once()
        assert not player._position_timer.isActive()


# ---------------------------------------------------------------------------
# Position update emission
# ---------------------------------------------------------------------------


@pytest.mark.skipif(vlc is None, reason="python-vlc not importable")
class TestPositionUpdate:
    def test_update_position_emits_current_position(self, mock_engine):
        player = _make_player(mock_engine)
        player.media_player.get_time.return_value = 2500
        received = []
        player.position_changed.connect(received.append)
        player._update_position()
        assert received == [2500]

    def test_update_position_suppresses_negative_position(self, mock_engine):
        # VLC returns -1 when position is unknown; that must not be emitted.
        player = _make_player(mock_engine)
        player.media_player.get_time.return_value = -1
        received = []
        player.position_changed.connect(received.append)
        player._update_position()
        assert received == []


# ---------------------------------------------------------------------------
# Delegation to media_player
# ---------------------------------------------------------------------------


@pytest.mark.skipif(vlc is None, reason="python-vlc not importable")
class TestDelegation:
    def test_is_playing_delegates(self, mock_engine):
        player = _make_player(mock_engine)
        player.media_player.is_playing.return_value = True
        assert player.is_playing() is True
        player.media_player.is_playing.return_value = False
        assert player.is_playing() is False

    def test_get_position_delegates_to_get_time(self, mock_engine):
        player = _make_player(mock_engine)
        player.media_player.get_time.return_value = 4321
        assert player.get_position() == 4321

    def test_get_duration_delegates_to_get_length(self, mock_engine):
        player = _make_player(mock_engine)
        player.media_player.get_length.return_value = 99999
        assert player.get_duration() == 99999

    def test_get_state_delegates(self, mock_engine):
        player = _make_player(mock_engine)
        sentinel = object()
        player.media_player.get_state.return_value = sentinel
        assert player.get_state() is sentinel

    def test_set_position_calls_set_time(self, mock_engine):
        player = _make_player(mock_engine)
        player.set_position(7500)
        player.media_player.set_time.assert_called_once_with(7500)


# ---------------------------------------------------------------------------
# Fades
# ---------------------------------------------------------------------------


def _drive_fade_to_completion(player):
    """Manually step a fade until it ends."""
    # Guard against infinite loop; 20 steps expected.
    for _ in range(100):
        if not player._is_fading():
            break
        player._fade_step()


@pytest.mark.skipif(vlc is None, reason="python-vlc not importable")
class TestFades:
    def test_fade_in_resets_volume_plays_and_fades(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player.target_volume = 90
        player.media_player.play.reset_mock()

        player.fade_in(duration_ms=1000)

        # starts playback
        player.media_player.play.assert_called_once()
        # fade is in progress immediately after starting
        assert player._is_fading()

        _drive_fade_to_completion(player)

        assert not player._is_fading()
        assert player._current_volume == 90

    def test_fade_in_does_not_play_when_start_playing_false(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player.media_player.play.reset_mock()
        player.fade_in(duration_ms=1000, start_playing=False)
        player.media_player.play.assert_not_called()
        assert player._is_fading()

    def test_fade_out_pauses_after_completion(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player.target_volume = 100
        player.media_player.pause.reset_mock()

        player.fade_out(duration_ms=1000, pause_after=True)
        assert player._is_fading()
        # pause should not have happened yet
        player.media_player.pause.assert_not_called()

        _drive_fade_to_completion(player)

        assert not player._is_fading()
        player.media_player.pause.assert_called_once()
        assert player._current_volume == 0

    def test_fade_out_no_pause_when_pause_after_false(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player.target_volume = 100
        player.media_player.pause.reset_mock()

        player.fade_out(duration_ms=1000, pause_after=False)
        _drive_fade_to_completion(player)

        player.media_player.pause.assert_not_called()
        assert player._current_volume == 0

    def test_fade_to_volume_updates_target_and_fades_toward_it(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player.target_volume = 100
        # set current to a known high value (not fading)
        assert player._current_volume == 100

        player.fade_to_volume(40, duration_ms=500)
        assert player.target_volume == 40
        assert player._is_fading()

        _drive_fade_to_completion(player)
        assert not player._is_fading()
        assert player._current_volume == 40

    def test_fade_to_volume_clamps(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player.fade_to_volume(500, duration_ms=500)
        assert player.target_volume == 100

    def test_target_volume_mid_fade_retargets_without_snapping(self, qapp, mock_engine):
        # A slider drag during a fade (e.g. a preset transition ramp) must
        # win: the fade retargets from its current level instead of either
        # snapping audibly or being silently discarded.
        player = _make_player(mock_engine)
        player.fade_to_volume(0, duration_ms=1000)
        assert player._is_fading()
        before = player._current_volume
        player.media_player.audio_set_volume.reset_mock()

        player.target_volume = 70

        assert player.target_volume == 70
        assert player._current_volume == before  # no snap
        player.media_player.audio_set_volume.assert_not_called()
        assert player._is_fading()

        _drive_fade_to_completion(player)
        assert player._current_volume == 70

    def test_target_volume_mid_fade_preserves_pending_pause(self, qapp, mock_engine):
        # Retargeting during a fade-out must not cancel the pause it was
        # going to perform, or a track could keep playing in a paused scene.
        player = _make_player(mock_engine)
        player.fade_out(duration_ms=1000, pause_after=True)
        player.media_player.pause.reset_mock()

        player.target_volume = 70
        _drive_fade_to_completion(player)

        player.media_player.pause.assert_called_once()


# ---------------------------------------------------------------------------
# End-reached handling
# ---------------------------------------------------------------------------


@pytest.mark.skipif(vlc is None, reason="python-vlc not importable")
class TestEndReached:
    def test_handle_end_reached_emits_signal(self, mock_engine):
        player = _make_player(mock_engine)
        emitted = []
        player.end_reached.connect(lambda: emitted.append(True))
        player._handle_end_reached()
        assert emitted == [True]

    def test_handle_end_reached_restarts_when_repeat(self, mock_engine):
        player = _make_player(mock_engine)
        player.repeat = True
        player.media_player.stop.reset_mock()
        player.media_player.play.reset_mock()

        player._handle_end_reached()

        player.media_player.stop.assert_called_once()
        player.media_player.play.assert_called_once()

    def test_handle_end_reached_does_not_restart_without_repeat(self, mock_engine):
        player = _make_player(mock_engine)
        player.repeat = False
        player.media_player.stop.reset_mock()
        player.media_player.play.reset_mock()

        player._handle_end_reached()

        player.media_player.stop.assert_not_called()
        player.media_player.play.assert_not_called()

    def test_handle_end_reached_with_repeat_after_release_is_safe(self, mock_engine):
        # repeat=True but player already released -> must still emit, not raise
        player = _make_player(mock_engine)
        player.repeat = True
        player.release()
        assert player.media_player is None
        emitted = []
        player.end_reached.connect(lambda: emitted.append(True))
        player._handle_end_reached()  # must not raise on None media_player
        assert emitted == [True]

    def test_on_end_reached_schedules_handler_via_single_shot(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        emitted = []
        player.end_reached.connect(lambda: emitted.append(True))

        # _on_end_reached uses QTimer.singleShot(0, ...) -> deferred
        player._on_end_reached(event=None)
        assert emitted == []  # not yet
        QCoreApplication.processEvents()
        assert emitted == [True]


# ---------------------------------------------------------------------------
# State-change handling
# ---------------------------------------------------------------------------


@pytest.mark.skipif(vlc is None, reason="python-vlc not importable")
class TestStateChange:
    def test_on_state_change_emits_captured_state(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player.media_player.get_state.return_value = 3  # arbitrary VLC state int

        received = []
        player.state_changed.connect(lambda s: received.append(s))

        player._on_state_change(event=None)
        # Deferred via singleShot
        assert received == []
        QCoreApplication.processEvents()
        assert received == [3]

    def test_on_state_change_captures_state_at_call_time(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player.media_player.get_state.return_value = 4

        received = []
        player.state_changed.connect(lambda s: received.append(s))

        player._on_state_change(event=None)
        # Mutate state after capture but before delivery; emitted value must be
        # the captured one (4), not the new one.
        player.media_player.get_state.return_value = 5
        QCoreApplication.processEvents()
        assert received == [4]


# ---------------------------------------------------------------------------
# Degraded path: engine unavailable
# ---------------------------------------------------------------------------


class TestUnavailableEngine:
    def test_media_player_is_none(self, unavailable_engine):
        player = _make_player(unavailable_engine)
        assert player.media_player is None
        assert player.available is False

    def test_transport_is_noop(self, qapp, unavailable_engine):
        player = _make_player(unavailable_engine)
        # None of these should raise
        player.play()
        player.pause()
        player.stop()
        player.set_position(1000)

    def test_query_methods_return_defaults(self, unavailable_engine):
        player = _make_player(unavailable_engine)
        assert player.is_playing() is False
        assert player.get_position() == 0
        assert player.get_duration() == 0
        assert player.get_state() is None

    def test_apply_volume_is_safe_noop(self, unavailable_engine):
        player = _make_player(unavailable_engine)
        # Should not raise even though media_player is None
        player._apply_volume(50)
        player.apply_master_volume()

    def test_release_is_idempotent_and_safe(self, unavailable_engine):
        player = _make_player(unavailable_engine)
        player.release()
        player.release()
        unavailable_engine.unregister_player.assert_called_with(player)


# ---------------------------------------------------------------------------
# Ended-state revive (scrub / repeat-toggle after a non-repeat track finishes)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(vlc is None, reason="python-vlc not importable")
class TestEndedRevive:
    def test_end_without_repeat_marks_ended_and_stops_position_timer(
        self, qapp, mock_engine
    ):
        player = _make_player(mock_engine)
        player.play()
        assert player._position_timer.isActive()

        player._handle_end_reached()

        assert player.has_ended is True
        assert player._position_timer.isActive() is False

    def test_end_with_repeat_restarts_and_does_not_mark_ended(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player.repeat = True

        player._handle_end_reached()

        assert player.has_ended is False
        player.media_player.stop.assert_called_once()
        player.media_player.play.assert_called_once()

    def test_set_position_on_ended_player_restarts_at_that_spot(
        self, qapp, mock_engine
    ):
        # VLC parks an ended player where set_time() is silently dropped, so
        # a scrub must stop+play and defer the seek until playback is live.
        player = _make_player(mock_engine)
        player._handle_end_reached()

        player.set_position(30_000)

        assert player.has_ended is False
        assert player._position_timer.isActive()
        player.media_player.stop.assert_called_once()
        player.media_player.play.assert_called_once()
        player.media_player.set_time.assert_not_called()

        player.media_player.is_playing.return_value = True
        player.media_player.get_time.return_value = 0
        player._update_position()
        player.media_player.set_time.assert_called_once_with(30_000)

        # Once VLC reports the target position, the pending seek is done.
        player.media_player.get_time.return_value = 30_000
        player._update_position()
        assert player._pending_seek_ms is None

    def test_pending_seek_retries_until_vlc_confirms_it(self, qapp, mock_engine):
        # A set_time issued the moment VLC starts playing can still be
        # dropped (MP3 demuxer isn't seek-ready yet) — keep re-issuing.
        player = _make_player(mock_engine)
        player._handle_end_reached()
        player.set_position(30_000)
        player.media_player.is_playing.return_value = True
        player.media_player.get_time.return_value = 0

        for _ in range(3):
            player._update_position()

        assert player.media_player.set_time.call_count == 3
        player.media_player.set_time.assert_called_with(30_000)

    def test_pending_seek_gives_up_after_bounded_attempts(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player._handle_end_reached()
        player.set_position(30_000)
        player.media_player.is_playing.return_value = True
        player.media_player.get_time.return_value = 0

        for _ in range(30):
            player._update_position()

        assert player._pending_seek_ms is None
        assert player.media_player.set_time.call_count <= 21

    def test_position_emissions_suppressed_while_seek_pending(self, qapp, mock_engine):
        # The pre-seek 0-position ticks must not yank the scrubber back.
        player = _make_player(mock_engine)
        player._handle_end_reached()
        player.set_position(30_000)
        player.media_player.is_playing.return_value = True
        player.media_player.get_time.return_value = 0
        emissions = []
        player.position_changed.connect(emissions.append)

        player._update_position()
        assert emissions == []

        player.media_player.get_time.return_value = 30_000
        player._update_position()  # seek confirmed -> emits the real position
        player._update_position()  # normal ticks resume
        assert emissions == [30_000, 30_000]

    def test_playing_state_change_issues_pending_seek_early(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player._handle_end_reached()
        player.set_position(30_000)
        player.media_player.is_playing.return_value = True
        player.media_player.get_time.return_value = 0

        player._handle_state_change(vlc.State.Playing)

        player.media_player.set_time.assert_called_once_with(30_000)

    def test_newer_seek_supersedes_pending_revive_seek(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player._handle_end_reached()
        player.set_position(30_000)
        player.media_player.is_playing.return_value = True
        player.media_player.get_time.return_value = 0

        player.set_position(60_000)  # user scrubs again before it lands
        player._update_position()

        player.media_player.set_time.assert_called_once_with(60_000)

    def test_set_position_while_not_ended_seeks_directly(self, qapp, mock_engine):
        player = _make_player(mock_engine)

        player.set_position(5_000)

        player.media_player.set_time.assert_called_once_with(5_000)
        player.media_player.stop.assert_not_called()

    def test_stop_clears_ended_state_and_pending_seek(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player._handle_end_reached()
        player.set_position(30_000)

        player.stop()

        assert player.has_ended is False
        assert player._pending_seek_ms is None
        player.media_player.is_playing.return_value = True
        player.media_player.get_time.return_value = 0
        player._update_position()
        player.media_player.set_time.assert_not_called()

    def test_restart_reapplies_current_volume(self, qapp, mock_engine):
        player = _make_player(mock_engine)
        player.target_volume = 40
        player.media_player.audio_set_volume.reset_mock()
        player._handle_end_reached()

        player.restart()

        player.media_player.audio_set_volume.assert_called_once_with(40)
