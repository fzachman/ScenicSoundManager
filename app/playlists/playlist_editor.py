"""Playlist editor for managing tracks in a playlist"""

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame
)
from PyQt6.QtCore import pyqtSignal, Qt, QByteArray
from PyQt6.QtGui import QDrag

from ..database import DatabaseConnection, Playlist, PlaylistTrack
from ..shared.styles import Styles
from ..shared.icons import IconLibrary


class PlaylistTrackItem(QFrame):
    """Display widget for a single track in a playlist"""

    remove_requested = pyqtSignal(int)  # track_id

    def __init__(self, track: PlaylistTrack, parent=None):
        super().__init__(parent)
        self.track = track
        self._icons = IconLibrary()
        self._drag_start_pos = None

        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            PlaylistTrackItem {{
                background-color: {Styles.BACKGROUND_LIGHT};
                border: 1px solid {Styles.BORDER};
                border-radius: 4px;
                padding: 8px;
            }}
        """)

        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Track info
        info_layout = QVBoxLayout()
        if self.track.audio_file:
            title_label = QLabel(self.track.audio_file.display_title)
            title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
            info_layout.addWidget(title_label)

            if self.track.audio_file.artist:
                artist_label = QLabel(self.track.audio_file.artist)
                artist_label.setStyleSheet(f"color: {Styles.TEXT_MUTED}; font-size: 11px;")
                info_layout.addWidget(artist_label)
        else:
            title_label = QLabel("Unknown Track")
            title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
            info_layout.addWidget(title_label)

        layout.addLayout(info_layout, 1)

        # Duration
        if self.track.audio_file:
            duration_label = QLabel(self.track.audio_file.duration_formatted)
            duration_label.setStyleSheet(f"color: {Styles.TEXT_MUTED};")
            layout.addWidget(duration_label)

        # Remove button
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setToolTip("Remove from playlist")
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
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.track.id))
        layout.addWidget(remove_btn)

    def mousePressEvent(self, event):
        from PyQt6.QtWidgets import QApplication
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QMimeData
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._drag_start_pos is None:
            return
        if (event.position().toPoint() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-soundmanager-playlist-track", QByteArray(str(self.track.id).encode()))
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(event.position().toPoint())
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_start_pos = None

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)


class PlaylistTrackListContainer(QWidget):
    """Container for draggable playlist track items"""

    order_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._track_widgets: dict[int, PlaylistTrackItem] = {}

    def register_track(self, track_id: int, widget: PlaylistTrackItem):
        self._track_widgets[track_id] = widget

    def clear_registry(self):
        self._track_widgets.clear()

    def track_ids_in_order(self) -> list[int]:
        layout = self.layout()
        if not layout:
            return []
        track_ids: list[int] = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget()
            if isinstance(widget, PlaylistTrackItem):
                track_ids.append(widget.track.id)
        return track_ids

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-soundmanager-playlist-track"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-soundmanager-playlist-track"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat("application/x-soundmanager-playlist-track"):
            return

        data = bytes(event.mimeData().data("application/x-soundmanager-playlist-track"))
        try:
            track_id = int(data.decode())
        except ValueError:
            return

        widget = self._track_widgets.get(track_id)
        if not widget:
            return

        layout = self.layout()
        if not layout:
            return

        insert_index = self._index_for_y(event.position().y())
        current_index = layout.indexOf(widget)
        if current_index == -1:
            return
        if insert_index > current_index:
            insert_index -= 1
        layout.removeWidget(widget)
        layout.insertWidget(insert_index, widget)
        event.acceptProposedAction()
        self.order_changed.emit(self.track_ids_in_order())

    def _index_for_y(self, y: float) -> int:
        layout = self.layout()
        if not layout:
            return 0
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget()
            if not isinstance(widget, PlaylistTrackItem):
                continue
            midpoint = widget.y() + (widget.height() / 2)
            if y < midpoint:
                return i
        return layout.count()


class PlaylistEditor(QWidget):
    """Editor for a single playlist's tracks"""

    playlist_modified = pyqtSignal()

    def __init__(self, db: DatabaseConnection, parent=None):
        super().__init__(parent)
        self.db = db
        self._current_playlist: Optional[Playlist] = None
        self._track_items: dict[int, PlaylistTrackItem] = {}
        self._icons = IconLibrary()

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header with playlist title
        header = QHBoxLayout()

        self.title_label = QLabel("Select a playlist")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 18px;")
        header.addWidget(self.title_label)

        header.addStretch()
        layout.addLayout(header)

        # Add tracks button
        add_layout = QHBoxLayout()
        self.add_tracks_btn = QPushButton("+ Add Tracks")
        self.add_tracks_btn.clicked.connect(self._add_tracks)
        self.add_tracks_btn.setEnabled(False)
        add_layout.addWidget(self.add_tracks_btn)
        add_layout.addStretch()
        layout.addLayout(add_layout)

        # Tracks scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.tracks_container = PlaylistTrackListContainer()
        self.tracks_container.order_changed.connect(self._on_tracks_reordered)
        self.tracks_layout = QVBoxLayout(self.tracks_container)
        self.tracks_layout.setContentsMargins(0, 8, 0, 0)
        self.tracks_layout.setSpacing(8)

        scroll.setWidget(self.tracks_container)
        layout.addWidget(scroll)

        # Empty state
        self.empty_label = QLabel("No tracks in this playlist.\nClick '+ Add Tracks' to add audio files.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {Styles.TEXT_MUTED}; padding: 40px;")
        self.empty_label.hide()
        layout.addWidget(self.empty_label)

    def load_playlist(self, playlist: Playlist):
        """Load a playlist for editing"""
        self._current_playlist = playlist
        self.title_label.setText(playlist.name)

        # Enable controls
        self.add_tracks_btn.setEnabled(True)

        # Load tracks
        self._refresh_tracks()

    def _refresh_tracks(self):
        """Refresh track display"""
        if not self._current_playlist:
            return

        # Clear existing track items
        while self.tracks_layout.count() > 0:
            item = self.tracks_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.tracks_container.clear_registry()
        self._track_items.clear()

        # Load tracks from playlist
        playlist = self.db.get_playlist(self._current_playlist.id)
        if not playlist:
            return

        self._current_playlist = playlist

        if not playlist.tracks:
            self.empty_label.show()
        else:
            self.empty_label.hide()

            for track in playlist.tracks:
                self._add_track_item(track)

    def _add_track_item(self, track: PlaylistTrack):
        """Add a track item widget"""
        item = PlaylistTrackItem(track)
        item.remove_requested.connect(self._remove_track)

        self._track_items[track.id] = item
        self.tracks_container.register_track(track.id, item)
        self.tracks_layout.addWidget(item)

    def _add_tracks(self):
        """Show dialog to add tracks"""
        if not self._current_playlist:
            return

        from ..scenes.scene_editor import AudioFileSearchDialog
        from ..audio import AudioEngine

        existing_ids = {t.audio_file_id for t in self._current_playlist.tracks}
        audio_engine = AudioEngine.get_instance()
        dialog = AudioFileSearchDialog(
            self.db, audio_engine,
            disabled_track_ids=existing_ids, parent=self,
        )
        if dialog.exec():
            files = dialog.get_selected_files()
            for file in files:
                position = len(self._current_playlist.tracks)
                self.db.add_track_to_playlist(self._current_playlist.id, file.id, position)

            self._refresh_tracks()
            self.playlist_modified.emit()

    def _remove_track(self, track_id: int):
        """Remove a track from the playlist"""
        self.db.remove_track_from_playlist(track_id)
        self._refresh_tracks()
        self._persist_track_order()
        self.playlist_modified.emit()

    def _on_tracks_reordered(self, track_ids: list[int]):
        if not self._current_playlist or not track_ids:
            return
        self._persist_track_order(track_ids)
        self.playlist_modified.emit()

    def _persist_track_order(self, track_ids: Optional[list[int]] = None):
        if not self._current_playlist:
            return
        if track_ids is None:
            track_ids = self.tracks_container.track_ids_in_order()
        if not track_ids:
            return
        self.db.reorder_playlist_tracks(self._current_playlist.id, track_ids)

    def clear(self):
        """Clear the editor"""
        self._track_items.clear()
        self._current_playlist = None
        self.title_label.setText("Select a playlist")
        self.add_tracks_btn.setEnabled(False)

        # Clear track items
        while self.tracks_layout.count() > 0:
            item = self.tracks_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.tracks_container.clear_registry()

    def refresh(self):
        """Refresh the current playlist"""
        if self._current_playlist:
            playlist = self.db.get_playlist(self._current_playlist.id)
            if playlist:
                self.load_playlist(playlist)
