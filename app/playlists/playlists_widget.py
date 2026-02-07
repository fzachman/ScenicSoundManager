"""Main playlists view widget"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QSplitter
from PyQt6.QtCore import Qt, pyqtSignal

from ..database import DatabaseConnection, Playlist
from ..audio import AudioEngine
from .playlist_list import PlaylistListWidget
from .playlist_editor import PlaylistEditor


class PlaylistsWidget(QWidget):
    """Main playlists view with list and editor"""

    playlist_selection_changed = pyqtSignal(int)  # playlist_id
    playback_state_changed = pyqtSignal(object, object, bool)  # playlist_id, playlist_name, is_playing

    def __init__(self, db: DatabaseConnection, audio_engine: AudioEngine, parent=None):
        super().__init__(parent)
        self.db = db
        self.audio_engine = audio_engine

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Playlist list (left sidebar)
        self.playlist_list = PlaylistListWidget(self.db)
        splitter.addWidget(self.playlist_list)

        # Playlist editor (right panel)
        self.playlist_editor = PlaylistEditor(self.db, self.audio_engine)
        splitter.addWidget(self.playlist_editor)

        # Set initial sizes (1:3 ratio)
        splitter.setSizes([250, 750])

        layout.addWidget(splitter)

    def _connect_signals(self):
        """Connect signals between components"""
        self.playlist_list.playlist_selected.connect(self._on_playlist_selected)
        self.playlist_list.playlist_created.connect(self._on_playlist_created)
        self.playlist_list.playlist_deleted.connect(self._on_playlist_deleted)
        self.playlist_editor.playlist_renamed.connect(self._on_playlist_renamed)
        self.playlist_editor.playback_state_changed.connect(self.playback_state_changed.emit)

    def _on_playlist_selected(self, playlist: Playlist):
        """Handle playlist selection"""
        self.playlist_editor.load_playlist(playlist)
        if playlist.id is not None:
            self.playlist_selection_changed.emit(playlist.id)

    def _on_playlist_created(self, playlist: Playlist):
        """Handle new playlist creation"""
        self.playlist_editor.load_playlist(playlist)
        if playlist.id is not None:
            self.playlist_selection_changed.emit(playlist.id)

    def _on_playlist_deleted(self, playlist_id: int):
        """Handle playlist deletion"""
        self.playlist_editor.clear()

    def _on_playlist_renamed(self, playlist_id: int, new_name: str):
        """Handle playlist rename from editor"""
        self.playlist_list.refresh_playlists()

    def stop_all_playback(self):
        """Stop all playlist playback"""
        self.playlist_editor.stop_all()

    def select_playlist(self, playlist_id: int):
        """Select and load a playlist by ID"""
        self.playlist_list.select_playlist(playlist_id)
