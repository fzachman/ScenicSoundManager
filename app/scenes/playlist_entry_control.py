"""Control widget for a playlist entry within a scene"""

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QFrame, QMenu, QApplication
)
from PyQt6.QtCore import pyqtSignal, Qt, QMimeData, QByteArray
from PyQt6.QtGui import QDrag

from ..database import ScenePlaylistEntry
from ..shared.styles import Styles
from ..shared.icons import IconLibrary


class PlaylistEntryControl(QFrame):
    """Widget for controlling a playlist entry in a scene"""

    shuffle_changed = pyqtSignal(int, bool)  # entry_id, is_shuffle
    repeat_changed = pyqtSignal(int, bool)  # entry_id, is_repeat
    remove_requested = pyqtSignal(int)  # entry_id

    MIME_TYPE = "application/x-soundmanager-scene-playlist"

    def __init__(self, entry: ScenePlaylistEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self._icons = IconLibrary()
        self._drag_start_pos = None
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
        self.setStyleSheet(self._base_style)
        if self.entry.playlist:
            self.setToolTip(f"Playlist: {self.entry.playlist.name}")

        self._setup_ui()

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
        if self._shuffle_mode:
            self.shuffle_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Styles.PRIMARY};
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background-color: {Styles.PRIMARY_DARK};
                }}
            """)
        else:
            self.shuffle_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Styles.BACKGROUND_LIGHTER};
                    color: {Styles.TEXT_MUTED};
                    border: 1px solid {Styles.BORDER};
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background-color: {Styles.BACKGROUND_LIGHT};
                }}
            """)

    def _update_repeat_button(self):
        """Update repeat button appearance"""
        if self._repeat_mode:
            self.repeat_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Styles.PRIMARY};
                    color: white;
                    border: none;
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background-color: {Styles.PRIMARY_DARK};
                }}
            """)
        else:
            self.repeat_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Styles.BACKGROUND_LIGHTER};
                    color: {Styles.TEXT_MUTED};
                    border: 1px solid {Styles.BORDER};
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background-color: {Styles.BACKGROUND_LIGHT};
                }}
            """)

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
