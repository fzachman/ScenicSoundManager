"""Control widget for a playlist entry within a scene"""

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSlider,
    QPushButton, QFrame, QMenu, QApplication
)
from PyQt6.QtCore import pyqtSignal, Qt, QMimeData, QByteArray
from PyQt6.QtGui import QDrag

from ..database import ScenePlaylistEntry
from ..shared.styles import Styles
from ..shared.icons import IconLibrary


class PlaylistEntryControl(QFrame):
    """Widget for controlling a playlist entry in a scene"""

    volume_changed = pyqtSignal(int, float)  # entry_id, volume (0-1)
    shuffle_changed = pyqtSignal(int, bool)  # entry_id, is_shuffle
    repeat_changed = pyqtSignal(int, bool)  # entry_id, is_repeat
    play_mode_changed = pyqtSignal(int, bool)  # entry_id, play_mode
    remove_requested = pyqtSignal(int)  # entry_id

    MIME_TYPE = "application/x-soundmanager-scene-playlist"

    def __init__(self, entry: ScenePlaylistEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self._icons = IconLibrary()
        self._drag_start_pos = None
        self._play_mode = bool(entry.play_mode)
        self._shuffle_mode = bool(entry.is_shuffle)
        self._repeat_mode = bool(entry.is_repeat)

        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self._base_style = f"""
            PlaylistEntryControl {{
                background-color: {Styles.BACKGROUND_LIGHT};
                border: 1px solid {Styles.BORDER};
                border-left: 4px solid {Styles.PRIMARY};
                border-radius: 4px;
                padding: 8px;
                padding-left: 6px;
            }}
        """
        if self.entry.playlist:
            self.setToolTip(f"Playlist: {self.entry.playlist.name}")

        self._setup_ui()
        self._update_play_mode_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Top row: playlist icon + title + remove
        top_row = QHBoxLayout()

        # Playlist type indicator
        type_label = QLabel("PL")
        type_label.setFixedSize(28, 28)
        type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        type_label.setStyleSheet(f"""
            QLabel {{
                background-color: {Styles.PRIMARY};
                color: white;
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        top_row.addWidget(type_label)

        # Title
        name = self.entry.playlist.name if self.entry.playlist else "Unknown Playlist"
        self.title_label = QLabel(name)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        top_row.addWidget(self.title_label, 1)

        # Play/Pause toggle button
        self.play_btn = QPushButton()
        self.play_btn.setFixedSize(36, 36)
        self.play_btn.setIconSize(self.play_btn.size())
        self.play_btn.clicked.connect(self._toggle_play)
        top_row.addWidget(self.play_btn)

        # Remove button
        remove_btn = QPushButton("\u00d7")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setToolTip("Remove from scene")
        remove_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Styles.TEXT_MUTED};
                border: none;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {Styles.DANGER};
            }}
        """)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.entry.id))
        top_row.addWidget(remove_btn)

        layout.addLayout(top_row)

        # Now-playing row: shows currently playing track title
        self.now_playing_label = QLabel("")
        self.now_playing_label.setStyleSheet(f"color: {Styles.SUCCESS}; font-size: 11px; padding-left: 32px;")
        self.now_playing_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.now_playing_label.hide()
        layout.addWidget(self.now_playing_label)

        # Volume row
        volume_row = QHBoxLayout()

        volume_label = QLabel("Vol:")
        volume_label.setStyleSheet(f"color: {Styles.TEXT_MUTED};")
        volume_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        volume_row.addWidget(volume_label)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(int(self.entry.volume * 100))
        self.volume_slider.setFixedWidth(120)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        volume_row.addWidget(self.volume_slider)

        self.volume_value_label = QLabel(f"{int(self.entry.volume * 100)}%")
        self.volume_value_label.setFixedWidth(40)
        self.volume_value_label.setStyleSheet(f"color: {Styles.TEXT_MUTED};")
        self.volume_value_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        volume_row.addWidget(self.volume_value_label)

        volume_row.addStretch()

        layout.addLayout(volume_row)

        # Bottom row: track count info + shuffle + repeat
        bottom_row = QHBoxLayout()

        # Track count from playlist
        if self.entry.playlist:
            track_count = len(self.entry.playlist.tracks) if self.entry.playlist.tracks else 0
            info_text = f"{track_count} track{'s' if track_count != 1 else ''}"
        else:
            info_text = "Unknown"
        self.info_label = QLabel(info_text)
        self.info_label.setStyleSheet(f"color: {Styles.TEXT_MUTED}; font-size: 11px;")
        self.info_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        bottom_row.addWidget(self.info_label)

        bottom_row.addStretch()

        # Shuffle toggle
        self.shuffle_btn = QPushButton("Shuffle")
        self.shuffle_btn.setFixedHeight(24)
        self.shuffle_btn.clicked.connect(self._toggle_shuffle)
        bottom_row.addWidget(self.shuffle_btn)
        self._update_shuffle_button()

        # Repeat toggle
        self.repeat_btn = QPushButton()
        self.repeat_btn.setFixedSize(30, 24)
        self.repeat_btn.setIcon(self._icons.icon("repeat"))
        self.repeat_btn.setIconSize(self.repeat_btn.size())
        self.repeat_btn.clicked.connect(self._toggle_repeat)
        bottom_row.addWidget(self.repeat_btn)
        self._update_repeat_button()

        layout.addLayout(bottom_row)

    def _on_volume_changed(self, value: int):
        """Handle volume slider change"""
        volume = value / 100.0
        self.volume_value_label.setText(f"{value}%")
        self.volume_changed.emit(self.entry.id, volume)

    def set_current_track(self, title: str):
        """Update the now-playing display with the current track title"""
        if title:
            self.now_playing_label.setText(f"Now playing: {title}")
            self.now_playing_label.show()
        else:
            self.now_playing_label.hide()

    def _toggle_play(self):
        """Toggle play mode"""
        self._play_mode = not self._play_mode
        self.entry.play_mode = self._play_mode
        self._update_play_mode_ui()
        self.play_mode_changed.emit(self.entry.id, self._play_mode)

    def set_play_mode(self, play_mode: bool):
        """Update the play mode state"""
        self._play_mode = bool(play_mode)
        self.entry.play_mode = self._play_mode
        self._update_play_mode_ui()

    def _update_play_mode_ui(self):
        """Update play button and border based on play mode state"""
        self.play_btn.setIcon(self._icons.icon("play"))
        if self._play_mode:
            self.play_btn.setStyleSheet(Styles.play_button_style())
            self.setStyleSheet(self._base_style)
        else:
            self.play_btn.setStyleSheet(Styles.play_button_inactive_style())
            self.setStyleSheet(self._base_style + f"""
                PlaylistEntryControl {{
                    border-left: 4px solid {Styles.BORDER};
                    padding-left: 6px;
                }}
            """)

    def _toggle_shuffle(self):
        """Toggle shuffle mode"""
        self._shuffle_mode = not self._shuffle_mode
        self.entry.is_shuffle = self._shuffle_mode
        self._update_shuffle_button()
        self.shuffle_changed.emit(self.entry.id, self._shuffle_mode)

    def _toggle_repeat(self):
        """Toggle repeat mode"""
        self._repeat_mode = not self._repeat_mode
        self.entry.is_repeat = self._repeat_mode
        self._update_repeat_button()
        self.repeat_changed.emit(self.entry.id, self._repeat_mode)

    def _update_shuffle_button(self):
        """Update shuffle button appearance"""
        extra = "padding: 2px 8px; font-size: 11px;"
        if self._shuffle_mode:
            self.shuffle_btn.setStyleSheet(Styles.toggle_on_style(radius=4, extra=extra))
        else:
            self.shuffle_btn.setStyleSheet(Styles.toggle_off_style(radius=4, extra=extra))

    def _update_repeat_button(self):
        """Update repeat button appearance"""
        if self._repeat_mode:
            self.repeat_btn.setStyleSheet(Styles.toggle_on_style())
        else:
            self.repeat_btn.setStyleSheet(Styles.toggle_off_style())

    def contextMenuEvent(self, event):
        """Show context menu"""
        menu = QMenu(self)
        remove_action = menu.addAction("Remove from scene")
        remove_action.triggered.connect(lambda: self.remove_requested.emit(self.entry.id))
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
        if (event.position().toPoint() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(self.MIME_TYPE, QByteArray(str(self.entry.id).encode()))
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(event.position().toPoint())
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_start_pos = None

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)
