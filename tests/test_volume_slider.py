"""Isolation tests for the reusable VolumeSlider component.

VolumeSlider owns the commit-on-release contract: ``changed`` fires on every
tick (live), ``committed`` only when the value settles (discrete change, or
slider release after a drag). The owning control re-emits its own id-bearing
signals from these.
"""

import pytest

from app.shared.volume_slider import VolumeSlider
from tests.control_helpers import record


class TestConstruction:
    def test_initial_slider_and_label(self, qapp):
        vs = VolumeSlider(0.5)
        assert vs.slider.value() == 50
        assert vs.value_label.text() == "50%"


class TestLiveChanged:
    def test_changed_fires_every_tick(self, qapp):
        vs = VolumeSlider(0.5)
        rec = record(vs.changed)

        vs.slider.setValue(30)
        vs.slider.setValue(20)

        assert rec[0] == pytest.approx((0.3,))
        assert rec[1] == pytest.approx((0.2,))

    def test_label_updates_live(self, qapp):
        vs = VolumeSlider(0.5)
        vs.slider.setValue(33)
        assert vs.value_label.text() == "33%"


class TestCommit:
    def test_discrete_change_commits_immediately(self, qapp):
        vs = VolumeSlider(0.5)
        rec = record(vs.committed)

        vs.slider.setValue(80)  # handle up -> discrete change

        assert len(rec) == 1
        assert rec[0] == pytest.approx((0.8,))

    def test_commit_deferred_until_release_during_drag(self, qapp):
        vs = VolumeSlider(0.5)
        rec = record(vs.committed)

        vs.slider.setSliderDown(True)
        vs.slider.setValue(30)
        vs.slider.setValue(20)
        assert rec == []  # nothing committed mid-drag

        vs.slider.sliderReleased.emit()
        assert len(rec) == 1
        assert rec[0] == pytest.approx((0.2,))
