"""Soundboard content: sticky controls row above a scrolling button grid"""

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from ..audio import SoundboardPlayer
from ..database import DatabaseConnection, Soundboard, SoundboardButton
from ..shared.icons import IconLibrary
from ..shared.layouts import FlowLayout, clear_layout
from ..shared.styles import Styles
from ..shared.volume_slider import VolumeSlider
from .edit_dialog import SoundboardEditDialog


class SoundboardButtonCell(QFrame):
    """One grid cell: the trigger button plus a grabber for drag-reorder.

    The grabber is inert until Phase 5 wires the drag. The cell's context
    menu carries the per-button VolumeSlider (commit-on-release contract)
    and the remove action.
    """

    triggered = pyqtSignal(object)  # SoundboardButton
    remove_requested = pyqtSignal(object)  # SoundboardButton
    volume_changed = pyqtSignal(object, float)  # live, 0-1
    volume_committed = pyqtSignal(object, float)  # persist, 0-1

    def __init__(self, button: SoundboardButton, icons: IconLibrary, parent=None):
        super().__init__(parent)
        self.button = button
        self._playing = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        title = button.audio_file.display_title if button.audio_file else "?"
        self.trigger_btn = QPushButton()
        self.trigger_btn.setFixedSize(150, 34)
        # NoFocus: a focused button would swallow the Space play/pause key.
        self.trigger_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        metrics = QFontMetrics(self.trigger_btn.font())
        self.trigger_btn.setText(
            metrics.elidedText(title, Qt.TextElideMode.ElideRight, 126)
        )
        self.trigger_btn.setToolTip(title)
        self.trigger_btn.clicked.connect(lambda: self.triggered.emit(self.button))
        layout.addWidget(self.trigger_btn)

        self.grabber = QPushButton()
        self.grabber.setFixedSize(22, 34)
        self.grabber.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.grabber.setIcon(icons.icon("list"))
        self.grabber.setToolTip("Drag to reorder")
        self.grabber.setCursor(Qt.CursorShape.OpenHandCursor)
        self.grabber.setStyleSheet(Styles.compact_icon_button_style())
        layout.addWidget(self.grabber)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._apply_style()

    @property
    def playing(self) -> bool:
        return self._playing

    def set_playing(self, playing: bool) -> None:
        if playing != self._playing:
            self._playing = playing
            self._apply_style()

    def _apply_style(self) -> None:
        self.trigger_btn.setStyleSheet(Styles.soundboard_button_style(self._playing))

    def _show_context_menu(self, pos):
        menu = QMenu(self)

        slider = VolumeSlider(self.button.volume)
        slider.changed.connect(lambda v: self.volume_changed.emit(self.button, v))
        slider.committed.connect(lambda v: self.volume_committed.emit(self.button, v))
        wrapper = QWidget()
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(12, 6, 12, 6)
        wrapper_layout.addWidget(slider)
        slider_action = QWidgetAction(menu)
        slider_action.setDefaultWidget(wrapper)
        menu.addAction(slider_action)

        menu.addSeparator()
        remove_action = menu.addAction("Remove from board")
        remove_action.triggered.connect(lambda: self.remove_requested.emit(self.button))
        menu.exec(self.mapToGlobal(pos))


class SoundboardContent(QWidget):
    """The dock's content widget.

    A fixed controls row — board combo, add/edit buttons, Stop — above a
    QScrollArea holding the wrapping FlowLayout grid of button cells, so
    the controls stay visible while the grid scrolls. Combo selection is
    tracked and restored by board id, never by index (alphabetical ordering
    means a rename can move a board in the list).
    """

    SETTINGS_GROUP = "soundboard"
    SETTINGS_LAST_BOARD_ID = "last_board_id"

    def __init__(
        self,
        db: DatabaseConnection,
        audio_engine,
        player: SoundboardPlayer,
        parent=None,
    ):
        super().__init__(parent)
        self.db = db
        self.audio_engine = audio_engine
        self.player = player
        self._icons = IconLibrary()
        self._cells_by_button_id: dict[int, SoundboardButtonCell] = {}

        self._setup_ui()
        self.player.button_started.connect(self._on_button_started)
        self.player.button_stopped.connect(self._on_button_stopped)
        self._reload_boards(select_id=self._restore_last_board_id())

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(10)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.board_combo = QComboBox()
        self.board_combo.setMinimumWidth(220)
        self.board_combo.setStyleSheet(Styles.combobox_style())
        # NoFocus on all controls here: focused widgets would swallow the
        # Space/arrow transport keys (same rationale as the master slider).
        self.board_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.board_combo.currentIndexChanged.connect(
            lambda _index: self._on_board_selected()
        )
        controls.addWidget(self.board_combo)

        self.add_btn = self._icon_button("plus", "New soundboard")
        self.add_btn.clicked.connect(self._add_board)
        controls.addWidget(self.add_btn)

        self.edit_btn = self._icon_button("edit-2", "Edit soundboard")
        self.edit_btn.clicked.connect(self._edit_board)
        controls.addWidget(self.edit_btn)

        controls.addStretch()

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.stop_btn.setStyleSheet(Styles.secondary_button_style(compact=True))
        self.stop_btn.clicked.connect(self.player.stop)
        controls.addWidget(self.stop_btn)

        layout.addLayout(controls)

        self.empty_label = QLabel("")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(Styles.subtle_text_style(size=12))
        layout.addWidget(self.empty_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_container = QWidget()
        self.grid_layout = FlowLayout(self.grid_container, margin=0, spacing=8)
        scroll.setWidget(self.grid_container)
        layout.addWidget(scroll, 1)

    def _icon_button(self, icon_name: str, tooltip: str) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(28, 28)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setIcon(self._icons.icon(icon_name))
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(Styles.compact_icon_button_style())
        return btn

    # Board selection / loading

    def current_board_id(self) -> int | None:
        return self.board_combo.currentData()

    def _restore_last_board_id(self) -> int | None:
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        board_id = settings.value(self.SETTINGS_LAST_BOARD_ID, type=int)
        settings.endGroup()
        return board_id

    def _reload_boards(self, select_id: int | None = None) -> None:
        """Rebuild the combo from the DB, selecting select_id (by id)."""
        boards = self.db.get_all_soundboards()
        self.board_combo.blockSignals(True)
        self.board_combo.clear()
        for board in boards:
            self.board_combo.addItem(board.name, board.id)
        index = next((i for i, b in enumerate(boards) if b.id == select_id), 0)
        if boards:
            self.board_combo.setCurrentIndex(index)
        self.board_combo.blockSignals(False)
        self._on_board_selected()

    def _on_board_selected(self) -> None:
        # Board switch empties the player slot (silent; the grid rebuilds).
        self.player.clear()
        board_id = self.current_board_id()
        if board_id is not None:
            settings = QSettings()
            settings.beginGroup(self.SETTINGS_GROUP)
            settings.setValue(self.SETTINGS_LAST_BOARD_ID, board_id)
            settings.endGroup()
        self.edit_btn.setEnabled(board_id is not None)
        self._load_buttons()

    def _load_buttons(self) -> None:
        clear_layout(self.grid_layout)
        self._cells_by_button_id = {}
        board_id = self.current_board_id()
        if board_id is None:
            self.empty_label.setText("No soundboards yet — click + to create one")
            self.empty_label.show()
            return

        buttons = self.db.get_soundboard_buttons(board_id)
        if not buttons:
            self.empty_label.setText(
                "This board has no sounds — click the edit button to add some"
            )
            self.empty_label.show()
        else:
            self.empty_label.hide()

        for button in buttons:
            cell = SoundboardButtonCell(button, self._icons)
            cell.triggered.connect(self._on_cell_triggered)
            cell.remove_requested.connect(self._on_remove_button)
            cell.volume_changed.connect(self._on_volume_changed)
            cell.volume_committed.connect(self._on_volume_committed)
            self.grid_layout.addWidget(cell)
            if button.id is not None:
                self._cells_by_button_id[button.id] = cell

    # Playback wiring

    def _on_cell_triggered(self, button: SoundboardButton) -> None:
        if button.id is None or button.audio_file is None:
            return
        self.player.trigger(button.id, button.audio_file.file_path, button.volume)

    def _on_button_started(self, button_id: int) -> None:
        cell = self._cells_by_button_id.get(button_id)
        if cell is not None:
            cell.set_playing(True)

    def _on_button_stopped(self, button_id: int) -> None:
        cell = self._cells_by_button_id.get(button_id)
        if cell is not None:
            cell.set_playing(False)

    # Button actions

    def _on_remove_button(self, button: SoundboardButton) -> None:
        if button.id is None:
            return
        if self.player.current_button_id == button.id:
            self.player.stop()
        self.db.remove_soundboard_button(button.id)
        self._load_buttons()

    def _on_volume_changed(self, button: SoundboardButton, volume: float) -> None:
        if button.id is not None:
            self.player.set_current_volume(button.id, volume)

    def _on_volume_committed(self, button: SoundboardButton, volume: float) -> None:
        if button.id is not None:
            self.db.update_soundboard_button_volume(button.id, volume)
            button.volume = volume

    # Board management

    def _add_board(self) -> None:
        dialog = SoundboardEditDialog(self.db, self.audio_engine, parent=self.window())
        if dialog.exec():
            board_id = self.db.add_soundboard(Soundboard(name=dialog.get_name()))
            for file in dialog.get_selected_files():
                if file.id is not None:
                    self.db.add_button_to_soundboard(board_id, file.id)
            self._reload_boards(select_id=board_id)

    def _edit_board(self) -> None:
        board_id = self.current_board_id()
        if board_id is None:
            return
        board = self.db.get_soundboard(board_id)
        if board is None:
            return
        dialog = SoundboardEditDialog(
            self.db, self.audio_engine, soundboard=board, parent=self.window()
        )
        if dialog.exec():
            new_name = dialog.get_name()
            if new_name != board.name:
                board.name = new_name
                self.db.update_soundboard(board)
            for file in dialog.get_selected_files():
                if file.id is not None:
                    self.db.add_button_to_soundboard(board_id, file.id)
            # Re-select by id: a rename may have moved the board alphabetically.
            self._reload_boards(select_id=board_id)
