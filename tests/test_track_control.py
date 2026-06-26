"""Tests for TrackControl volume persistence behavior.

Volume must update live on every slider tick, but only emit volume_committed
(the persistence signal) once the value settles — on release for a drag, or
immediately for a discrete keyboard/wheel change.
"""

import pytest

from app.database import AudioFile, SceneAudioFile
from app.scenes.track_control import TrackControl


@pytest.fixture
def track():
    af = AudioFile(file_path="/fake/track.mp3", title="Track", duration_seconds=120.0)
    return SceneAudioFile(
        id=7, scene_id=1, audio_file_id=1, position=0, volume=0.5, audio_file=af
    )


def _capture(control):
    live, committed = [], []
    control.volume_changed.connect(lambda tid, v: live.append((tid, v)))
    control.volume_committed.connect(lambda tid, v: committed.append((tid, v)))
    return live, committed


class TestVolumeCommit:
    def test_discrete_change_commits_immediately(self, qapp, track):
        control = TrackControl(track)
        live, committed = _capture(control)

        # A programmatic/keyboard/wheel change happens with the handle up.
        control.volume_slider.setValue(80)

        assert live[-1][0] == 7 and live[-1][1] == pytest.approx(0.8)
        assert committed[-1][0] == 7 and committed[-1][1] == pytest.approx(0.8)

    def test_drag_defers_commit_until_release(self, qapp, track):
        control = TrackControl(track)
        live, committed = _capture(control)

        # Simulate an in-progress drag: handle down, value moving.
        control.volume_slider.setSliderDown(True)
        control.volume_slider.setValue(30)
        control.volume_slider.setValue(20)

        # Live updates fired for each tick...
        assert (7, pytest.approx(0.3)) in live
        assert (7, pytest.approx(0.2)) in live
        # ...but nothing persisted yet.
        assert committed == []

        # Release persists exactly once, with the final value.
        control.volume_slider.sliderReleased.emit()
        assert len(committed) == 1
        assert committed[0][0] == 7 and committed[0][1] == pytest.approx(0.2)

    def test_in_memory_volume_stays_fresh(self, qapp, track):
        # Playback setup reads track.volume directly, so the in-memory model
        # must reflect the current slider value even mid-drag (before commit).
        control = TrackControl(track)
        assert control.track is track

        control.volume_slider.setValue(80)  # discrete
        assert track.volume == pytest.approx(0.8)

        control.volume_slider.setSliderDown(True)  # mid-drag, not yet committed
        control.volume_slider.setValue(30)
        assert track.volume == pytest.approx(0.3)
