"""Scene list sidebar widget"""

from PyQt6.QtCore import pyqtSignal

from ..database import DatabaseConnection, Scene
from ..shared.base_list_widget import BaseListWidget


class SceneListWidget(BaseListWidget):
    """Sidebar list of scenes"""

    _entity_name = "Scene"
    _display_attr = "title"

    scene_selected = pyqtSignal(Scene)
    scene_created = pyqtSignal(Scene)
    scene_deleted = pyqtSignal(int)

    def __init__(self, db: DatabaseConnection, parent=None):
        super().__init__(db, parent)

    # --- Backward-compatible public API ---

    def refresh_scenes(self):
        self.refresh()

    def get_selected_scene_id(self):
        return self.get_selected_id()

    def select_scene(self, scene_id: int):
        self.select_by_id(scene_id)

    # --- DB operations ---

    def _get_all_items(self):
        return self.db.get_all_scenes()

    def _search_items(self, query):
        return self.db.search_scenes(query)

    def _get_item_by_id(self, item_id):
        return self.db.get_scene(item_id)

    def _create_new_item(self, name):
        scene = Scene(title=name)
        scene.id = self.db.add_scene(scene)
        return scene

    def _update_item(self, item):
        self.db.update_scene(item)

    def _delete_item_by_id(self, item_id):
        self.db.delete_scene(item_id)

    def _duplicate_item(self, scene):
        return self.db.duplicate_scene(scene.id, f"{scene.title} (copy)")

    def _reorder_items(self, ids):
        self.db.reorder_scenes(ids)

    # --- Signal emitters ---

    def _emit_selected(self, item):
        self.scene_selected.emit(item)

    def _emit_created(self, item):
        self.scene_created.emit(item)

    def _emit_deleted(self, item_id):
        self.scene_deleted.emit(item_id)
