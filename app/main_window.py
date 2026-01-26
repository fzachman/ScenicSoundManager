"""Main application window with tab navigation"""

from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton
)
from PyQt6.QtCore import Qt, QSettings

from .database import DatabaseConnection
from .audio import AudioEngine
from .library import LibraryWidget
from .scenes import ScenesWidget
from .shared.styles import Styles


class MainWindow(QMainWindow):
    """Main application window"""

    SETTINGS_GROUP = "audio"
    SETTINGS_MASTER_VOLUME = "master_volume"
    SETTINGS_UI_GROUP = "ui"
    SETTINGS_ACTIVE_TAB = "active_tab"
    SETTINGS_LAST_SCENE_ID = "last_scene_id"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SoundManager")
        self.setMinimumSize(1200, 800)
        self._tab_restore_done = False
        self._current_scene_id = None

        # Initialize core components
        self.db = DatabaseConnection()
        self.db.connect()

        self.audio_engine = AudioEngine.get_instance()

        # Apply global styles
        self.setStyleSheet(Styles.APP_STYLESHEET)

        # Set up UI
        self._setup_ui()
        self._restore_master_volume()
        self._restore_active_tab()
        self._restore_last_scene()

    def _setup_ui(self):
        """Set up the main UI components"""
        # Central widget with tab navigation
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        master_bar = QHBoxLayout()
        master_bar.setContentsMargins(12, 8, 12, 8)

        master_label = QLabel("Master Volume")
        master_label.setStyleSheet("font-weight: bold;")
        master_bar.addWidget(master_label)

        self.master_slider = QSlider(Qt.Orientation.Horizontal)
        self.master_slider.setRange(0, 100)
        self.master_slider.setValue(self.audio_engine.master_volume)
        self.master_slider.setFixedWidth(220)
        self.master_slider.valueChanged.connect(self._on_master_volume_changed)
        master_bar.addWidget(self.master_slider)

        self.master_value_label = QLabel(f"{self.audio_engine.master_volume}%")
        self.master_value_label.setFixedWidth(50)
        master_bar.addWidget(self.master_value_label)

        master_bar.addStretch()

        self.currently_playing_widget = QWidget()
        current_layout = QVBoxLayout(self.currently_playing_widget)
        current_layout.setContentsMargins(0, 0, 0, 0)
        current_layout.setSpacing(2)

        current_label = QLabel("Currently Playing")
        current_label.setStyleSheet(f"color: {Styles.TEXT_MUTED}; font-size: 11px;")
        current_layout.addWidget(current_label)

        self.current_scene_btn = QPushButton("None")
        self.current_scene_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Styles.TEXT};
                text-align: left;
                padding: 0;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {Styles.PRIMARY};
            }}
        """)
        self.current_scene_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        current_layout.addWidget(self.current_scene_btn)

        self.currently_playing_widget.hide()
        master_bar.addWidget(self.currently_playing_widget)

        layout.addLayout(master_bar)

        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tab_widget)

        # Library tab
        self.library_widget = LibraryWidget(self.db, self.audio_engine)
        self.tab_widget.addTab(self.library_widget, "Library")

        # Scenes tab
        self.scenes_widget = ScenesWidget(self.db, self.audio_engine)
        self.tab_widget.addTab(self.scenes_widget, "Scenes")

        # Connect signals between modules
        self._connect_signals()

    def _connect_signals(self):
        """Connect signals between different modules"""
        # When library is updated, refresh scene track info
        self.library_widget.library_updated.connect(
            self.scenes_widget.refresh_current_scene
        )
        self.scenes_widget.playback_state_changed.connect(self._on_playback_state_changed)
        self.scenes_widget.scene_selection_changed.connect(self._on_scene_selection_changed)
        self.current_scene_btn.clicked.connect(self._on_current_scene_clicked)

    def _on_master_volume_changed(self, value: int):
        self.audio_engine.master_volume = value
        self.master_value_label.setText(f"{value}%")
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        settings.setValue(self.SETTINGS_MASTER_VOLUME, value)
        settings.endGroup()

    def _restore_master_volume(self):
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        value = settings.value(self.SETTINGS_MASTER_VOLUME, type=int)
        settings.endGroup()
        if value is None:
            return
        self.audio_engine.master_volume = value
        self.master_slider.blockSignals(True)
        self.master_slider.setValue(value)
        self.master_slider.blockSignals(False)
        self.master_value_label.setText(f"{value}%")

    def _on_tab_changed(self, index: int):
        if self.tab_widget.widget(index) is not self.library_widget:
            self.library_widget.file_table.stop_playback()
        if not self._tab_restore_done:
            return
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_UI_GROUP)
        settings.setValue(self.SETTINGS_ACTIVE_TAB, index)
        settings.endGroup()

    def _restore_active_tab(self):
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_UI_GROUP)
        index = settings.value(self.SETTINGS_ACTIVE_TAB, type=int)
        settings.endGroup()
        if index is None:
            return
        if 0 <= index < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(index)
        self._tab_restore_done = True

    def _on_scene_selection_changed(self, scene_id: int):
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_UI_GROUP)
        settings.setValue(self.SETTINGS_LAST_SCENE_ID, scene_id)
        settings.endGroup()

    def _restore_last_scene(self):
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_UI_GROUP)
        scene_id = settings.value(self.SETTINGS_LAST_SCENE_ID, type=int)
        settings.endGroup()
        if scene_id is None:
            return
        self.scenes_widget.select_scene(scene_id)

    def _on_playback_state_changed(self, scene_id, scene_title, is_playing: bool):
        if is_playing and scene_id:
            self._current_scene_id = scene_id
            self.current_scene_btn.setText(scene_title or "Untitled Scene")
            self.currently_playing_widget.show()
        else:
            self._current_scene_id = scene_id if scene_id else None
            self.currently_playing_widget.hide()

    def _on_current_scene_clicked(self):
        if not self._current_scene_id:
            return
        scenes_index = self.tab_widget.indexOf(self.scenes_widget)
        if scenes_index != -1:
            self.tab_widget.setCurrentIndex(scenes_index)
        self.scenes_widget.select_scene(self._current_scene_id)

    def closeEvent(self, event):
        """Handle application close"""
        # Stop all audio
        self.scenes_widget.stop_all_playback()

        # Close database
        self.db.close()

        # Release audio engine
        self.audio_engine.release()

        event.accept()
