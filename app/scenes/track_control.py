"""Individual track control widget"""

import os

from PyQt6.QtCore import QByteArray, QMimeData, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from ..audio import TrackPlayer
from ..database import SceneAudioFile
from ..shared.icons import IconLibrary
from ..shared.styles import Styles


class TrackControl(QFrame):
    """Widget for controlling a single track in a scene"""

    volume_changed = pyqtSignal(int, float)  # track_id, volume (0-1) — live, per-tick
    # Fired when the volume settles (slider release, or a discrete keyboard/wheel
    # change), so listeners can persist once instead of on every drag tick.
    volume_committed = pyqtSignal(int, float)  # track_id, volume (0-1)
    repeat_changed = pyqtSignal(int, bool)  # track_id, is_repeat
    remove_requested = pyqtSignal(int)  # track_id
    play_mode_changed = pyqtSignal(int, bool)  # track_id, play_mode

    def __init__(
        self, track: SceneAudioFile, player: TrackPlayer | None = None, parent=None
    ):
        super().__init__(parent)
        self.track = track
        self.player = player
        self._updating_position = False
        self._drag_start_pos = None
        self._icons = IconLibrary()
        self._play_mode = bool(track.play_mode)
        self._repeat_mode = bool(track.is_repeat)

        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self._base_style = Styles.card_frame_style("TrackControl")
        self.setStyleSheet(self._base_style)
        if self.track.audio_file:
            self.setToolTip(self.track.audio_file.file_path)

        self._setup_ui()
        self._connect_player_signals()
        self._update_play_mode_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Top row: title, play, remove
        top_row = QHBoxLayout()

        # Title
        title = (
            self.track.audio_file.display_title if self.track.audio_file else "Unknown"
        )
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(Styles.title_style(size=14))
        self.title_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        top_row.addWidget(self.title_label, 1)

        # File missing indicator
        if self.track.audio_file and not os.path.exists(
            self.track.audio_file.file_path
        ):
            missing_label = QLabel("⚠️ File not found")
            missing_label.setStyleSheet(
                f"color: {Styles.WARNING}; font-size: 11px; font-weight: 700;"
            )
            top_row.addWidget(missing_label)

        # Play/Pause button
        self.play_btn = QPushButton()
        self.play_btn.setFixedSize(28, 28)
        self.play_btn.setIconSize(QSize(12, 12))
        self.play_btn.setStyleSheet(Styles.play_button_style(size=28))
        self.play_btn.clicked.connect(self._toggle_play)
        top_row.addWidget(self.play_btn)

        layout.addLayout(top_row)

        # Middle row: position slider
        position_row = QHBoxLayout()

        self.position_label = QLabel("0:00")
        self.position_label.setFixedWidth(45)
        self.position_label.setStyleSheet(Styles.subtle_text_style(size=11))
        self.position_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        position_row.addWidget(self.position_label)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setMinimum(0)
        self.position_slider.setMaximum(1000)
        self.position_slider.setValue(0)
        self.position_slider.sliderPressed.connect(self._on_position_pressed)
        self.position_slider.sliderReleased.connect(self._on_position_released)
        position_row.addWidget(self.position_slider, 1)

        self.duration_label = QLabel(
            self.track.audio_file.duration_formatted
            if self.track.audio_file
            else "--:--"
        )
        self.duration_label.setFixedWidth(45)
        self.duration_label.setStyleSheet(Styles.subtle_text_style(size=11))
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.duration_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        position_row.addWidget(self.duration_label)

        layout.addLayout(position_row)

        # Bottom row: volume and repeat
        bottom_row = QHBoxLayout()

        # Volume label and slider
        volume_label = QLabel("Vol:")
        volume_label.setStyleSheet(Styles.subtle_text_style(size=12))
        volume_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        bottom_row.addWidget(volume_label)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(int(self.track.volume * 100))
        self.volume_slider.setFixedWidth(120)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.sliderReleased.connect(self._on_volume_released)
        bottom_row.addWidget(self.volume_slider)

        self.volume_value_label = QLabel(f"{int(self.track.volume * 100)}%")
        self.volume_value_label.setFixedWidth(40)
        self.volume_value_label.setStyleSheet(Styles.subtle_text_style(size=12))
        self.volume_value_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        bottom_row.addWidget(self.volume_value_label)

        bottom_row.addStretch()

        # Repeat toggle button
        self.repeat_btn = QPushButton()
        self.repeat_btn.setFixedSize(28, 28)
        self.repeat_btn.setIcon(self._icons.icon("repeat"))
        self.repeat_btn.setIconSize(QSize(14, 14))
        self.repeat_btn.clicked.connect(self._toggle_repeat)
        bottom_row.addWidget(self.repeat_btn)

        layout.addLayout(bottom_row)

    def _connect_player_signals(self):
        """Connect to player signals if available"""
        if self.player:
            self.player.position_changed.connect(self._update_position)
            self.player.end_reached.connect(self._on_end_reached)

    def set_player(self, player: TrackPlayer):
        """Set the track player"""
        self.player = player
        self._connect_player_signals()

        # Apply current settings
        self.player.target_volume = int(self.track.volume * 100)
        self.player.repeat = self.track.is_repeat

    def _toggle_play(self):
        """Toggle play mode"""
        self._play_mode = not self._play_mode
        self.track.play_mode = self._play_mode
        self._update_play_mode_ui()
        self.play_mode_changed.emit(self.track.id, self._play_mode)

    def _on_volume_changed(self, value: int):
        """Handle volume slider change (fires on every tick while dragging)."""
        volume = value / 100.0
        # Keep the in-memory model fresh so later playback setup
        # (_start_scene_playback -> _play_track reads track.volume) uses the
        # current value, not the value the scene was loaded with.
        self.track.volume = volume
        self.volume_value_label.setText(f"{value}%")

        if self.player:
            self.player.target_volume = value

        # Live update every tick so the audio responds immediately.
        self.volume_changed.emit(self.track.id, volume)

        # Persist only for discrete changes (keyboard, wheel, programmatic).
        # While the handle is being dragged, defer persistence to the release
        # (see _on_volume_released) so a drag is one DB write, not dozens.
        if not self.volume_slider.isSliderDown():
            self.volume_committed.emit(self.track.id, volume)

    def _on_volume_released(self):
        """Persist the final volume once a drag finishes."""
        volume = self.volume_slider.value() / 100.0
        self.volume_committed.emit(self.track.id, volume)

    def _update_position(self, position_ms: int):
        """Update position display"""
        if self._updating_position:
            return

        if self.player:
            duration = self.player.get_duration()
            if duration > 0:
                self.position_slider.setValue(int(position_ms * 1000 / duration))

            # Update time label
            seconds = position_ms // 1000
            minutes = seconds // 60
            seconds = seconds % 60
            self.position_label.setText(f"{minutes}:{seconds:02d}")

    def _on_position_pressed(self):
        """Handle position slider press"""
        self._updating_position = True

    def _on_position_released(self):
        """Handle position slider release"""
        if self.player:
            duration = self.player.get_duration()
            if duration > 0:
                position = int(self.position_slider.value() * duration / 1000)
                self.player.set_position(position)

        self._updating_position = False

    def _on_end_reached(self):
        """Handle end of playback"""
        self.position_slider.setValue(0)
        self.position_label.setText("0:00")

    def set_play_mode(self, play_mode: bool):
        """Update the play mode state"""
        self._play_mode = bool(play_mode)
        self.track.play_mode = self._play_mode
        self._update_play_mode_ui()

    def _update_play_mode_ui(self):
        """Update play button based on play mode state"""
        self.play_btn.setIcon(self._icons.icon("play-solid"))
        if self._play_mode:
            self.play_btn.setStyleSheet(Styles.play_button_style(size=28))
            self.setStyleSheet(
                Styles.card_frame_style(
                    "TrackControl",
                    accent_color=Styles.SUCCESS,
                    border_color=Styles.SUCCESS,
                    background_color=Styles.BACKGROUND_LIGHT,
                )
            )
        else:
            self.play_btn.setStyleSheet(Styles.play_button_inactive_style(size=28))
            self.setStyleSheet(self._base_style)

        self._update_repeat_button()

    def _toggle_repeat(self):
        """Toggle repeat mode"""
        self._repeat_mode = not self._repeat_mode
        self.track.is_repeat = self._repeat_mode
        if self.player:
            self.player.repeat = self._repeat_mode
        self._update_repeat_button()
        self.repeat_changed.emit(self.track.id, self._repeat_mode)

    def _update_repeat_button(self):
        """Update repeat button appearance"""
        self.repeat_btn.setStyleSheet(
            Styles.icon_toggle_button_style(self._repeat_mode, size=28)
        )

    def contextMenuEvent(self, event):
        """Show context menu for track actions"""
        menu = QMenu(self)
        remove_action = menu.addAction("Remove from scene")
        remove_action.triggered.connect(
            lambda: self.remove_requested.emit(self.track.id)
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
        mime.setData(
            "application/x-soundmanager-track", QByteArray(str(self.track.id).encode())
        )
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(event.position().toPoint())
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_start_pos = None

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)
