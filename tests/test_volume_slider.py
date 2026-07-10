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

    def test_initial_value_rounds_not_truncates(self, qapp):
        # 0.29 * 100 == 28.9999...; must round to 29, so a saved 29% reloads as
        # 29%, not 28%.
        vs = VolumeSlider(0.29)
        assert vs.slider.value() == 29
        assert vs.value_label.text() == "29%"


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


class TestSilentSet:
    def test_set_volume_silently_emits_nothing(self, qapp):
        vs = VolumeSlider(0.5)
        changed = record(vs.changed)
        committed = record(vs.committed)

        vs.set_volume_silently(0.8)

        assert changed == []
        assert committed == []
        assert vs.slider.value() == 80
        assert vs.value_label.text() == "80%"

    def test_set_volume_silently_rounds_not_truncates(self, qapp):
        vs = VolumeSlider(0.5)
        vs.set_volume_silently(0.29)
        assert vs.slider.value() == 29
        assert vs.value_label.text() == "29%"
