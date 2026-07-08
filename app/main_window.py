"""Main application window with tab navigation"""

from PyQt6.QtCore import QEvent, QSettings, Qt, QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .audio import AudioEngine
from .database import DatabaseConnection
from .library import LibraryWidget
from .playlists import PlaylistsWidget
from .remote import RemoteControlFacade
from .scenes import ScenesWidget
from .shared.styles import Styles


class MainWindow(QMainWindow):
    """Main application window"""

    SETTINGS_GROUP = "audio"
    SETTINGS_MASTER_VOLUME = "master_volume"
    SETTINGS_UI_GROUP = "ui"
    SETTINGS_ACTIVE_TAB = "active_tab"
    SETTINGS_LAST_SCENE_ID = "last_scene_id"
    SETTINGS_LAST_PLAYLIST_ID = "last_playlist_id"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SoundManager")
        self.setMinimumSize(1200, 800)
        self._tab_restore_done = False
        self._current_scene_id = None
        self._current_playlist_playing_id = None
        self._current_playing_type = None  # "scene" or "playlist"

        # Initialize core components
        self.db = DatabaseConnection()
        self.db.connect()

        self.audio_engine = AudioEngine.get_instance()

        # Apply global styles
        self.setStyleSheet(Styles.APP_STYLESHEET)

        # Set up UI
        self._setup_ui()
        # After _setup_ui: the facade's state snapshots rely on MainWindow's
        # playback slots being connected (and thus invoked) first.
        self.remote_facade = RemoteControlFacade(self)
        self._restore_master_volume()
        self._restore_active_tab()
        self._restore_last_scene()
        self._restore_last_playlist()

    def _setup_ui(self):
        """Set up the main UI components"""
        # Central widget with tab navigation
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        top_bar_widget = QWidget()
        top_bar_widget.setObjectName("topBarWidget")
        top_bar_widget.setStyleSheet(Styles.widget_panel_style("QWidget#topBarWidget"))
        master_bar = QHBoxLayout(top_bar_widget)
        master_bar.setContentsMargins(18, 14, 18, 14)
        master_bar.setSpacing(14)

        master_label = QLabel("Master Volume")
        master_label.setStyleSheet(Styles.title_style(size=13))
        master_bar.addWidget(master_label)

        self.master_slider = QSlider(Qt.Orientation.Horizontal)
        # Don't hold keyboard focus, so the playback arrow shortcuts aren't
        # redirected into the volume after the slider is clicked. (Kept wheel-
        # adjustable: it's in the top bar, not a scroll area, so it can't snag
        # list scrolling.)
        self.master_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.master_slider.setRange(0, 100)
        self.master_slider.setValue(self.audio_engine.master_volume)
        self.master_slider.setFixedWidth(260)
        self.master_slider.valueChanged.connect(self._on_master_volume_changed)
        master_bar.addWidget(self.master_slider)

        self.master_value_label = QLabel(f"{self.audio_engine.master_volume}%")
        self.master_value_label.setFixedWidth(50)
        self.master_value_label.setStyleSheet(Styles.subtle_text_style(size=12))
        master_bar.addWidget(self.master_value_label)

        master_bar.addStretch()

        self.currently_playing_widget = QWidget()
        current_layout = QVBoxLayout(self.currently_playing_widget)
        current_layout.setContentsMargins(0, 0, 0, 0)
        current_layout.setSpacing(4)

        current_label = QLabel("Currently Playing")
        current_label.setStyleSheet(Styles.subtle_text_style(size=11))
        current_layout.addWidget(current_label)

        self.current_scene_btn = QPushButton("None")
        self.current_scene_btn.setStyleSheet(Styles.ghost_button_style())
        self.current_scene_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        current_layout.addWidget(self.current_scene_btn)

        self.currently_playing_widget.hide()
        master_bar.addWidget(self.currently_playing_widget)

        layout.addWidget(top_bar_widget)

        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.tabBar().setDrawBase(False)
        layout.addWidget(self.tab_widget, 1)

        # Library tab
        self.library_widget = LibraryWidget(self.db, self.audio_engine)
        self.tab_widget.addTab(self.library_widget, "Library")

        # Scenes tab
        self.scenes_widget = ScenesWidget(self.db, self.audio_engine)
        self.tab_widget.addTab(self.scenes_widget, "Scenes")

        # Playlists tab
        self.playlists_widget = PlaylistsWidget(self.db, self.audio_engine)
        self.tab_widget.addTab(self.playlists_widget, "Playlists")

        # Connect currentChanged only AFTER the tabs exist: adding the first tab
        # auto-fires currentChanged, and the handler references every tab widget.
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Connect signals between modules
        self._connect_signals()

        # Playback keyboard shortcuts
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        """Install an application event filter for the playback transport keys.

        Why a filter rather than QShortcut: the keys we want are also used by
        focused widgets — the sidebar ``QListWidget`` consumes Space, sliders
        consume the arrows — so a QShortcut is unreliably swallowed (Space right
        after clicking a scene) or conversely steals a key the widget needs. The
        filter dispatches each key for transport but yields to widgets that
        legitimately use it (see ``_handle_transport_key``). On macOS Qt reports
        the ⌘ key as ``ControlModifier``, so Ctrl+Arrow here means ⌘+Arrow.
        """
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def eventFilter(self, obj, event):
        if (
            isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
            and not event.isAutoRepeat()
            # Don't hijack keys while a modal dialog (rename, playlist/color
            # picker) is open — those belong to the dialog.
            and QApplication.activeModalWidget() is None
            and self._handle_transport_key(
                event.key(), event.modifiers(), QApplication.focusWidget()
            )
        ):
            return True
        return super().eventFilter(obj, event)

    def _handle_transport_key(self, key, modifiers, focus) -> bool:
        """Dispatch a transport key; return True if handled (consume the event).

        Yields (False) when the focused widget legitimately uses the key: text
        inputs for every shortcut, plus sliders/spinboxes for the bare Right
        (they step on arrows). So Space still types in the search box and
        activates a focused button, and Right still nudges a focused volume slider.
        """
        # macOS tags arrow keys (and Home/End/PageUp/Down) with KeypadModifier;
        # QKeySequence normalizes that away but a manual filter must strip it, or
        # the comparisons below never match and the arrows appear dead.
        mods = modifiers & ~Qt.KeyboardModifier.KeypadModifier
        no_mod = mods == Qt.KeyboardModifier.NoModifier
        ctrl = mods == Qt.KeyboardModifier.ControlModifier  # ⌘ on macOS
        is_text = isinstance(
            focus, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)
        )

        if no_mod and key == Qt.Key.Key_Space:
            if is_text or isinstance(focus, QAbstractButton):
                return False
            self.toggle_play_pause()
            return True
        if no_mod and key == Qt.Key.Key_Right:
            if is_text or isinstance(focus, QAbstractSlider):
                return False
            self.next_track()
            return True
        if ctrl and key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            if is_text:
                return False
            self._shortcut_step_item(1 if key == Qt.Key.Key_Right else -1)
            return True
        return False

    def _active_play_widget(self) -> "ScenesWidget | PlaylistsWidget | None":
        """The scenes/playlists widget for the current tab (None on Library)."""
        current = self.tab_widget.currentWidget()
        if current is self.scenes_widget:
            return self.scenes_widget
        if current is self.playlists_widget:
            return self.playlists_widget
        return None

    def toggle_play_pause(self):
        """Pause whatever is playing; if idle, start/resume the item open in
        the current Scenes/Playlists tab. Shared by the Space shortcut and the
        remote-control facade — keep them on this single path."""
        if self._current_playing_type == "scene":
            self.scenes_widget.pause_active()
        elif self._current_playing_type == "playlist":
            self.playlists_widget.pause_active()
        else:
            widget = self._active_play_widget()
            if widget is not None:
                widget.toggle_playback()

    def next_track(self):
        """Advance the playing playlist to its next track (no-op when a scene
        is playing or nothing is). Shared by the Right shortcut and the
        remote-control facade."""
        if self._current_playing_type == "playlist":
            self.playlists_widget.next_track()

    def current_playback(self) -> tuple[str, int | None] | None:
        """(type, id) of the actively playing scene/playlist, or None if idle."""
        if self._current_playing_type == "scene":
            return ("scene", self._current_scene_id)
        if self._current_playing_type == "playlist":
            return ("playlist", self._current_playlist_playing_id)
        return None

    def _shortcut_step_item(self, delta: int):
        """Ctrl+Left / Ctrl+Right: step to the previous/next scene-or-playlist
        in the current tab's sidebar (no wrap). If something was playing, the
        newly selected item starts playing (mutual exclusivity stops the old)."""
        widget = self._active_play_widget()
        if widget is None:
            return
        was_playing = self._current_playing_type is not None
        new_id = widget.select_relative(delta)
        if new_id is not None and was_playing:
            widget.play_current()

    def _connect_signals(self):
        """Connect signals between different modules"""
        # When library is updated, refresh scene track info
        self.library_widget.library_updated.connect(
            self.scenes_widget.refresh_current_scene
        )
        self.scenes_widget.playback_state_changed.connect(
            self._on_scene_playback_changed
        )
        self.scenes_widget.scene_selection_changed.connect(
            self._on_scene_selection_changed
        )
        self.playlists_widget.playlist_selection_changed.connect(
            self._on_playlist_selection_changed
        )
        self.playlists_widget.playback_state_changed.connect(
            self._on_playlist_playback_changed
        )
        self.current_scene_btn.clicked.connect(self._on_current_playing_clicked)

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
        widget = self.tab_widget.widget(index)
        if widget is not self.library_widget:
            self.library_widget.file_table.stop_playback()
        # Focus the tab's list so its header order/search buttons don't keep
        # keyboard focus (which would make Space toggle the order button instead
        # of play/pause). Deferred so it runs after Qt's own tab-switch focus.
        if widget is self.scenes_widget:
            QTimer.singleShot(0, self.scenes_widget.focus_list)
        elif widget is self.playlists_widget:
            QTimer.singleShot(0, self.playlists_widget.focus_list)
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

    def _on_playlist_selection_changed(self, playlist_id: int):
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_UI_GROUP)
        settings.setValue(self.SETTINGS_LAST_PLAYLIST_ID, playlist_id)
        settings.endGroup()

    def _restore_last_playlist(self):
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_UI_GROUP)
        playlist_id = settings.value(self.SETTINGS_LAST_PLAYLIST_ID, type=int)
        settings.endGroup()
        if playlist_id is None:
            return
        self.playlists_widget.select_playlist(playlist_id)

    def _on_scene_playback_changed(self, scene_id, scene_title, is_playing: bool):
        if is_playing and scene_id:
            # Mutual exclusivity: stop any active playlist before activating scene
            if self._current_playing_type == "playlist":
                self.playlists_widget.stop_all_playback()
            self._current_scene_id = scene_id
            self._current_playing_type = "scene"
            self.current_scene_btn.setText(f"Scene: {scene_title or 'Untitled Scene'}")
            self.currently_playing_widget.show()
        else:
            if self._current_playing_type == "scene":
                self._current_scene_id = scene_id if scene_id else None
                self._current_playing_type = None
                self.currently_playing_widget.hide()

    def _on_playlist_playback_changed(
        self, playlist_id, playlist_name, is_playing: bool
    ):
        if is_playing and playlist_id:
            # Mutual exclusivity: stop any active scene before activating playlist
            if self._current_playing_type == "scene":
                self.scenes_widget.stop_all_playback()
            self._current_playlist_playing_id = playlist_id
            self._current_playing_type = "playlist"
            self.current_scene_btn.setText(
                f"Playlist: {playlist_name or 'Untitled Playlist'}"
            )
            self.currently_playing_widget.show()
        else:
            if self._current_playing_type == "playlist":
                self._current_playlist_playing_id = None
                self._current_playing_type = None
                self.currently_playing_widget.hide()

    def _on_current_playing_clicked(self):
        if self._current_playing_type == "scene" and self._current_scene_id:
            scenes_index = self.tab_widget.indexOf(self.scenes_widget)
            if scenes_index != -1:
                self.tab_widget.setCurrentIndex(scenes_index)
            self.scenes_widget.select_scene(self._current_scene_id)
        elif (
            self._current_playing_type == "playlist"
            and self._current_playlist_playing_id
        ):
            playlists_index = self.tab_widget.indexOf(self.playlists_widget)
            if playlists_index != -1:
                self.tab_widget.setCurrentIndex(playlists_index)
            self.playlists_widget.select_playlist(self._current_playlist_playing_id)

    def closeEvent(self, event):
        """Handle application close"""
        # Stop all audio
        self.scenes_widget.stop_all_playback()
        self.playlists_widget.stop_all_playback()

        # Close database
        self.db.close()

        # Release audio engine
        self.audio_engine.release()

        event.accept()
