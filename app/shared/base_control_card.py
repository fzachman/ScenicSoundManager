"""Shared base class for the scene control cards.

``TrackControl`` and ``PlaylistEntryControl`` are two ``QFrame`` cards that share
a large common surface: the volume row (commit-on-release), the repeat/play
toggles, the drag-drop / context-menu plumbing, and a set of signals. This base
hoists that surface; subclasses supply a model object and per-card styling via
the hooks below, and assemble their own ``_setup_ui`` (row composition genuinely
differs — a position slider for tracks vs. shuffle / now-playing / track-count
for playlist entries).

This is intentionally a *partial* template (mirroring
``app/shared/base_list_widget.py``): ``_setup_ui`` and the card-style hooks stay
per-subclass because their layouts and accent colors differ. Everything that is
identical or differs only by a model attribute / MIME type / id lives here.
"""

from PyQt6.QtCore import QByteArray, QMimeData, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QMenu,
    QPushButton,
    QSlider,
)

from .icons import IconLibrary
from .styles import Styles
from .volume_slider import VolumeSlider


class SceneControlCard(QFrame):
    """Base class for ``TrackControl`` and ``PlaylistEntryControl``."""

    # Signals common to both controls. The leading int is the entity id
    # (track id / entry id); volume is a 0-1 float.
    volume_changed = pyqtSignal(int, float)  # live, per-tick
    volume_committed = pyqtSignal(int, float)  # on settle (persist once)
    repeat_changed = pyqtSignal(int, bool)
    play_mode_changed = pyqtSignal(int, bool)
    remove_requested = pyqtSignal(int)

    # Overridden by subclasses with a draggable payload.
    MIME_TYPE: str = ""

    # Attributes the base references but the subclass populates (in
    # _init_card_state or _setup_ui). Declared here for clarity / type-checking.
    _icons: IconLibrary
    _drag_start_pos: object
    _play_mode: bool
    _repeat_mode: bool
    play_btn: QPushButton
    repeat_btn: QPushButton
    volume: VolumeSlider
    volume_slider: QSlider

    # --- Card state scaffolding ---

    def _init_card_state(self) -> None:
        """Initialize the state both controls set identically.

        Call this AFTER the subclass has stored its model — it reads ``_model``
        for the initial play/repeat state.
        """
        self._icons = IconLibrary()
        self._drag_start_pos = None
        self._play_mode = bool(self._model.play_mode)
        self._repeat_mode = bool(self._model.is_repeat)
        self.setFrameStyle(QFrame.Shape.StyledPanel)

    # --- Shared builders (the subclass _setup_ui places the returned widgets) ---

    def _build_volume_row(self) -> VolumeSlider:
        """Create the volume slider and wire commit-on-release; return it."""
        self.volume = VolumeSlider(self._model.volume)
        # Stable public handle to the inner slider (callers/tests poke this).
        self.volume_slider = self.volume.slider
        self.volume.changed.connect(self._on_volume_changed)
        self.volume.committed.connect(self._on_volume_committed)
        return self.volume

    def _build_repeat_button(self) -> QPushButton:
        """Create the repeat toggle button (already styled) and return it."""
        self.repeat_btn = QPushButton()
        self.repeat_btn.setFixedSize(28, 28)
        self.repeat_btn.setIcon(self._icons.icon("repeat"))
        self.repeat_btn.setIconSize(QSize(14, 14))
        self.repeat_btn.clicked.connect(self._toggle_repeat)
        self._update_repeat_button()
        return self.repeat_btn

    # --- Volume handlers (commit-on-release split preserved) ---

    def _on_volume_changed(self, volume: float) -> None:
        """Live update on every slider tick."""
        # Keep the in-memory model fresh so later playback setup reads the
        # current volume, not the value the scene was loaded with.
        self._model.volume = volume
        # round() (not int()) so e.g. 0.29 -> 29, not 28 (float truncation).
        self._on_volume_applied(round(volume * 100))
        self.volume_changed.emit(self._entity_id, volume)

    def _on_volume_committed(self, volume: float) -> None:
        """Persist once the value settles (release / discrete change)."""
        self._model.volume = volume
        self.volume_committed.emit(self._entity_id, volume)

    # --- Repeat toggle ---

    def _toggle_repeat(self) -> None:
        self._repeat_mode = not self._repeat_mode
        self._model.is_repeat = self._repeat_mode
        self._on_repeat_applied()
        self._update_repeat_button()
        self.repeat_changed.emit(self._entity_id, self._repeat_mode)

    def _update_repeat_button(self) -> None:
        self.repeat_btn.setStyleSheet(
            Styles.icon_toggle_button_style(self._repeat_mode, size=28)
        )

    # --- Play toggle / play-mode styling ---

    def _toggle_play(self) -> None:
        self._play_mode = not self._play_mode
        self._model.play_mode = self._play_mode
        self._update_play_mode_ui()
        self.play_mode_changed.emit(self._entity_id, self._play_mode)

    def set_play_mode(self, play_mode: bool) -> None:
        """Update play-mode state WITHOUT emitting (unlike ``_toggle_play``)."""
        self._play_mode = bool(play_mode)
        self._model.play_mode = self._play_mode
        self._update_play_mode_ui()

    def _update_play_mode_ui(self) -> None:
        self.play_btn.setIcon(self._icons.icon("play-solid"))
        if self._play_mode:
            self.play_btn.setStyleSheet(Styles.play_button_style(size=28))
            self.setStyleSheet(self._active_card_style())
        else:
            self.play_btn.setStyleSheet(Styles.play_button_inactive_style(size=28))
            self.setStyleSheet(self._inactive_card_style())
        self._after_play_mode_update()

    # --- Drag-drop / context menu ---

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        remove_action = menu.addAction("Remove from scene")
        remove_action.triggered.connect(
            lambda: self.remove_requested.emit(self._entity_id)
        )
        menu.exec(event.globalPos())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._drag_start_pos is None:
            return
        if (
            event.position().toPoint() - self._drag_start_pos
        ).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(self.MIME_TYPE, QByteArray(str(self._entity_id).encode()))
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(event.position().toPoint())
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_start_pos = None

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    # --- Overridable hooks (default no-op) ---

    def _on_volume_applied(self, value: int) -> None:
        """Hook: a subclass with a player pushes the 0-100 int volume to it."""

    def _on_repeat_applied(self) -> None:
        """Hook: a subclass with a player pushes repeat state to it."""

    def _after_play_mode_update(self) -> None:
        """Hook: extra work after the play-mode restyle (e.g. repeat refresh)."""

    # --- Abstract methods (subclasses MUST override) ---

    @property
    def _model(self):
        """The bound dataclass (e.g. ``SceneAudioFile`` / ``ScenePlaylistEntry``)."""
        raise NotImplementedError

    @property
    def _entity_id(self) -> int:
        """The id emitted in this control's signals (``track.id`` / ``entry.id``)."""
        raise NotImplementedError

    def _active_card_style(self) -> str:
        """The frame stylesheet to apply when play mode is on."""
        raise NotImplementedError

    def _inactive_card_style(self) -> str:
        """The frame stylesheet to apply when play mode is off."""
        raise NotImplementedError
