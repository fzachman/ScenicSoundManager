"""Main playlists view widget"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QSplitter, QWidget

from ..audio import AudioEngine
from ..database import DatabaseConnection, Playlist
from .playlist_editor import PlaylistEditor
from .playlist_list import PlaylistListWidget


class PlaylistsWidget(QWidget):
    """Main playlists view with list and editor"""

    playlist_selection_changed = pyqtSignal(int)  # playlist_id
    playback_state_changed = pyqtSignal(
        object, object, bool
    )  # playlist_id, playlist_name, is_playing
    playlist_modified = pyqtSignal()  # a playlist's tracks changed

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
        self.playlist_editor.playback_state_changed.connect(
            self.playback_state_changed.emit
        )
        # Track adds/removes change the sidebar counts.
        self.playlist_editor.playlist_modified.connect(self.refresh_track_counts)
        self.playlist_editor.playlist_modified.connect(self.playlist_modified.emit)

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

    def stop_all_playback(self, fade_ms: int = 0):
        """Stop all playlist playback (immediately, or fading over ``fade_ms``)"""
        self.playlist_editor.stop_all(fade_ms)

    def active_playback(self) -> tuple[int, bool] | None:
        """(playlist_id, is_playing) of the playlist owning playback, or None."""
        return self.playlist_editor.active_playback()

    def select_playlist(self, playlist_id: int):
        """Select and load a playlist by ID"""
        self.playlist_list.select_playlist(playlist_id)

    def add_audio_files(self, playlist_id: int, audio_file_ids: list[int]) -> int:
        """Append library files to a playlist, skipping ones it already holds."""
        return self.playlist_editor.add_audio_files(playlist_id, audio_file_ids)

    def create_playlist(self, name: str, audio_file_ids: list[int]) -> int:
        """Create a playlist holding the given files; return its id.

        The sidebar gains the new playlist, but the open one stays open.
        """
        playlist_id = self.db.add_playlist(Playlist(name=name))
        self.playlist_editor.add_audio_files(playlist_id, audio_file_ids)
        self.playlist_list.refresh_playlists()
        return playlist_id

    def refresh_track_counts(self):
        """Re-read the sidebar's per-playlist track counts."""
        self.playlist_list.refresh_playlists()

    # --- Keyboard-shortcut entry points (delegated to editor / list) ---

    def toggle_playback(self):
        """Play/pause the open playlist."""
        self.playlist_editor.toggle_playback()

    def pause_active(self):
        """Pause the playing playlist."""
        self.playlist_editor.pause_active()

    def next_track(self):
        """Advance the playing playlist to its next track."""
        self.playlist_editor.next_track()

    def play_current(self):
        """Start the open playlist unless it is already playing."""
        self.playlist_editor.play_current()

    def select_relative(self, delta: int) -> int | None:
        """Step the playlist-list selection by ``delta`` (next/prev)."""
        return self.playlist_list.select_relative(delta)

    def focus_list(self):
        """Focus the playlist list (so transport shortcuts work when the tab opens)."""
        self.playlist_list.focus_list()
