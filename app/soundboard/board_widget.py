"""Soundboard content: sticky controls row above a scrolling button grid"""

from PyQt6.QtCore import (
    QByteArray,
    QEvent,
    QMimeData,
    QPoint,
    QSettings,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QDrag, QFontMetrics
from PyQt6.QtWidgets import (
    QApplication,
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

SOUNDBOARD_BUTTON_MIME = "application/x-soundmanager-soundboard-button"


class SoundboardButtonCell(QFrame):
    """One grid cell: the trigger button plus a grabber for drag-reorder.

    Dragging the grabber starts a QDrag carrying the button id (custom MIME,
    same pattern as PlaylistTrackItem); SoundboardGrid handles the drop. The
    cell's context menu carries the per-button VolumeSlider
    (commit-on-release contract) and the remove action.
    """

    triggered = pyqtSignal(object)  # SoundboardButton
    remove_requested = pyqtSignal(object)  # SoundboardButton
    volume_changed = pyqtSignal(object, float)  # live, 0-1
    volume_committed = pyqtSignal(object, float)  # persist, 0-1

    def __init__(self, button: SoundboardButton, icons: IconLibrary, parent=None):
        super().__init__(parent)
        self.button = button
        self._playing = False
        self._drag_start_pos: QPoint | None = None

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
        self.grabber.installEventFilter(self)
        layout.addWidget(self.grabber)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._apply_style()

    def eventFilter(self, obj, event):
        """Start a drag from the grabber (a QPushButton eats mouse events,
        so the drag gesture is detected here rather than in the button)."""
        if obj is self.grabber:
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                self._drag_start_pos = event.position().toPoint()
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._drag_start_pos = None
            elif (
                event.type() == QEvent.Type.MouseMove
                and (event.buttons() & Qt.MouseButton.LeftButton)
                and self._drag_start_pos is not None
                and (
                    event.position().toPoint() - self._drag_start_pos
                ).manhattanLength()
                >= QApplication.startDragDistance()
            ):
                self._start_drag()
                return True
        return super().eventFilter(obj, event)

    def _start_drag(self) -> None:
        self._drag_start_pos = None
        if self.button.id is None:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(SOUNDBOARD_BUTTON_MIME, QByteArray(str(self.button.id).encode()))
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(QPoint(self.width() // 2, self.height() // 2))
        drag.exec(Qt.DropAction.MoveAction)

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


class SoundboardGrid(QWidget):
    """Drop-accepting container for the wrapping grid of button cells.

    Reorder is insert-style: dropping on a cell shifts it (and everything
    after it) down-list. A dashed trailing drop cell is always present while
    the board has buttons, so "move to end" always has a target. The drop
    only computes and emits the new id order (``order_changed``); the owner
    persists it and rebuilds the grid.
    """

    order_changed = pyqtSignal(list)  # list[int]: button ids in new order

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.grid_layout = FlowLayout(self, margin=0, spacing=8)
        self._drop_zone: QFrame | None = None

    def populate(self, cells: list[SoundboardButtonCell]) -> None:
        clear_layout(self.grid_layout)
        self._drop_zone = None
        for cell in cells:
            self.grid_layout.addWidget(cell)
        if cells:
            self._drop_zone = self._build_drop_zone()
            self.grid_layout.addWidget(self._drop_zone)

    def _build_drop_zone(self) -> QFrame:
        zone = QFrame()
        zone.setFixedSize(174, 34)
        zone.setToolTip("Drop here to move a sound to the end")
        zone.setStyleSheet(
            f"""
            QFrame {{
                background-color: transparent;
                border: 1px dashed {Styles.BORDER};
                border-radius: 8px;
            }}
            """
        )
        return zone

    def cells_in_order(self) -> list[SoundboardButtonCell]:
        cells = []
        for i in range(self.grid_layout.count()):
            item = self.grid_layout.itemAt(i)
            widget = item.widget() if item else None
            if isinstance(widget, SoundboardButtonCell):
                cells.append(widget)
        return cells

    def button_ids_in_order(self) -> list[int]:
        return [c.button.id for c in self.cells_in_order() if c.button.id is not None]

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(SOUNDBOARD_BUTTON_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(SOUNDBOARD_BUTTON_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(SOUNDBOARD_BUTTON_MIME):
            return
        data = bytes(event.mimeData().data(SOUNDBOARD_BUTTON_MIME))
        try:
            button_id = int(data.decode())
        except ValueError:
            return
        new_order = self._reordered_ids(
            button_id, event.position().x(), event.position().y()
        )
        if new_order is None:
            return
        event.acceptProposedAction()
        self.order_changed.emit(new_order)

    def _reordered_ids(self, button_id: int, x: float, y: float) -> list[int] | None:
        """The id order after inserting button_id at (x, y); None if a no-op."""
        ids = self.button_ids_in_order()
        if button_id not in ids:
            return None
        insert_index = self._index_for_pos(x, y)
        current_index = ids.index(button_id)
        ids.remove(button_id)
        if insert_index > current_index:
            insert_index -= 1
        ids.insert(insert_index, button_id)
        if ids == self.button_ids_in_order():
            return None
        return ids

    def _index_for_pos(self, x: float, y: float) -> int:
        """Insert index for a point in the wrapped flow (reading order).

        Rows are walked in layout order: a point above a cell's row inserts
        before that cell (it sits in the wrap gap); within a row, a point
        left of a cell's horizontal midpoint inserts before it. Past all
        cells (including on the trailing drop zone) appends.
        """
        cells = self.cells_in_order()
        for index, cell in enumerate(cells):
            geo = cell.geometry()
            if y < geo.top():
                return index
            if y <= geo.bottom() and x < geo.x() + geo.width() / 2:
                return index
        return len(cells)


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
        self.grid = SoundboardGrid()
        self.grid.order_changed.connect(self._on_reorder)
        scroll.setWidget(self.grid)
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

    def select_board(self, board_id: int) -> None:
        """Select a board by id (the Soundboards menu entry point).

        Same-board selection is a deliberate no-op: switching boards stops the
        player, and re-selecting the open board must not cut a playing sound.
        """
        if board_id == self.current_board_id():
            return
        index = self.board_combo.findData(board_id)
        if index >= 0:
            self.board_combo.setCurrentIndex(index)
        else:
            # Not in the combo (created elsewhere, e.g. remote): full reload.
            self._reload_boards(select_id=board_id)

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
        # Board switch empties the player slot. stop(), not clear(): the
        # button_stopped signal must fire so remote clients' state stays
        # truthful (a silent clear would leave them showing a ghost sound).
        self.player.stop()
        board_id = self.current_board_id()
        if board_id is not None:
            settings = QSettings()
            settings.beginGroup(self.SETTINGS_GROUP)
            settings.setValue(self.SETTINGS_LAST_BOARD_ID, board_id)
            settings.endGroup()
        self.edit_btn.setEnabled(board_id is not None)
        self._load_buttons()

    def _load_buttons(self) -> None:
        self._cells_by_button_id = {}
        board_id = self.current_board_id()
        if board_id is None:
            self.grid.populate([])
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

        cells = []
        for button in buttons:
            cell = SoundboardButtonCell(button, self._icons)
            cell.triggered.connect(self._on_cell_triggered)
            cell.remove_requested.connect(self._on_remove_button)
            cell.volume_changed.connect(self._on_volume_changed)
            cell.volume_committed.connect(self._on_volume_committed)
            cells.append(cell)
            if button.id is not None:
                self._cells_by_button_id[button.id] = cell
        self.grid.populate(cells)

    def _on_reorder(self, button_ids: list) -> None:
        board_id = self.current_board_id()
        if board_id is None:
            return
        self.db.reorder_soundboard_buttons(board_id, button_ids)
        self._load_buttons()

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
