"""Playlist list sidebar widget"""

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QMenu, QAbstractItemView
)
from PyQt6.QtCore import pyqtSignal, Qt

from ..database import DatabaseConnection, Playlist
from ..library.search_bar import SearchBar
from ..shared.icons import IconLibrary
from ..shared.dialogs import TextInputDialog


class PlaylistListWidget(QWidget):
    """Sidebar list of playlists"""

    playlist_selected = pyqtSignal(object)  # Playlist
    playlist_created = pyqtSignal(object)  # Playlist
    playlist_deleted = pyqtSignal(int)  # playlist_id

    def __init__(self, db: DatabaseConnection, parent=None):
        super().__init__(parent)
        self.db = db
        self._playlists: list[Playlist] = []
        self._icons = IconLibrary()

        self.setMinimumWidth(200)
        self.setMaximumWidth(300)

        self._setup_ui()
        self.refresh_playlists()
        self._update_order_button_state()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("Playlists")
        header_label.setStyleSheet("font-weight: bold; font-size: 16px; padding: 8px;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        self.order_btn = QPushButton()
        self.order_btn.setCheckable(True)
        self.order_btn.setFixedSize(28, 28)
        self.order_btn.setIcon(self._icons.icon("list"))
        self.order_btn.setIconSize(self.order_btn.size())
        self.order_btn.setToolTip("Unlock Playlist Order")
        self.order_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                color: white;
                margin-right: 6px;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.05);
                border-color: rgba(0, 0, 0, 0.12);
            }
            QPushButton:checked {
                background-color: rgba(74, 144, 217, 0.2);
                border-color: #4A90D9;
            }
        """)
        self.order_btn.toggled.connect(self._set_ordering_enabled)
        header_layout.addWidget(self.order_btn)
        layout.addLayout(header_layout)

        # Search bar
        self.search_bar = SearchBar(placeholder="Search playlists...")
        self.search_bar.search_changed.connect(self._on_search)
        layout.addWidget(self.search_bar)

        # Playlist list
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.list_widget.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self.list_widget)

        # New playlist button
        new_btn = QPushButton("+ New Playlist")
        new_btn.clicked.connect(self._create_playlist)
        layout.addWidget(new_btn)

    def refresh_playlists(self):
        """Reload playlists from database"""
        query = self.search_bar.get_text()
        if query:
            self._playlists = self.db.search_playlists(query)
        else:
            self._playlists = self.db.get_all_playlists()

        self._update_list()
        self._update_order_button_state()

    def _update_list(self):
        """Update the list widget"""
        current_id = self.get_selected_playlist_id()

        self.list_widget.clear()
        for playlist in self._playlists:
            item = QListWidgetItem(playlist.name)
            item.setData(Qt.ItemDataRole.UserRole, playlist.id)
            self.list_widget.addItem(item)

            # Restore selection
            if playlist.id == current_id:
                item.setSelected(True)

    def _on_search(self, query: str):
        """Handle search query change"""
        self.refresh_playlists()
        self._update_order_button_state()

    def _on_item_clicked(self, item: QListWidgetItem):
        """Handle item click"""
        playlist_id = item.data(Qt.ItemDataRole.UserRole)
        playlist = self.db.get_playlist(playlist_id)
        if playlist:
            self.playlist_selected.emit(playlist)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """Handle item double-click (rename)"""
        playlist_id = item.data(Qt.ItemDataRole.UserRole)
        playlist = self.db.get_playlist(playlist_id)
        if playlist:
            self._rename_playlist(playlist)

    def _show_context_menu(self, pos):
        """Show context menu for playlist"""
        item = self.list_widget.itemAt(pos)
        if not item:
            return

        playlist_id = item.data(Qt.ItemDataRole.UserRole)
        playlist = self.db.get_playlist(playlist_id)
        if not playlist:
            return

        menu = QMenu(self)

        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(lambda: self._rename_playlist(playlist))

        duplicate_action = menu.addAction("Duplicate")
        duplicate_action.triggered.connect(lambda: self._duplicate_playlist(playlist))

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._delete_playlist(playlist))

        menu.exec(self.list_widget.mapToGlobal(pos))

    def _create_playlist(self):
        """Create a new playlist"""
        dialog = TextInputDialog(
            self,
            title="New Playlist",
            label="Playlist name:"
        )

        if dialog.exec():
            name = dialog.get_text()
            if name:
                playlist = Playlist(name=name)
                playlist.id = self.db.add_playlist(playlist)
                self.refresh_playlists()
                self.playlist_created.emit(playlist)

                # Select the new playlist
                self.select_playlist(playlist.id)

    def _rename_playlist(self, playlist: Playlist):
        """Rename a playlist"""
        dialog = TextInputDialog(
            self,
            title="Rename Playlist",
            label="Playlist name:",
            default=playlist.name
        )

        if dialog.exec():
            name = dialog.get_text()
            if name and name != playlist.name:
                playlist.name = name
                self.db.update_playlist(playlist)
                self.refresh_playlists()

    def _duplicate_playlist(self, playlist: Playlist):
        """Duplicate a playlist"""
        new_playlist = Playlist(name=f"{playlist.name} (copy)")
        new_playlist.id = self.db.add_playlist(new_playlist)

        # Copy tracks
        tracks = self.db.get_playlist_tracks(playlist.id)
        for track in tracks:
            self.db.add_track_to_playlist(new_playlist.id, track.audio_file_id, track.position)

        self.refresh_playlists()
        self.playlist_created.emit(new_playlist)
        self.select_playlist(new_playlist.id)

    def _delete_playlist(self, playlist: Playlist):
        """Delete a playlist"""
        self.db.delete_playlist(playlist.id)
        self.refresh_playlists()
        self.playlist_deleted.emit(playlist.id)

    def get_selected_playlist_id(self) -> Optional[int]:
        """Get the currently selected playlist ID"""
        items = self.list_widget.selectedItems()
        if items:
            return items[0].data(Qt.ItemDataRole.UserRole)
        return None

    def select_playlist(self, playlist_id: int):
        """Select a playlist by ID"""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == playlist_id:
                item.setSelected(True)
                playlist = self.db.get_playlist(playlist_id)
                if playlist:
                    self.playlist_selected.emit(playlist)
                break

    def _set_ordering_enabled(self, enabled: bool):
        self.order_btn.setToolTip("Lock Playlist Order" if enabled else "Unlock Playlist Order")
        self.list_widget.setDragEnabled(enabled)
        self.list_widget.setAcceptDrops(enabled)
        self.list_widget.setDropIndicatorShown(enabled)
        mode = QAbstractItemView.DragDropMode.InternalMove if enabled else QAbstractItemView.DragDropMode.NoDragDrop
        self.list_widget.setDragDropMode(mode)

    def _on_rows_moved(self, parent, start, end, destination, row):
        if not self.order_btn.isChecked():
            return
        self._persist_playlist_order()

    def _persist_playlist_order(self):
        playlist_ids = []
        playlist_by_id = {playlist.id: playlist for playlist in self._playlists}
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            playlist_id = item.data(Qt.ItemDataRole.UserRole)
            playlist_ids.append(playlist_id)
        self.db.reorder_playlists(playlist_ids)
        self._playlists = [playlist_by_id[pid] for pid in playlist_ids if pid in playlist_by_id]

    def _update_order_button_state(self):
        has_query = bool(self.search_bar.get_text())
        if has_query and self.order_btn.isChecked():
            self.order_btn.setChecked(False)
        self.order_btn.setEnabled(not has_query)
