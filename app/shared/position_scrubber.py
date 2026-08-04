"""Reusable playback position scrubber.

A small, player-agnostic widget: ``position_label | slider | duration_label``.
The slider tracks playback position (0-1000 of the track) and, after the user
drags or clicks it, emits ``seek`` with a 0..1 fraction. The owning control maps
that fraction to milliseconds against the player's duration and seeks.

This mirrors the ``VolumeSlider`` component pattern (DEBT-01): the cohesive,
drag-aware scrubber logic lives here so both ``TrackControl`` and
``PlaylistEntryControl`` compose it instead of each carrying a copy.

Drag handling: while the handle is held down (``sliderPressed`` until
``sliderReleased``), incoming ``set_progress`` calls are ignored so the player's
position updates don't fight the user's drag. The seek is emitted once on
release.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .no_scroll_slider import NoScrollSlider
from .styles import Styles
from .theme import theme_manager


def _format_ms(position_ms: int) -> str:
    """Format a millisecond position as ``m:ss``."""
    seconds = max(0, position_ms) // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"


class PositionScrubber(QWidget):
    """Position label + seek slider + duration label.

    Signals:
        seek(float): emitted on slider release with a 0..1 fraction of the
            track. The owner maps it to ms (``int(fraction * duration_ms)``).
    """

    SLIDER_MAX = 1000

    seek = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._dragging = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.position_label = QLabel("0:00")
        self.position_label.setFixedWidth(45)
        self.position_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        layout.addWidget(self.position_label)

        self.slider = NoScrollSlider()
        self.slider.setMinimum(0)
        self.slider.setMaximum(self.SLIDER_MAX)
        self.slider.setValue(0)
        self.slider.sliderPressed.connect(self._on_pressed)
        self.slider.sliderReleased.connect(self._on_released)
        layout.addWidget(self.slider, 1)

        self.duration_label = QLabel("--:--")
        self.duration_label.setFixedWidth(45)
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.duration_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        layout.addWidget(self.duration_label)

        self._apply_theme_styles()
        theme_manager.theme_changed.connect(self._apply_theme_styles)

    def _apply_theme_styles(self) -> None:
        """Re-apply palette-dependent styles; re-run on theme change."""
        self.position_label.setStyleSheet(Styles.subtle_text_style(size=11))
        self.duration_label.setStyleSheet(Styles.subtle_text_style(size=11))

    # --- Drive from the player ---

    def set_progress(self, position_ms: int, duration_ms: int) -> None:
        """Update the slider + position label from the current playback time.

        Ignored while the user is dragging the handle, so a seek-in-progress is
        not overwritten by the player's position ticks.
        """
        if self._dragging:
            return
        if duration_ms > 0:
            self.slider.setValue(int(position_ms * self.SLIDER_MAX / duration_ms))
        self.position_label.setText(_format_ms(position_ms))

    def set_duration_text(self, text: str) -> None:
        """Set the right-hand duration label (e.g. ``"2:00"`` or ``"--:--"``)."""
        self.duration_label.setText(text)

    def set_duration(self, duration_ms: int) -> None:
        """Set the duration label from a ms value (``"--:--"`` when unknown/0)."""
        self.set_duration_text(_format_ms(duration_ms) if duration_ms > 0 else "--:--")

    def reset(self) -> None:
        """Return to the start (slider 0, position ``0:00``).

        Also clears any in-progress drag: a reset means whatever the user was
        scrubbing is gone (track changed / playback stopped), so the drag is
        stale. Clearing it lets the next track's position ticks drive the slider
        again instead of staying frozen behind a drag that never "released".
        """
        self._dragging = False
        self.slider.setValue(0)
        self.position_label.setText("0:00")

    # --- Drag handling ---

    def _on_pressed(self) -> None:
        self._dragging = True

    def _on_released(self) -> None:
        self._dragging = False
        self.seek.emit(self.slider.value() / self.SLIDER_MAX)
