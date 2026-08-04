"""Reusable volume slider with commit-on-release semantics."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .no_scroll_slider import NoScrollSlider
from .styles import Styles
from .theme import theme_manager


class VolumeSlider(QWidget):
    """A 'Vol:' label + 0-100 slider + percent label.

    Emits ``changed`` every tick (live) and ``committed`` only when the value
    settles — on slider release, or immediately for a discrete keyboard/wheel/
    programmatic change (when the handle is not held down). This is the
    commit-on-release contract PERF-02 introduced: persisting listeners connect
    to ``committed`` (one write per gesture), live listeners (audio) connect to
    ``changed``.

    Both signals carry the volume as a 0-1 float. The owning control re-emits
    its own id-bearing signal, so the entity id is intentionally not part of
    this widget's API.
    """

    changed = pyqtSignal(float)  # 0-1, every tick
    committed = pyqtSignal(float)  # 0-1, on settle

    def __init__(self, initial_volume: float, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("Vol:")
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._label)

        self.slider = NoScrollSlider()
        self.slider.setMinimum(0)
        self.slider.setMaximum(100)
        self.slider.setValue(round(initial_volume * 100))
        self.slider.setFixedWidth(120)
        self.slider.valueChanged.connect(self._on_changed)
        self.slider.sliderReleased.connect(self._on_released)
        layout.addWidget(self.slider)

        self.value_label = QLabel(f"{round(initial_volume * 100)}%")
        self.value_label.setFixedWidth(40)
        self.value_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        layout.addWidget(self.value_label)

        self._apply_theme_styles()
        theme_manager.theme_changed.connect(self._apply_theme_styles)

    def _apply_theme_styles(self) -> None:
        """Re-apply palette-dependent styles; re-run on theme change."""
        self._label.setStyleSheet(Styles.subtle_text_style(size=12))
        self.value_label.setStyleSheet(Styles.subtle_text_style(size=12))

    def set_volume_silently(self, volume: float) -> None:
        """Set the slider without emitting changed/committed.

        For programmatic state swaps (preset apply): a plain setValue would
        emit both signals (the handle isn't down) and write the value back
        to persistence. blockSignals also suppresses the label update, so
        the label is set manually.
        """
        value = round(volume * 100)
        self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(False)
        self.value_label.setText(f"{value}%")

    def _on_changed(self, value: int) -> None:
        self.value_label.setText(f"{value}%")
        volume = value / 100.0
        self.changed.emit(volume)
        # Defer the commit while the handle is held; the drag persists on
        # release (see _on_released). Discrete changes commit immediately.
        if not self.slider.isSliderDown():
            self.committed.emit(volume)

    def _on_released(self) -> None:
        self.committed.emit(self.slider.value() / 100.0)
