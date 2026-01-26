"""Scene list sidebar widget"""

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QMenu, QAbstractItemView
)
from PyQt6.QtCore import pyqtSignal, Qt

from ..database import DatabaseConnection, Scene
from ..library.search_bar import SearchBar
from ..shared.icons import IconLibrary
from ..shared.dialogs import TextInputDialog


class SceneListWidget(QWidget):
    """Sidebar list of scenes"""

    scene_selected = pyqtSignal(Scene)  # Emitted when a scene is selected
    scene_created = pyqtSignal(Scene)  # Emitted when a new scene is created
    scene_deleted = pyqtSignal(int)  # Emitted when a scene is deleted (scene_id)

    def __init__(self, db: DatabaseConnection, parent=None):
        super().__init__(parent)
        self.db = db
        self._scenes: list[Scene] = []
        self._icons = IconLibrary()

        self.setMinimumWidth(200)
        self.setMaximumWidth(300)

        self._setup_ui()
        self.refresh_scenes()
        self._update_order_button_state()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("Scenes")
        header_label.setStyleSheet("font-weight: bold; font-size: 16px; padding: 8px;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        self.order_btn = QPushButton()
        self.order_btn.setCheckable(True)
        self.order_btn.setFixedSize(28, 28)
        self.order_btn.setIcon(self._icons.icon("list"))
        self.order_btn.setIconSize(self.order_btn.size())
        self.order_btn.setToolTip("Unlock Scene Order")
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
        self.search_bar = SearchBar(placeholder="Search scenes...")
        self.search_bar.search_changed.connect(self._on_search)
        layout.addWidget(self.search_bar)

        # Scene list
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.list_widget.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self.list_widget)

        # New scene button
        new_btn = QPushButton("+ New Scene")
        new_btn.clicked.connect(self._create_scene)
        layout.addWidget(new_btn)

    def refresh_scenes(self):
        """Reload scenes from database"""
        query = self.search_bar.get_text()
        if query:
            self._scenes = self.db.search_scenes(query)
        else:
            self._scenes = self.db.get_all_scenes()

        self._update_list()
        self._update_order_button_state()

    def _update_list(self):
        """Update the list widget"""
        current_id = self.get_selected_scene_id()

        self.list_widget.clear()
        for scene in self._scenes:
            item = QListWidgetItem(scene.title)
            item.setData(Qt.ItemDataRole.UserRole, scene.id)
            self.list_widget.addItem(item)

            # Restore selection
            if scene.id == current_id:
                item.setSelected(True)

    def _on_search(self, query: str):
        """Handle search query change"""
        self.refresh_scenes()
        self._update_order_button_state()

    def _on_item_clicked(self, item: QListWidgetItem):
        """Handle item click"""
        scene_id = item.data(Qt.ItemDataRole.UserRole)
        scene = self.db.get_scene(scene_id)
        if scene:
            self.scene_selected.emit(scene)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """Handle item double-click (rename)"""
        scene_id = item.data(Qt.ItemDataRole.UserRole)
        scene = self.db.get_scene(scene_id)
        if scene:
            self._rename_scene(scene)

    def _show_context_menu(self, pos):
        """Show context menu for scene"""
        item = self.list_widget.itemAt(pos)
        if not item:
            return

        scene_id = item.data(Qt.ItemDataRole.UserRole)
        scene = self.db.get_scene(scene_id)
        if not scene:
            return

        menu = QMenu(self)

        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(lambda: self._rename_scene(scene))

        duplicate_action = menu.addAction("Duplicate")
        duplicate_action.triggered.connect(lambda: self._duplicate_scene(scene))

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._delete_scene(scene))

        menu.exec(self.list_widget.mapToGlobal(pos))

    def _create_scene(self):
        """Create a new scene"""
        dialog = TextInputDialog(
            self,
            title="New Scene",
            label="Scene name:"
        )

        if dialog.exec():
            name = dialog.get_text()
            if name:
                scene = Scene(title=name)
                scene.id = self.db.add_scene(scene)
                self.refresh_scenes()
                self.scene_created.emit(scene)

                # Select the new scene
                self.select_scene(scene.id)

    def _rename_scene(self, scene: Scene):
        """Rename a scene"""
        dialog = TextInputDialog(
            self,
            title="Rename Scene",
            label="Scene name:",
            default=scene.title
        )

        if dialog.exec():
            name = dialog.get_text()
            if name and name != scene.title:
                scene.title = name
                self.db.update_scene(scene)
                self.refresh_scenes()

    def _duplicate_scene(self, scene: Scene):
        """Duplicate a scene"""
        # Create new scene
        new_scene = Scene(title=f"{scene.title} (copy)")
        new_scene.id = self.db.add_scene(new_scene)

        # Copy tracks
        tracks = self.db.get_scene_tracks(scene.id)
        for track in tracks:
            self.db.add_track_to_scene(
                new_scene.id,
                track.audio_file_id,
                track.position,
                play_mode=track.play_mode,
            )
            # Get the new track and update its settings
            new_tracks = self.db.get_scene_tracks(new_scene.id)
            for new_track in new_tracks:
                if new_track.audio_file_id == track.audio_file_id:
                    new_track.volume = track.volume
                    new_track.is_repeat = track.is_repeat
                    new_track.play_mode = track.play_mode
                    self.db.update_track_settings(new_track)
                    break

        self.refresh_scenes()
        self.scene_created.emit(new_scene)
        self.select_scene(new_scene.id)

    def _delete_scene(self, scene: Scene):
        """Delete a scene"""
        self.db.delete_scene(scene.id)
        self.refresh_scenes()
        self.scene_deleted.emit(scene.id)

    def get_selected_scene_id(self) -> Optional[int]:
        """Get the currently selected scene ID"""
        items = self.list_widget.selectedItems()
        if items:
            return items[0].data(Qt.ItemDataRole.UserRole)
        return None

    def select_scene(self, scene_id: int):
        """Select a scene by ID"""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == scene_id:
                item.setSelected(True)
                scene = self.db.get_scene(scene_id)
                if scene:
                    self.scene_selected.emit(scene)
                break

    def _set_ordering_enabled(self, enabled: bool):
        self.order_btn.setToolTip("Lock Scene Order" if enabled else "Unlock Scene Order")
        self.list_widget.setDragEnabled(enabled)
        self.list_widget.setAcceptDrops(enabled)
        self.list_widget.setDropIndicatorShown(enabled)
        mode = QAbstractItemView.DragDropMode.InternalMove if enabled else QAbstractItemView.DragDropMode.NoDragDrop
        self.list_widget.setDragDropMode(mode)

    def _on_rows_moved(self, parent, start, end, destination, row):
        if not self.order_btn.isChecked():
            return
        self._persist_scene_order()

    def _persist_scene_order(self):
        scene_ids = []
        scene_by_id = {scene.id: scene for scene in self._scenes}
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            scene_id = item.data(Qt.ItemDataRole.UserRole)
            scene_ids.append(scene_id)
        self.db.reorder_scenes(scene_ids)
        self._scenes = [scene_by_id[sid] for sid in scene_ids if sid in scene_by_id]

    def _update_order_button_state(self):
        has_query = bool(self.search_bar.get_text())
        if has_query and self.order_btn.isChecked():
            self.order_btn.setChecked(False)
        self.order_btn.setEnabled(not has_query)
