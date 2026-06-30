"""Tests for NoScrollSlider — the value slider that doesn't steal keyboard focus
or mouse-wheel scrolling from its surroundings (volume + position scrubber)."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSlider

from app.shared.no_scroll_slider import NoScrollSlider
from app.shared.position_scrubber import PositionScrubber
from app.shared.volume_slider import VolumeSlider


class _FakeWheel:
    """Minimal stand-in for a QWheelEvent — only ignore()/accept() are used."""

    def __init__(self):
        self.ignored = False

    def ignore(self):
        self.ignored = True

    def accept(self):
        self.ignored = False


def test_is_a_qslider(qapp):
    assert isinstance(NoScrollSlider(), QSlider)


def test_does_not_take_keyboard_focus(qapp):
    # NoFocus -> the playback arrow shortcuts are never redirected into the slider.
    assert NoScrollSlider().focusPolicy() == Qt.FocusPolicy.NoFocus


def test_wheel_is_ignored_and_value_unchanged(qapp):
    # Ignoring the wheel lets it propagate to the parent scroll area (so a long
    # list keeps scrolling) instead of nudging the slider under the cursor.
    slider = NoScrollSlider()
    slider.setRange(0, 100)
    slider.setValue(50)

    event = _FakeWheel()
    slider.wheelEvent(event)

    assert event.ignored is True
    assert slider.value() == 50


def test_volume_slider_uses_no_scroll_slider(qapp):
    assert isinstance(VolumeSlider(0.5).slider, NoScrollSlider)


def test_position_scrubber_uses_no_scroll_slider(qapp):
    assert isinstance(PositionScrubber().slider, NoScrollSlider)
