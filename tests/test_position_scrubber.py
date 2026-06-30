"""Isolation tests for the reusable PositionScrubber component.

PositionScrubber owns the drag-aware scrubber contract: ``set_progress`` moves
the slider/label from the player's clock, but is ignored while the user holds
the handle; releasing emits ``seek`` with a 0..1 fraction. Both scene control
cards compose it (DEBT-01-style component reuse).
"""

import pytest

from app.shared.position_scrubber import PositionScrubber
from tests.control_helpers import record


class TestConstruction:
    def test_initial_state(self, qapp):
        ps = PositionScrubber()
        assert ps.slider.value() == 0
        assert ps.position_label.text() == "0:00"
        assert ps.duration_label.text() == "--:--"


class TestSetProgress:
    def test_moves_slider_proportionally(self, qapp):
        ps = PositionScrubber()
        ps.set_progress(30000, 60000)
        assert ps.slider.value() == 500
        assert ps.position_label.text() == "0:30"

    def test_formats_minutes_and_seconds(self, qapp):
        ps = PositionScrubber()
        ps.set_progress(125000, 600000)
        assert ps.position_label.text() == "2:05"

    def test_zero_duration_leaves_slider_but_updates_label(self, qapp):
        # Before VLC reports a length, duration is 0: don't divide by zero,
        # still advance the time label.
        ps = PositionScrubber()
        ps.set_progress(15000, 0)
        assert ps.slider.value() == 0
        assert ps.position_label.text() == "0:15"

    def test_ignored_while_dragging(self, qapp):
        ps = PositionScrubber()
        ps.slider.sliderPressed.emit()  # user grabs the handle
        ps.slider.setValue(123)

        ps.set_progress(30000, 60000)  # player tick mid-drag

        assert ps.slider.value() == 123  # not overwritten
        assert ps.position_label.text() == "0:00"  # label frozen too


class TestDurationText:
    def test_set_duration_text(self, qapp):
        ps = PositionScrubber()
        ps.set_duration_text("3:07")
        assert ps.duration_label.text() == "3:07"

    def test_set_duration_formats_ms(self, qapp):
        ps = PositionScrubber()
        ps.set_duration(187000)
        assert ps.duration_label.text() == "3:07"

    def test_set_duration_zero_is_placeholder(self, qapp):
        ps = PositionScrubber()
        ps.set_duration_text("3:07")
        ps.set_duration(0)
        assert ps.duration_label.text() == "--:--"


class TestReset:
    def test_reset_zeroes_position(self, qapp):
        ps = PositionScrubber()
        ps.set_progress(30000, 60000)
        ps.reset()
        assert ps.slider.value() == 0
        assert ps.position_label.text() == "0:00"

    def test_reset_clears_dragging(self, qapp):
        # A track change while the user is mid-drag must not leave the scrubber
        # frozen: reset cancels the drag so player ticks drive it again.
        ps = PositionScrubber()
        ps.slider.sliderPressed.emit()  # mid-drag
        ps.reset()

        ps.set_progress(30000, 60000)
        assert ps.slider.value() == 500


class TestSeek:
    def test_release_emits_fraction(self, qapp):
        ps = PositionScrubber()
        rec = record(ps.seek)

        ps.slider.sliderPressed.emit()
        ps.slider.setValue(750)
        assert rec == []  # nothing emitted mid-drag

        ps.slider.sliderReleased.emit()
        assert rec == [pytest.approx((0.75,))]

    def test_release_clears_dragging(self, qapp):
        ps = PositionScrubber()
        ps.slider.sliderPressed.emit()
        ps.slider.sliderReleased.emit()

        # After release, player ticks drive the slider again.
        ps.set_progress(30000, 60000)
        assert ps.slider.value() == 500
