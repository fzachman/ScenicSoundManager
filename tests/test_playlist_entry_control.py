"""Tests for PlaylistEntryControl volume persistence behavior.

Mirrors TrackControl: volume updates live on every slider tick, but
volume_committed (the persistence signal) only fires once the value settles —
on release for a drag, or immediately for a discrete keyboard/wheel change.
"""

import pytest

from app.database import ScenePlaylistEntry
from app.scenes.playlist_entry_control import PlaylistEntryControl


@pytest.fixture
def entry():
    # playlist=None is rendered as "Unknown Playlist"; fine for this test.
    return ScenePlaylistEntry(id=9, scene_id=1, playlist_id=1, volume=0.5)


def _capture(control):
    live, committed = [], []
    control.volume_changed.connect(lambda eid, v: live.append((eid, v)))
    control.volume_committed.connect(lambda eid, v: committed.append((eid, v)))
    return live, committed


class TestVolumeCommit:
    def test_discrete_change_commits_immediately(self, qapp, entry):
        control = PlaylistEntryControl(entry)
        live, committed = _capture(control)

        control.volume_slider.setValue(80)

        assert live[-1][0] == 9 and live[-1][1] == pytest.approx(0.8)
        assert committed[-1][0] == 9 and committed[-1][1] == pytest.approx(0.8)

    def test_drag_defers_commit_until_release(self, qapp, entry):
        control = PlaylistEntryControl(entry)
        live, committed = _capture(control)

        control.volume_slider.setSliderDown(True)
        control.volume_slider.setValue(30)
        control.volume_slider.setValue(20)

        assert (9, pytest.approx(0.3)) in live
        assert (9, pytest.approx(0.2)) in live
        assert committed == []

        control.volume_slider.sliderReleased.emit()
        assert len(committed) == 1
        assert committed[0][0] == 9 and committed[0][1] == pytest.approx(0.2)

    def test_in_memory_volume_stays_fresh(self, qapp, entry):
        control = PlaylistEntryControl(entry)
        assert control.entry is entry

        control.volume_slider.setValue(80)  # discrete
        assert entry.volume == pytest.approx(0.8)

        control.volume_slider.setSliderDown(True)  # mid-drag, not yet committed
        control.volume_slider.setValue(30)
        assert entry.volume == pytest.approx(0.3)
