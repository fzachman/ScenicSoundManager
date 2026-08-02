"""Main application window with tab navigation"""

import os
import sqlite3
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path

from PyQt6.QtCore import QEvent, QProcess, QSettings, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QKeyEvent, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import APP_DISPLAY_NAME, __version__
from .audio import TRANSITION_FADE_MS, AudioEngine, SoundboardPlayer
from .database import (
    DatabaseConnection,
    NewerDatabaseError,
    swap_database,
    validate_backup,
)
from .library import LibraryWidget
from .playlists import PlaylistsWidget
from .remote import (
    DEFAULT_PORT,
    SETTINGS_ENABLED,
    SETTINGS_GROUP,
    SETTINGS_PORT,
    RemoteControlFacade,
    RemoteControlServer,
)
from .scenes import ScenesWidget
from .settings_dialog import SettingsDialog
from .shared.logging import get_logger
from .shared.styles import Styles
from .soundboard import SoundboardContent, SoundboardDock
from .update_check import UpdateChecker

logger = get_logger(__name__)

# Beta feedback Google Form (Help > Send Feedback…). Also linked from the
# README and docs/release-notes-base.md — update all three together.
FEEDBACK_FORM_URL = "https://forms.gle/QyTAhJCRd18NvHNn6"


class MainWindow(QMainWindow):
    """Main application window"""

    SETTINGS_GROUP = "audio"
    SETTINGS_MASTER_VOLUME = "master_volume"
    SETTINGS_UI_GROUP = "ui"
    SETTINGS_ACTIVE_TAB = "active_tab"
    SETTINGS_WINDOW_STATE = "window_state"
    SETTINGS_WINDOW_GEOMETRY = "window_geometry"
    SETTINGS_LAST_SCENE_ID = "last_scene_id"
    SETTINGS_LAST_PLAYLIST_ID = "last_playlist_id"
    SETTINGS_SKIP_UPDATE = "updates/skip_version"

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.setMinimumSize(1200, 800)
        self._tab_restore_done = False
        self._current_scene_id = None
        self._current_playlist_playing_id = None
        self._current_playing_type = None  # "scene" or "playlist"
        self._pending_restore: str | None = None  # backup path; see closeEvent

        # Initialize core components
        self.db = DatabaseConnection(seed_default_tags=True)
        try:
            self.db.connect()
        except NewerDatabaseError:
            QMessageBox.critical(
                self,
                "Library Too New",
                f"Your library database was written by a newer version of "
                f"{APP_DISPLAY_NAME} than this one.\n\n"
                "Update the app to its latest release, or restore a backup "
                "made by this version (File → Restore Database…).",
            )
            raise SystemExit(1) from None

        self.audio_engine = AudioEngine.get_instance()
        if not self.audio_engine.available:
            # After the window shows: everything but playback still works,
            # but the user must be told why the app is silent.
            QTimer.singleShot(0, self._warn_missing_audio)

        # Apply global styles
        self.setStyleSheet(Styles.APP_STYLESHEET)

        # Set up UI
        self._setup_ui()
        # After _setup_ui: the facade's state snapshots rely on MainWindow's
        # playback slots being connected (and thus invoked) first.
        self.remote_facade = RemoteControlFacade(self)
        self.remote_server = self._start_remote_server()
        self._restore_master_volume()
        self._restore_active_tab()
        self._restore_last_scene()
        self._restore_last_playlist()
        self._restore_window_state()

        # Notify-only update check, delayed so startup never races it.
        self._update_checker = UpdateChecker(parent=self)
        self._update_checker.update_available.connect(self._on_update_available)
        QTimer.singleShot(3000, self._update_checker.check)

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

        # Soundboard panel: a permanent dock below the content, deliberately
        # outside the scene/playlist mutual-exclusivity chain (its sounds play
        # over whatever is active).
        self.soundboard_player = SoundboardPlayer(self.audio_engine)
        self.soundboard_content = SoundboardContent(
            self.db, self.audio_engine, self.soundboard_player
        )
        self.soundboard_dock = SoundboardDock(content=self.soundboard_content)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.soundboard_dock)

        # Connect signals between modules
        self._connect_signals()

        # Playback keyboard shortcuts
        self._setup_shortcuts()

        # Native menu bar
        self._setup_menus()

    def _setup_menus(self):
        """Build the native menu bar.

        macOS relocates the About/Settings/Quit actions out of the File menu
        into the application menu via their MenuRoles (the app menu's *name*
        comes from the bundle plist, so it reads "Python" when running
        unbundled). The Scenes/Playlists/Soundboards menus rebuild from the
        database on every aboutToShow, so they never go stale and need no
        CRUD signal wiring.
        """
        menubar = self.menuBar()
        if menubar is None:  # pragma: no cover - QMainWindow creates one
            return

        file_menu = QMenu("File", self)
        menubar.addMenu(file_menu)

        about_action = QAction(f"About {APP_DISPLAY_NAME}", self)
        about_action.setMenuRole(QAction.MenuRole.AboutRole)
        about_action.triggered.connect(self._show_about)
        file_menu.addAction(about_action)

        settings_action = QAction("Settings…", self)
        settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        settings_action.setShortcut(QKeySequence.StandardKey.Preferences)
        settings_action.triggered.connect(self._show_settings)
        file_menu.addAction(settings_action)

        # close(), not QApplication.quit(): closeEvent owns the teardown
        # (audio stop, remote server stop, DB close, engine release).
        quit_action = QAction(f"Quit {APP_DISPLAY_NAME}", self)
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        import_menu = QMenu("Import", self)
        file_menu.addMenu(import_menu)
        import_files_action = QAction("Files…", self)
        import_files_action.setShortcut(QKeySequence.StandardKey.Open)
        import_files_action.triggered.connect(self.import_files)
        import_menu.addAction(import_files_action)
        import_folder_action = QAction("Folder…", self)
        import_folder_action.triggered.connect(self.import_folder)
        import_menu.addAction(import_folder_action)

        file_menu.addSeparator()
        backup_action = QAction("Back Up Database…", self)
        backup_action.triggered.connect(self._backup_database)
        file_menu.addAction(backup_action)
        restore_action = QAction("Restore Database…", self)
        restore_action.triggered.connect(self._restore_database)
        file_menu.addAction(restore_action)
        repair_action = QAction("Repair Library…", self)
        repair_action.triggered.connect(self._repair_library)
        file_menu.addAction(repair_action)

        # The transport keys (Space/→) are deliberately NOT bound as action
        # shortcuts: they live in the application event filter so they can
        # yield to text fields and sliders (see _setup_shortcuts). The labels
        # only advertise them.
        playback_menu = QMenu("Playback", self)
        menubar.addMenu(playback_menu)
        play_pause_action = QAction("Play/Pause  (Space)", self)
        play_pause_action.triggered.connect(self.toggle_play_pause)
        playback_menu.addAction(play_pause_action)
        next_track_action = QAction("Next Track  (→)", self)
        next_track_action.triggered.connect(self.next_track)
        playback_menu.addAction(next_track_action)
        playback_menu.addSeparator()
        stop_all_action = QAction("Stop All", self)
        stop_all_action.triggered.connect(self.stop_all_playback)
        playback_menu.addAction(stop_all_action)

        view_menu = QMenu("View", self)
        menubar.addMenu(view_menu)
        tabs = [
            ("Library", self.library_widget),
            ("Scenes", self.scenes_widget),
            ("Playlists", self.playlists_widget),
        ]
        for i, (label, widget) in enumerate(tabs):
            tab_action = QAction(label, self)
            tab_action.setShortcut(f"Ctrl+{i + 1}")  # ⌘1/2/3 on macOS
            tab_action.triggered.connect(
                lambda checked=False, w=widget: self.tab_widget.setCurrentWidget(w)
            )
            view_menu.addAction(tab_action)
        view_menu.addSeparator()
        self._soundboard_view_action = QAction("Soundboard", self)
        self._soundboard_view_action.setCheckable(True)
        self._soundboard_view_action.triggered.connect(self._toggle_soundboard_panel)
        view_menu.addAction(self._soundboard_view_action)
        view_menu.aboutToShow.connect(self._sync_view_menu)

        self.scenes_menu = QMenu("Scenes", self)
        menubar.addMenu(self.scenes_menu)
        self.scenes_menu.aboutToShow.connect(self._rebuild_scenes_menu)

        self.playlists_menu = QMenu("Playlists", self)
        menubar.addMenu(self.playlists_menu)
        self.playlists_menu.aboutToShow.connect(self._rebuild_playlists_menu)

        self.soundboards_menu = QMenu("Soundboards", self)
        menubar.addMenu(self.soundboards_menu)
        self.soundboards_menu.aboutToShow.connect(self._rebuild_soundboards_menu)

        help_menu = QMenu("Help", self)
        menubar.addMenu(help_menu)
        shortcuts_action = QAction("Keyboard Shortcuts", self)
        shortcuts_action.triggered.connect(self._show_shortcuts_help)
        help_menu.addAction(shortcuts_action)
        feedback_action = QAction("Send Feedback…", self)
        feedback_action.triggered.connect(self._send_feedback)
        help_menu.addAction(feedback_action)

        # Populate the dynamic menus now, not just on aboutToShow: the macOS
        # native menu bar HIDES empty menus, so without an initial build the
        # Scenes/Playlists/Soundboards titles never appear at all.
        self._rebuild_scenes_menu()
        self._rebuild_playlists_menu()
        self._rebuild_soundboards_menu()

    def _rebuild_scenes_menu(self):
        playing_id = (
            self._current_scene_id if self._current_playing_type == "scene" else None
        )
        self._populate_item_menu(
            self.scenes_menu,
            [(s.id, s.title or "Untitled Scene") for s in self.db.get_all_scenes()],
            empty_text="No Scenes",
            checked_id=playing_id,
            on_selected=self.show_scene,
        )

    def _rebuild_playlists_menu(self):
        playing_id = (
            self._current_playlist_playing_id
            if self._current_playing_type == "playlist"
            else None
        )
        self._populate_item_menu(
            self.playlists_menu,
            [
                (p.id, p.name or "Untitled Playlist")
                for p in self.db.get_all_playlists()
            ],
            empty_text="No Playlists",
            checked_id=playing_id,
            on_selected=self.show_playlist,
        )

    def _rebuild_soundboards_menu(self):
        # The checkmark marks the board open in the panel (there is no
        # "playing" board — soundboard sounds are one-shots).
        self._populate_item_menu(
            self.soundboards_menu,
            [(b.id, b.name) for b in self.db.get_all_soundboards()],
            empty_text="No Soundboards",
            checked_id=self.soundboard_content.current_board_id(),
            on_selected=self.show_soundboard,
        )

    @staticmethod
    def _populate_item_menu(
        menu: QMenu,
        items: list[tuple[int | None, str]],
        empty_text: str,
        checked_id: int | None,
        on_selected: Callable[[int], None],
    ):
        """Fill a dynamic menu with (id, label) entries.

        Called from the menu's aboutToShow, so the contents always mirror the
        database. Actions are parented to the menu: clear() deletes them.
        """
        menu.clear()
        if not items:
            placeholder = QAction(empty_text, menu)
            placeholder.setEnabled(False)
            menu.addAction(placeholder)
            return
        for item_id, label in items:
            if item_id is None:
                continue
            action = QAction(label, menu)
            action.setCheckable(True)
            action.setChecked(item_id == checked_id)
            action.triggered.connect(lambda checked=False, i=item_id: on_selected(i))
            menu.addAction(action)

    def _sync_view_menu(self):
        floating = self.soundboard_dock.isFloating()
        self._soundboard_view_action.setChecked(
            floating or not self.soundboard_dock.collapsed
        )
        # Collapse is a docked-only affordance; a floating board is a window.
        self._soundboard_view_action.setEnabled(not floating)

    def _toggle_soundboard_panel(self, checked: bool):
        self.soundboard_dock.set_collapsed(not checked)

    def import_files(self):
        """File > Import > Files…: open the Library tab and its file picker."""
        self.tab_widget.setCurrentWidget(self.library_widget)
        self.library_widget.add_files()

    def import_folder(self):
        """File > Import > Folder…: open the Library tab and its folder picker."""
        self.tab_widget.setCurrentWidget(self.library_widget)
        self.library_widget.add_folder()

    def show_scene(self, scene_id: int):
        """Bring the Scenes tab forward and open the given scene."""
        self.tab_widget.setCurrentWidget(self.scenes_widget)
        self.scenes_widget.select_scene(scene_id)

    def show_playlist(self, playlist_id: int):
        """Bring the Playlists tab forward and open the given playlist."""
        self.tab_widget.setCurrentWidget(self.playlists_widget)
        self.playlists_widget.select_playlist(playlist_id)

    def show_soundboard(self, board_id: int):
        """Expand (and raise, if floating) the soundboard panel on a board."""
        self.soundboard_dock.set_collapsed(False)
        if self.soundboard_dock.isFloating():
            self.soundboard_dock.raise_()
            self.soundboard_dock.activateWindow()
        self.soundboard_content.select_board(board_id)

    def stop_all_playback(self):
        """Stop scenes, playlists, and any soundboard one-shot (Stop All)."""
        self.scenes_widget.stop_all_playback()
        self.playlists_widget.stop_all_playback()
        self.soundboard_player.stop()

    def _show_about(self):
        QMessageBox.about(
            self,
            f"About {APP_DISPLAY_NAME}",
            f"<b>{APP_DISPLAY_NAME}</b><br>"
            f"Version {__version__}<br><br>"
            "Layered soundscapes, playlists, and soundboards "
            "for tabletop games.<br><br>"
            "<small>Feather icons © Cole Bemis, MIT license.<br>"
            "Audio playback via VLC (videolan.org).</small>",
        )

    def _show_settings(self):
        dialog = SettingsDialog(self)
        # Only restart on an actual change: a restart drops remote clients.
        if dialog.exec() and dialog.remote_config_changed():
            self._restart_remote_server()

    def _restart_remote_server(self):
        if self.remote_server is not None:
            self.remote_server.stop()
            self.remote_server = None
        self.remote_server = self._start_remote_server()

    def _show_shortcuts_help(self):
        QMessageBox.information(
            self,
            "Keyboard Shortcuts",
            "<table cellspacing='6'>"
            "<tr><td><b>Space</b></td><td>Play / pause</td></tr>"
            "<tr><td><b>→</b></td><td>Next track (playlist)</td></tr>"
            "<tr><td><b>⌘← / ⌘→</b></td>"
            "<td>Previous / next scene or playlist</td></tr>"
            "<tr><td><b>⌘1 / ⌘2 / ⌘3</b></td>"
            "<td>Library / Scenes / Playlists tab</td></tr>"
            "<tr><td><b>⌘O</b></td><td>Import audio files</td></tr>"
            "</table>",
        )

    def _send_feedback(self):
        """Help > Send Feedback…: open the beta feedback form in the browser."""
        QDesktopServices.openUrl(QUrl(FEEDBACK_FORM_URL))

    def _on_update_available(self, release):
        """A newer GitHub release exists: offer the download page, once."""
        settings = QSettings()
        if settings.value(self.SETTINGS_SKIP_UPDATE, "", type=str) == release.version:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Update Available")
        box.setText(
            f"{APP_DISPLAY_NAME} {release.version} is available "
            f"(you have {__version__})."
        )
        box.setInformativeText(
            "Before updating, back up your library "
            "(File → Back Up Database…) so you can roll back if needed. "
            f"Then quit {APP_DISPLAY_NAME} before installing the new version."
        )
        open_btn = box.addButton(
            "Open Download Page", QMessageBox.ButtonRole.AcceptRole
        )
        skip_btn = box.addButton(
            "Skip This Version", QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl(release.url))
        elif box.clickedButton() is skip_btn:
            settings.setValue(self.SETTINGS_SKIP_UPDATE, release.version)

    def _backup_database(self):
        """File > Back Up Database…: snapshot the live DB wherever the user picks."""
        default = str(
            Path.home() / f"soundmanager-backup-{date.today().isoformat()}.db"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Back Up Database", default, "SQLite Database (*.db)"
        )
        if not path:
            return
        try:
            self.db.backup_to(path)
        except (sqlite3.Error, OSError) as exc:
            QMessageBox.critical(
                self, "Backup Failed", f"Could not write the backup:\n{exc}"
            )
            return
        QMessageBox.information(
            self, "Backup Complete", f"Database backed up to:\n{path}"
        )

    def _warn_missing_audio(self):
        """Tell the user VLC is missing and where to get it (plan 010)."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("VLC Not Found")
        box.setText(
            f"{APP_DISPLAY_NAME} uses VLC for audio playback, and it doesn't "
            "appear to be installed.\n\n"
            "Everything except playback will still work. To enable audio, "
            "install VLC from videolan.org and relaunch this app."
        )
        download_btn = box.addButton(
            "Open VLC Download Page", QMessageBox.ButtonRole.ActionRole
        )
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() is download_btn:
            QDesktopServices.openUrl(QUrl("https://www.videolan.org/vlc/"))

    def _repair_library(self):
        """File > Repair Library…: relink entries whose files moved on disk."""
        from .library import RepairLibraryDialog

        dialog = RepairLibraryDialog(self.db, self.audio_engine, parent=self)
        dialog.exec()
        if dialog.relinked_count:
            self.library_widget.refresh()

    def _restore_database(self):
        """File > Restore Database…: validate, confirm, then restart to swap.

        The actual file swap happens in closeEvent, after playback has
        stopped and the database connection is closed — swapping under a
        live SQLite connection corrupts data.
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "Restore Database", str(Path.home()), "SQLite Database (*.db)"
        )
        if not path:
            return
        error = validate_backup(path)
        if error is not None:
            QMessageBox.critical(self, "Cannot Restore", error)
            return
        answer = QMessageBox.question(
            self,
            "Restore Database",
            "Replace your current library, scenes, playlists, and soundboards "
            "with this backup?\n\nYour current database will be kept beside "
            "it as a safety copy, and the app will restart.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Ok:
            self._pending_restore = path
            self.close()

    def _finish_pending_restore(self):
        """Swap in the restore file and relaunch. Runs at the end of
        closeEvent — the ONLY point where the database is guaranteed closed."""
        assert self._pending_restore is not None
        try:
            swap_database(Path(self.db.db_path), Path(self._pending_restore))
        except OSError:
            logger.exception("restore_swap_failed")
            return
        # Relaunch: in a py2app bundle sys.executable is the app launcher
        # (no args); in dev it's the venv python, which needs main.py back.
        args = [] if getattr(sys, "frozen", False) else sys.argv
        QProcess.startDetached(sys.executable, args, os.getcwd())

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

    def _start_remote_server(self) -> RemoteControlServer | None:
        """Start the remote-control WebSocket server (see docs/remote-protocol.md).

        Configured via QSettings group ``remote``: ``enabled`` (default True)
        and ``port`` (default 8765). Bind failure only logs a warning — remote
        control must never prevent the app from starting.
        """
        settings = QSettings()
        settings.beginGroup(SETTINGS_GROUP)
        enabled = settings.value(SETTINGS_ENABLED, defaultValue=True, type=bool)
        port = settings.value(SETTINGS_PORT, defaultValue=DEFAULT_PORT, type=int)
        settings.endGroup()
        if not enabled:
            return None
        server = RemoteControlServer(self.remote_facade, port=port, parent=self)
        server.start()
        return server

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
        # NB: with type=int, QSettings.value() returns 0 (not None) for a
        # missing key, so an explicit default is required — without it every
        # fresh install started muted.
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        value = settings.value(self.SETTINGS_MASTER_VOLUME, 100, type=int)
        settings.endGroup()
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

    def _save_window_state(self):
        """Persist window geometry + dock layout (soundboard height /
        floating geometry)."""
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_UI_GROUP)
        settings.setValue(self.SETTINGS_WINDOW_GEOMETRY, self.saveGeometry())
        settings.setValue(self.SETTINGS_WINDOW_STATE, self.saveState())
        settings.endGroup()

    def _restore_window_state(self):
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_UI_GROUP)
        geometry = settings.value(self.SETTINGS_WINDOW_GEOMETRY)
        state = settings.value(self.SETTINGS_WINDOW_STATE)
        settings.endGroup()
        # Qt-recommended order: geometry first, then dock state. Qt sanity-
        # checks restored geometry against the current screens, so a window
        # saved on a disconnected monitor comes back on a visible one.
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            self.restoreState(state)

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
            # Mutual exclusivity: stop any active playlist before activating
            # the scene. Unconditional because _current_playing_type can't be
            # trusted here — a PAUSED playlist has type None but still holds a
            # resumable player. The editor's stop path only emits when
            # something was actually active, so this is a silent no-op when idle.
            # The fade overlaps the scene's own fade-in: a crossfade, not a cut.
            self.playlists_widget.stop_all_playback(TRANSITION_FADE_MS)
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
            # Mutual exclusivity: stop any active scene before activating the
            # playlist. Unconditional for the same reason as the scene handler:
            # a paused scene has type None but must still be torn down.
            # The fade overlaps the playlist's fade-in: a crossfade, not a cut.
            self.scenes_widget.stop_all_playback(TRANSITION_FADE_MS)
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
            self.show_scene(self._current_scene_id)
        elif (
            self._current_playing_type == "playlist"
            and self._current_playlist_playing_id
        ):
            self.show_playlist(self._current_playlist_playing_id)

    def closeEvent(self, event):
        """Handle application close"""
        self._save_window_state()

        if self.remote_server is not None:
            self.remote_server.stop()

        # Stop all audio
        self.scenes_widget.stop_all_playback()
        self.playlists_widget.stop_all_playback()
        self.soundboard_player.clear()

        # Close database
        self.db.close()

        # Release audio engine
        self.audio_engine.release()

        # A confirmed File > Restore Database… swaps files and relaunches
        # here, now that the database connection is closed.
        if self._pending_restore is not None:
            self._finish_pending_restore()

        event.accept()
