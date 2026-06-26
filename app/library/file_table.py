"""Sortable file list table for library"""

import os

from PyQt6.QtCore import QByteArray, QEvent, QSettings, QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from app.shared.logging import get_logger

from ..audio import AudioEngine, TrackPlayer
from ..database import AudioFile, DatabaseConnection
from ..shared.icons import IconLibrary
from ..shared.styles import Styles
from .tag_manager import TagAssigner

_log = get_logger(__name__)


class FileTableWidget(QTableWidget):
    """Sortable table displaying audio files"""

    file_selected = pyqtSignal(AudioFile)
    file_double_clicked = pyqtSignal(AudioFile)
    files_deleted = pyqtSignal(list)  # List of deleted file IDs
    tags_bulk_assigned = pyqtSignal()  # Emitted after bulk tag assignment
    file_metadata_changed = pyqtSignal()  # Emitted after inline title/artist edit
    sort_requested = pyqtSignal(int, Qt.SortOrder)  # column index, sort order
    SETTINGS_GROUP = "library/file_table"
    SETTINGS_HEADER_STATE = "header_state"
    SETTINGS_COLUMN_VISIBILITY = "column_visibility"
    SETTINGS_COLUMN_COUNT = "column_count"

    COLUMNS = ["", "Title", "Artist", "Duration", "Tags", "Added", "Filename", "Path"]
    COL_PLAY = 0
    COL_TITLE = 1
    COL_ARTIST = 2
    COL_DURATION = 3
    COL_TAGS = 4
    COL_ADDED = 5
    COL_FILENAME = 6
    COL_PATH = 7

    # Columns the user can toggle on/off (Play and Title are always visible)
    TOGGLEABLE_COLUMNS = {
        COL_ARTIST: "Artist",
        COL_DURATION: "Duration",
        COL_TAGS: "Tags",
        COL_ADDED: "Added",
        COL_FILENAME: "Filename",
        COL_PATH: "Path",
    }
    DEFAULT_VISIBLE = {COL_ARTIST, COL_DURATION, COL_TAGS, COL_ADDED}

    # Columns that cannot be sorted (no meaningful sort key)
    UNSORTABLE_COLUMNS = {COL_PLAY, COL_TAGS}

    def __init__(self, db: DatabaseConnection, audio_engine: AudioEngine, parent=None):
        super().__init__(parent)
        self.db = db
        self.audio_engine = audio_engine
        self._files: list[AudioFile] = []
        self._current_player: TrackPlayer | None = None
        self._playing_row: int = -1
        self._playing_file_id: int | None = None
        self._icons = IconLibrary()
        self._visible_columns: set[int] = set(self.DEFAULT_VISIBLE)
        self._sort_column: int = -1
        self._sort_order: Qt.SortOrder = Qt.SortOrder.AscendingOrder

        self._setup_table()
        self._setup_column_button()

    def _setup_table(self):
        """Configure table settings"""
        self.setColumnCount(len(self.COLUMNS))
        self.setHorizontalHeaderLabels(self.COLUMNS)

        # Column widths
        header = self.horizontalHeader()
        header.setSectionResizeMode(self.COL_PLAY, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(self.COL_PLAY, 50)
        header.setSectionResizeMode(self.COL_TITLE, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(self.COL_TITLE, 260)
        header.setSectionResizeMode(self.COL_ARTIST, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(self.COL_ARTIST, 220)
        header.setSectionResizeMode(
            self.COL_DURATION, QHeaderView.ResizeMode.Interactive
        )
        header.resizeSection(self.COL_DURATION, 110)
        header.setSectionResizeMode(self.COL_TAGS, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(self.COL_TAGS, 240)
        header.setSectionResizeMode(self.COL_ADDED, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(self.COL_ADDED, 160)
        header.setSectionResizeMode(
            self.COL_FILENAME, QHeaderView.ResizeMode.Interactive
        )
        header.resizeSection(self.COL_FILENAME, 200)
        header.setSectionResizeMode(self.COL_PATH, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(self.COL_PATH, 300)
        header.setStretchLastSection(True)

        # Enable drag reorder for columns
        header.setSectionsMovable(True)
        header.sectionMoved.connect(self._on_section_moved)

        self._restore_header_state()
        self._restore_column_visibility()
        header.sectionResized.connect(self._save_header_state)

        # Selection behavior
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.verticalHeader().setDefaultSectionSize(44)
        self.verticalHeader().setVisible(False)

        # Sorting — disabled at the table level; sorting is handled globally
        # via sort_requested signal so pagination works across the full dataset
        self.setSortingEnabled(False)
        self.horizontalHeader().setSortIndicatorShown(True)
        self.horizontalHeader().setSectionsClickable(True)
        self.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

        # Context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Double-click
        self.cellDoubleClicked.connect(self._on_double_click)

        # Inline editing
        self.cellChanged.connect(self._on_cell_changed)

        # Selection change
        self.itemSelectionChanged.connect(self._on_selection_changed)

        # Enable drag for adding to scenes
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)

    def set_files(self, files: list[AudioFile]):
        """Set the files to display"""
        self._files = files
        self._refresh_table()

    def _refresh_table(self):
        """Refresh table contents"""
        self.blockSignals(True)
        self.setRowCount(len(self._files))

        for row, audio_file in enumerate(self._files):
            self._populate_row(row, audio_file)

        self.blockSignals(False)
        self._apply_playback_state()

    def _populate_row(self, row: int, audio_file: AudioFile):
        """Populate a single row"""
        # Play button
        play_widget = QWidget()
        play_layout = QHBoxLayout(play_widget)
        play_layout.setContentsMargins(6, 0, 6, 0)
        play_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        play_btn = QPushButton()
        play_btn.setFixedSize(16, 16)
        play_btn.setIcon(self._icons.icon("play-solid"))
        play_btn.setIconSize(QSize(12, 12))
        play_btn.setStyleSheet(Styles.small_play_button_style())
        play_btn.setProperty("file_id", audio_file.id)
        play_btn.clicked.connect(self._toggle_play_for_button)
        play_layout.addWidget(play_btn)

        self.setCellWidget(row, self.COL_PLAY, play_widget)

        # Title (editable — show raw title, not display_title which falls back to filename)
        title_text = audio_file.title or ""
        title_item = QTableWidgetItem(title_text)
        title_item.setData(Qt.ItemDataRole.UserRole, audio_file.id)
        title_item.setToolTip(audio_file.display_title)
        self.setItem(row, self.COL_TITLE, title_item)

        # Artist
        artist_text = audio_file.artist or ""
        artist_item = QTableWidgetItem(artist_text)
        artist_item.setToolTip(artist_text)
        self.setItem(row, self.COL_ARTIST, artist_item)

        # Duration (read-only)
        duration_item = QTableWidgetItem(audio_file.duration_formatted)
        duration_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        duration_item.setFlags(duration_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, self.COL_DURATION, duration_item)

        # Tags
        tag_widget = TagAssigner(self.db, audio_file.id)
        tag_widget.tags_changed.connect(self.tags_bulk_assigned.emit)
        self.setCellWidget(row, self.COL_TAGS, tag_widget)

        # Added date (read-only)
        added_text = str(audio_file.created_at or "")
        added_item = QTableWidgetItem(added_text)
        added_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        added_item.setToolTip(added_text)
        added_item.setFlags(added_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, self.COL_ADDED, added_item)

        # Filename (read-only)
        filename_text = os.path.basename(audio_file.file_path)
        filename_item = QTableWidgetItem(filename_text)
        filename_item.setToolTip(filename_text)
        filename_item.setFlags(filename_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, self.COL_FILENAME, filename_item)

        # Path (read-only)
        path_item = QTableWidgetItem(audio_file.file_path)
        path_item.setToolTip(audio_file.file_path)
        path_item.setFlags(path_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.setItem(row, self.COL_PATH, path_item)

    def _toggle_play_for_button(self):
        """Toggle play/stop based on the clicked play button"""
        btn = self.sender()
        if not isinstance(btn, QPushButton):
            return
        file_id = btn.property("file_id")
        if not file_id:
            return
        self._toggle_play_by_file_id(int(file_id))

    def _toggle_play_by_file_id(self, file_id: int):
        """Toggle play/stop for a file ID"""
        # Stop current playback
        if self._current_player:
            self._current_player.fade_out(500)
            self._clear_playing_button()
            self._current_player.release()
            self._current_player = None

            if file_id == self._playing_file_id:
                self._playing_row = -1
                self._playing_file_id = None
                return

        # Start new playback
        audio_file = self._get_file_by_id(file_id)
        if audio_file and not os.path.exists(audio_file.file_path):
            _log.warning(
                "audio_file_missing",
                audio_file_id=file_id,
                file_path=audio_file.file_path,
            )
            return
        if audio_file:
            self._current_player = TrackPlayer(audio_file.file_path, self.audio_engine)
            self._current_player.end_reached.connect(
                lambda: self._on_playback_ended(file_id)
            )
            self._current_player.fade_in(500)
            self._playing_file_id = file_id
            self._playing_row = self._find_row_for_file_id(file_id)
            if self._playing_row >= 0:
                self._update_play_button(self._playing_row, True)

    def _update_play_button(self, row: int, playing: bool):
        """Update play button appearance"""
        if row < 0 or row >= self.rowCount():
            return

        widget = self.cellWidget(row, self.COL_PLAY)
        if widget:
            btn = widget.findChild(QPushButton)
            if btn:
                if playing:
                    btn.setText("")
                    btn.setIcon(self._icons.icon("pause-solid"))
                    btn.setIconSize(QSize(12, 12))
                    btn.setStyleSheet(Styles.small_stop_button_style())
                else:
                    btn.setText("")
                    btn.setIcon(self._icons.icon("play-solid"))
                    btn.setIconSize(QSize(12, 12))
                    btn.setStyleSheet(Styles.small_play_button_style())

    def _on_playback_ended(self, file_id: int):
        """Handle playback ended"""
        row = self._find_row_for_file_id(file_id)
        if row >= 0:
            self._update_play_button(row, False)
        if self._current_player:
            self._current_player.release()
            self._current_player = None
        self._playing_row = -1
        self._playing_file_id = None

    def _get_file_at_row(self, row: int) -> AudioFile | None:
        """Get audio file for a row"""
        item = self.item(row, self.COL_TITLE)
        if item:
            file_id = item.data(Qt.ItemDataRole.UserRole)
            for f in self._files:
                if f.id == file_id:
                    return f
        return None

    def _get_file_by_id(self, file_id: int) -> AudioFile | None:
        """Get audio file for a file ID"""
        for audio_file in self._files:
            if audio_file.id == file_id:
                return audio_file
        return None

    def _find_row_for_file_id(self, file_id: int) -> int:
        """Find the current row for a file ID"""
        for row in range(self.rowCount()):
            item = self.item(row, self.COL_TITLE)
            if item and item.data(Qt.ItemDataRole.UserRole) == file_id:
                return row
        return -1

    def _on_cell_changed(self, row: int, col: int):
        """Persist inline edits for Title and Artist columns"""
        if col not in (self.COL_TITLE, self.COL_ARTIST):
            return
        audio_file = self._get_file_at_row(row)
        if not audio_file:
            return
        item = self.item(row, col)
        if not item:
            return
        new_value = item.text().strip() or None
        if col == self.COL_TITLE:
            if new_value == audio_file.title:
                return
            audio_file.title = new_value
        else:
            if new_value == audio_file.artist:
                return
            audio_file.artist = new_value
        self.db.update_audio_file(audio_file)
        self.file_metadata_changed.emit()

    def _on_double_click(self, row: int, col: int):
        """Handle double-click on a row"""
        audio_file = self._get_file_at_row(row)
        if audio_file:
            self.file_double_clicked.emit(audio_file)

    def _on_selection_changed(self):
        """Handle selection change"""
        rows = self.selectionModel().selectedRows()
        if rows:
            audio_file = self._get_file_at_row(rows[0].row())
            if audio_file:
                self.file_selected.emit(audio_file)

    def _show_context_menu(self, pos):
        """Show context menu"""
        rows = self.selectionModel().selectedRows()
        if not rows:
            return

        menu = QMenu(self)

        if len(rows) == 1:
            play_action = menu.addAction("Play")
            audio_file = self._get_file_at_row(rows[0].row())
            if audio_file:
                play_action.triggered.connect(
                    lambda checked=False, fid=audio_file.id: (
                        self._toggle_play_by_file_id(fid)
                    )
                )

        tag_action = menu.addAction(f"Info ({len(rows)})")
        tag_action.triggered.connect(self._open_get_info)

        delete_action = menu.addAction(f"Remove ({len(rows)} files)")
        delete_action.triggered.connect(self._delete_selected)

        menu.exec(self.mapToGlobal(pos))

    def _delete_selected(self):
        """Delete selected files from library"""
        rows = self.selectionModel().selectedRows()
        file_ids = []

        for row_index in sorted([r.row() for r in rows], reverse=True):
            audio_file = self._get_file_at_row(row_index)
            if audio_file:
                file_ids.append(audio_file.id)
                self.db.delete_audio_file(audio_file.id)

        self.files_deleted.emit(file_ids)

    def _open_get_info(self):
        """Open Get Info dialog for viewing/editing metadata of selected files"""
        from .tag_selection_dialog import GetInfoDialog

        rows = self.selectionModel().selectedRows()
        audio_files = []
        for row in rows:
            audio_file = self._get_file_at_row(row.row())
            if audio_file:
                audio_files.append(audio_file)

        if not audio_files:
            return

        dialog = GetInfoDialog(self.db, audio_files, parent=self)
        if not dialog.exec():
            return

        file_ids = [f.id for f in audio_files]
        changed = False

        # Apply artist changes
        artist = dialog.get_artist_value()
        if artist is not None or dialog.get_artist_should_clear():
            self.db.bulk_update_artist(file_ids, artist)
            changed = True

        # Apply tag additions
        tags_to_add = dialog.get_tags_to_add()
        if tags_to_add:
            self.db.bulk_add_tags_to_audio_files(file_ids, tags_to_add)
            changed = True

        # Apply tag removals
        tags_to_remove = dialog.get_tags_to_remove()
        if tags_to_remove:
            self.db.bulk_remove_tags_from_audio_files(file_ids, tags_to_remove)
            changed = True

        if changed:
            self.tags_bulk_assigned.emit()

    def _refresh_tag_widgets(self):
        """Refresh TagAssigner widgets for all visible rows"""
        for row in range(self.rowCount()):
            tag_widget = self.cellWidget(row, self.COL_TAGS)
            if isinstance(tag_widget, TagAssigner):
                tag_widget.refresh_tags()

    def get_selected_files(self) -> list[AudioFile]:
        """Get currently selected audio files"""
        rows = self.selectionModel().selectedRows()
        files = []
        for row in rows:
            audio_file = self._get_file_at_row(row.row())
            if audio_file:
                files.append(audio_file)
        return files

    def stop_playback(self):
        """Stop any current playback"""
        if self._current_player:
            self._current_player.stop()
            self._current_player.release()
            self._current_player = None
            self._clear_playing_button()
            self._playing_row = -1
            self._playing_file_id = None

    def _clear_playing_button(self):
        """Clear the currently highlighted play button"""
        if self._playing_file_id is None:
            return
        row = self._find_row_for_file_id(self._playing_file_id)
        if row >= 0:
            self._update_play_button(row, False)

    def _apply_playback_state(self):
        """Re-apply playback state after refresh/sort"""
        if self._playing_file_id is None:
            return
        self._playing_row = self._find_row_for_file_id(self._playing_file_id)
        if self._playing_row >= 0:
            self._update_play_button(self._playing_row, True)

    def _on_header_clicked(self, logical_index: int):
        """Handle header click for sorting — toggle sort indicator and emit signal"""
        if logical_index in self.UNSORTABLE_COLUMNS:
            return

        if logical_index == self._sort_column:
            # Toggle direction
            self._sort_order = (
                Qt.SortOrder.DescendingOrder
                if self._sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self._sort_column = logical_index
            self._sort_order = Qt.SortOrder.AscendingOrder

        self.horizontalHeader().setSortIndicator(self._sort_column, self._sort_order)
        self.sort_requested.emit(self._sort_column, self._sort_order)

    # --- Column customization ---

    def _setup_column_button(self):
        """Create column customization button overlaid on the header"""
        header = self.horizontalHeader()
        self._column_btn = QPushButton(header)
        self._column_btn.setFixedSize(24, 24)
        self._column_btn.setIcon(self._icons.icon("list"))
        self._column_btn.setIconSize(QSize(14, 14))
        self._column_btn.setToolTip("Customize columns")
        self._column_btn.setStyleSheet(self._column_button_style())
        self._column_btn.clicked.connect(self._show_column_menu)
        header.installEventFilter(self)
        self._reposition_column_button()

    def eventFilter(self, obj, event):
        if obj == self.horizontalHeader() and event.type() == QEvent.Type.Resize:
            self._reposition_column_button()
        return super().eventFilter(obj, event)

    def _reposition_column_button(self):
        header = self.horizontalHeader()
        btn = self._column_btn
        x = header.width() - btn.width() - 4
        y = (header.height() - btn.height()) // 2
        btn.move(x, y)

    def _show_column_menu(self):
        menu = QMenu(self)
        for col_idx in sorted(self.TOGGLEABLE_COLUMNS):
            col_name = self.TOGGLEABLE_COLUMNS[col_idx]
            action = menu.addAction(col_name)
            action.setCheckable(True)
            action.setChecked(col_idx in self._visible_columns)
            action.triggered.connect(lambda checked, c=col_idx: self._toggle_column(c))
        menu.exec(self._column_btn.mapToGlobal(self._column_btn.rect().bottomRight()))

    def _toggle_column(self, col_index: int):
        if col_index in self._visible_columns:
            self._visible_columns.discard(col_index)
        else:
            self._visible_columns.add(col_index)
        self._apply_column_visibility()
        self._save_column_visibility()

    def _apply_column_visibility(self):
        for col_idx in self.TOGGLEABLE_COLUMNS:
            self.setColumnHidden(col_idx, col_idx not in self._visible_columns)

    def _on_section_moved(self, logical_index: int, old_visual: int, new_visual: int):
        """Enforce Play (visual 0) and Title (visual 1) stay locked"""
        header = self.horizontalHeader()
        play_visual = header.visualIndex(self.COL_PLAY)
        title_visual = header.visualIndex(self.COL_TITLE)

        if play_visual != 0 or title_visual != 1:
            header.blockSignals(True)
            header.moveSection(new_visual, old_visual)
            header.blockSignals(False)
        else:
            self._save_header_state()

    # --- Settings persistence ---

    def _restore_header_state(self):
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        saved_count = settings.value(self.SETTINGS_COLUMN_COUNT, type=int)
        state = settings.value(self.SETTINGS_HEADER_STATE)
        settings.endGroup()

        if not state:
            return
        # Only restore if column count was saved and matches current layout
        if not saved_count or saved_count != len(self.COLUMNS):
            return

        header = self.horizontalHeader()
        header.blockSignals(True)
        if isinstance(state, QByteArray):
            header.restoreState(state)
        elif isinstance(state, bytes):
            header.restoreState(QByteArray(state))
        header.blockSignals(False)

    def _save_header_state(self):
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        settings.setValue(
            self.SETTINGS_HEADER_STATE, self.horizontalHeader().saveState()
        )
        settings.setValue(self.SETTINGS_COLUMN_COUNT, len(self.COLUMNS))
        settings.endGroup()

    def _restore_column_visibility(self):
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        saved = settings.value(self.SETTINGS_COLUMN_VISIBILITY)
        settings.endGroup()

        if saved is not None:
            try:
                self._visible_columns = {int(c) for c in saved}
            except (TypeError, ValueError):
                self._visible_columns = set(self.DEFAULT_VISIBLE)
        self._apply_column_visibility()

    def _save_column_visibility(self):
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        settings.setValue(self.SETTINGS_COLUMN_VISIBILITY, list(self._visible_columns))
        settings.endGroup()

    @staticmethod
    def _column_button_style() -> str:
        return f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: {Styles.BACKGROUND_HOVER};
            }}
        """
