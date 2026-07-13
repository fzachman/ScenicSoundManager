"""Main scenes view widget"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QSplitter, QWidget

from ..audio import AudioEngine
from ..database import DatabaseConnection, Scene
from .scene_editor import SceneEditor
from .scene_list import SceneListWidget


class ScenesWidget(QWidget):
    """Main scenes view with list and editor"""

    playback_state_changed = pyqtSignal(
        object, object, bool
    )  # scene_id, scene_title, is_playing
    scene_selection_changed = pyqtSignal(int)  # scene_id
    preset_changed = pyqtSignal(int, int)  # scene_id, slot

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

        # Scene list (left sidebar)
        self.scene_list = SceneListWidget(self.db)
        splitter.addWidget(self.scene_list)

        # Scene editor (right panel)
        self.scene_editor = SceneEditor(self.db, self.audio_engine)
        splitter.addWidget(self.scene_editor)

        # Set initial sizes (1:3 ratio)
        splitter.setSizes([250, 750])

        layout.addWidget(splitter)

    def _connect_signals(self):
        """Connect signals between components"""
        self.scene_list.scene_selected.connect(self._on_scene_selected)
        self.scene_list.scene_created.connect(self._on_scene_created)
        self.scene_list.scene_deleted.connect(self._on_scene_deleted)
        self.scene_editor.playback_state_changed.connect(
            self.playback_state_changed.emit
        )
        self.scene_editor.preset_changed.connect(self.preset_changed.emit)

    def _on_scene_selected(self, scene: Scene):
        """Handle scene selection"""
        self.scene_editor.load_scene(scene)
        if scene.id is not None:
            self.scene_selection_changed.emit(scene.id)

    def _on_scene_created(self, scene: Scene):
        """Handle new scene creation"""
        self.scene_editor.load_scene(scene)
        if scene.id is not None:
            self.scene_selection_changed.emit(scene.id)

    def _on_scene_deleted(self, scene_id: int):
        """Handle scene deletion"""
        self.scene_editor.clear()

    def stop_all_playback(self, fade_ms: int = 0):
        """Stop all audio playback (immediately, or fading over ``fade_ms``)"""
        self.scene_editor.stop_all(fade_ms)

    def active_playback(self) -> tuple[int, bool] | None:
        """(scene_id, is_playing) of the scene owning playback, or None."""
        return self.scene_editor.active_playback()

    def refresh_current_scene(self):
        """Refresh the currently loaded scene"""
        self.scene_editor.refresh()

    def select_scene(self, scene_id: int):
        """Select and load a scene by ID"""
        self.scene_list.select_scene(scene_id)

    # --- Keyboard-shortcut entry points (delegated to editor / list) ---

    def toggle_playback(self):
        """Play/pause the open scene."""
        self.scene_editor.toggle_playback()

    def pause_active(self):
        """Pause the playing scene."""
        self.scene_editor.pause_active()

    def play_current(self):
        """Start the open scene unless it is already playing."""
        self.scene_editor.play_current()

    def switch_preset(self, slot: int):
        """Activate a preset on the open scene."""
        self.scene_editor.switch_preset(slot)

    def select_relative(self, delta: int) -> int | None:
        """Step the scene-list selection by ``delta`` (next/prev)."""
        return self.scene_list.select_relative(delta)

    def focus_list(self):
        """Focus the scene list (so transport shortcuts work when the tab opens)."""
        self.scene_list.focus_list()
