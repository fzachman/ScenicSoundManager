"""Playlist list sidebar widget"""

from PyQt6.QtCore import pyqtSignal

from ..database import DatabaseConnection, Playlist
from ..shared.base_list_widget import BaseListWidget


class PlaylistListWidget(BaseListWidget):
    """Sidebar list of playlists"""

    _entity_name = "Playlist"
    _display_attr = "name"

    playlist_selected = pyqtSignal(object)
    playlist_created = pyqtSignal(object)
    playlist_deleted = pyqtSignal(int)

    def __init__(self, db: DatabaseConnection, parent=None):
        super().__init__(db, parent)

    # --- Backward-compatible public API ---

    def refresh_playlists(self):
        self.refresh()

    def get_selected_playlist_id(self):
        return self.get_selected_id()

    def select_playlist(self, playlist_id: int):
        self.select_by_id(playlist_id)

    # --- DB operations ---

    def _get_all_items(self):
        return self.db.get_all_playlists()

    def _search_items(self, query):
        return self.db.search_playlists(query)

    def _get_item_by_id(self, item_id):
        return self.db.get_playlist(item_id)

    def _create_new_item(self, name):
        playlist = Playlist(name=name)
        playlist.id = self.db.add_playlist(playlist)
        return playlist

    def _update_item(self, item):
        self.db.update_playlist(item)

    def _delete_item_by_id(self, item_id):
        self.db.delete_playlist(item_id)

    def _duplicate_item(self, playlist):
        new_playlist = Playlist(name=f"{playlist.name} (copy)")
        new_playlist.id = self.db.add_playlist(new_playlist)

        tracks = self.db.get_playlist_tracks(playlist.id)
        for track in tracks:
            self.db.add_track_to_playlist(
                new_playlist.id, track.audio_file_id, track.position
            )

        return new_playlist

    def _reorder_items(self, ids):
        self.db.reorder_playlists(ids)

    # --- Signal emitters ---

    def _emit_selected(self, item):
        self.playlist_selected.emit(item)

    def _emit_created(self, item):
        self.playlist_created.emit(item)

    def _emit_deleted(self, item_id):
        self.playlist_deleted.emit(item_id)
