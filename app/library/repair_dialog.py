"""Repair Library dialog: relink unlinked entries to files found on disk.

Flow (plan 009): on open, list every library entry whose path no longer
exists and search Spotlight for same-named files automatically. Each row
shows its candidates with a confidence badge (hash match = exact), a
preview button, and a Relink button. "Search a Folder…" walks a chosen
root for the entries that are still unresolved (catches renamed files by
size + hash, and files on volumes Spotlight doesn't index).
"""

import os

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.shared.icons import IconLibrary
from app.shared.styles import Styles

from . import repair
from .repair import Candidate, Confidence, UnlinkedEntry


class RepairItem(QFrame):
    """One unlinked library entry with its candidate matches."""

    preview_requested = pyqtSignal(str, object)  # candidate path, self
    relink_requested = pyqtSignal(object, object, object)  # entry, candidate, self

    def __init__(self, entry: UnlinkedEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.relinked = False
        self._icons = IconLibrary()

        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            RepairItem {{
                background-color: {Styles.BACKGROUND_LIGHT};
                border: 1px solid {Styles.BORDER};
                border-radius: 4px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        title_label = QLabel(entry.audio_file.display_title)
        title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(title_label)

        old_path_label = QLabel(f"Missing: {entry.audio_file.file_path}")
        old_path_label.setStyleSheet(f"color: {Styles.TEXT_SUBTLE}; font-size: 11px;")
        old_path_label.setToolTip(entry.audio_file.file_path)
        old_path_label.setWordWrap(True)  # long paths must not widen the row
        layout.addWidget(old_path_label)

        self.candidate_row = QHBoxLayout()
        self.candidate_row.setSpacing(8)
        layout.addLayout(self.candidate_row)
        self.refresh_candidates()

    def _clear_candidate_row(self):
        while self.candidate_row.count():
            item = self.candidate_row.takeAt(0)
            if item is not None and (widget := item.widget()) is not None:
                # hide() first: deleteLater() keeps the widget painting until
                # the event loop runs, which overlaps it with its replacement.
                widget.hide()
                widget.deleteLater()

    def refresh_candidates(self):
        """(Re)build the candidate row from the entry's current candidates."""
        if self.relinked:
            return
        self._clear_candidate_row()

        if not self.entry.candidates:
            no_match = QLabel("No match found")
            no_match.setStyleSheet(
                f"color: {Styles.TEXT_MUTED}; font-style: italic; font-size: 12px;"
            )
            self.candidate_row.addWidget(no_match)
            self.candidate_row.addStretch()
            return

        self.candidate_combo = QComboBox()
        self.candidate_combo.setStyleSheet(Styles.combobox_style())
        # Long absolute paths must not dictate the row's width (they'd push
        # the badge and buttons out of view); tooltips carry the full path.
        self.candidate_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.candidate_combo.setMinimumContentsLength(24)
        for candidate in self.entry.candidates:
            self.candidate_combo.addItem(candidate.path, candidate)
            index = self.candidate_combo.count() - 1
            self.candidate_combo.setItemData(
                index, candidate.path, Qt.ItemDataRole.ToolTipRole
            )
        self.candidate_combo.currentIndexChanged.connect(self._update_badge)
        self.candidate_row.addWidget(self.candidate_combo, 1)

        self.confidence_badge = QLabel()
        self.candidate_row.addWidget(self.confidence_badge)
        self._update_badge()

        self.preview_btn = QPushButton()
        self.preview_btn.setFixedSize(22, 22)
        self.preview_btn.setIcon(self._icons.icon("play-solid"))
        self.preview_btn.setIconSize(QSize(12, 12))
        self.preview_btn.setStyleSheet(Styles.small_play_button_style())
        self.preview_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.preview_btn.setToolTip("Preview this file")
        self.preview_btn.clicked.connect(
            lambda: self.preview_requested.emit(self.selected_candidate().path, self)
        )
        self.candidate_row.addWidget(self.preview_btn)

        self.relink_btn = QPushButton("Relink")
        self.relink_btn.setStyleSheet(Styles.secondary_button_style(compact=True))
        self.relink_btn.clicked.connect(
            lambda: self.relink_requested.emit(
                self.entry, self.selected_candidate(), self
            )
        )
        self.candidate_row.addWidget(self.relink_btn)

    def selected_candidate(self) -> Candidate:
        candidate = self.candidate_combo.currentData()
        assert isinstance(candidate, Candidate)
        return candidate

    def _update_badge(self):
        confidence = self.selected_candidate().confidence
        color = Styles.SUCCESS if confidence is Confidence.CERTAIN else Styles.WARNING
        self.confidence_badge.setText(confidence.label)
        self.confidence_badge.setStyleSheet(
            f"color: {color}; border: 1px solid {color}; border-radius: 3px;"
            " padding: 1px 6px; font-size: 11px;"
        )

    def mark_relinked(self, path: str):
        """Replace the candidate row with a confirmation line."""
        self.relinked = True
        self._clear_candidate_row()
        done = QLabel(f"✓ Relinked to {path}")
        done.setStyleSheet(f"color: {Styles.SUCCESS}; font-size: 12px;")
        done.setToolTip(path)
        done.setWordWrap(True)
        self.candidate_row.addWidget(done)

    def set_preview_playing(self, playing: bool):
        if self.relinked or not self.entry.candidates:
            return
        if playing:
            self.preview_btn.setIcon(self._icons.icon("pause-solid"))
            self.preview_btn.setStyleSheet(Styles.small_stop_button_style())
        else:
            self.preview_btn.setIcon(self._icons.icon("play-solid"))
            self.preview_btn.setStyleSheet(Styles.small_play_button_style())
        self.preview_btn.setIconSize(QSize(12, 12))


class RepairLibraryDialog(QDialog):
    """Find library entries whose files moved and relink them."""

    def __init__(self, db, audio_engine, parent=None):
        super().__init__(parent)
        self.db = db
        self.audio_engine = audio_engine
        self.relinked_count = 0
        self._preview_player = None
        self._preview_item: RepairItem | None = None
        self._scanned_spotlight = False

        self.setWindowTitle("Repair Library")
        self.setMinimumSize(720, 420)

        layout = QVBoxLayout(self)

        self.header_label = QLabel()
        self.header_label.setWordWrap(True)
        layout.addWidget(self.header_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self.items_layout = QVBoxLayout(container)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(6)
        self.items_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        button_row = QHBoxLayout()
        self.search_folder_btn = QPushButton("Search a Folder…")
        self.search_folder_btn.setStyleSheet(Styles.secondary_button_style())
        self.search_folder_btn.clicked.connect(self._search_folder)
        button_row.addWidget(self.search_folder_btn)
        button_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        self.entries = repair.find_unlinked(self.db)
        self.items: list[RepairItem] = []
        for entry in self.entries:
            item = RepairItem(entry)
            item.preview_requested.connect(self._on_preview_requested)
            item.relink_requested.connect(self._on_relink_requested)
            self.items.append(item)
            self.items_layout.insertWidget(self.items_layout.count() - 1, item)
        self._update_header()

        if not self.entries:
            self.search_folder_btn.setEnabled(False)

    def showEvent(self, event):
        """Run the automatic Spotlight scan once, after the dialog appears."""
        super().showEvent(event)
        if self._scanned_spotlight or not self.entries:
            return
        self._scanned_spotlight = True
        self._scan_spotlight()

    def _scan_spotlight(self):
        progress = self._make_progress("Searching Spotlight for moved files…")
        try:
            repair.scan_spotlight(
                self.entries,
                self.db.get_all_audio_file_paths(),
                progress=lambda done, total: self._tick(progress, done, total),
            )
        finally:
            progress.close()
        self._refresh_items()

    def _search_folder(self):
        root = QFileDialog.getExistingDirectory(self, "Search Folder")
        if not root:
            return
        progress = self._make_progress(f"Scanning {root}…")
        try:
            repair.scan_folder(
                root,
                self._pending_entries(),
                self.db.get_all_audio_file_paths(),
                progress=lambda done, total: self._tick(progress, done, total),
                walk_tick=lambda seen: self._walk_tick(progress, seen),
            )
        finally:
            progress.close()
        self._refresh_items()

    def _pending_entries(self) -> list[UnlinkedEntry]:
        return [item.entry for item in self.items if not item.relinked]

    def _make_progress(self, label: str) -> QProgressDialog:
        progress = QProgressDialog(label, "Cancel", 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(400)
        return progress

    def _tick(self, progress: QProgressDialog, done: int, total: int) -> bool:
        progress.setMaximum(total)
        progress.setValue(done)
        QApplication.processEvents()
        return not progress.wasCanceled()

    def _walk_tick(self, progress: QProgressDialog, seen: int) -> bool:
        progress.setLabelText(f"Scanning… ({seen} files seen)")
        QApplication.processEvents()
        return not progress.wasCanceled()

    def _refresh_items(self):
        for item in self.items:
            item.refresh_candidates()
        self._update_header()

    def _update_header(self):
        pending = len(self._pending_entries())
        if not self.entries:
            text = "All library files are linked. Nothing to repair."
        elif pending == 0:
            text = "All unlinked files have been relinked."
        else:
            with_candidates = sum(
                1 for item in self.items if not item.relinked and item.entry.candidates
            )
            noun = "file points" if pending == 1 else "files point"
            text = (
                f"{pending} library {noun} to paths that no longer exist."
                f" Matches found for {with_candidates}."
                " Exact matches are confirmed by content fingerprint;"
                " preview possible matches before relinking."
            )
        self.header_label.setText(text)

    def _on_relink_requested(
        self, entry: UnlinkedEntry, candidate: Candidate, item: RepairItem
    ):
        self._stop_preview()
        repair.relink(self.db, entry.audio_file, candidate)
        self.relinked_count += 1
        item.mark_relinked(candidate.path)
        self._update_header()

    def _on_preview_requested(self, path: str, item: RepairItem):
        from ..audio import TrackPlayer

        was_playing_this = (
            self._preview_player is not None and self._preview_item is item
        )
        self._stop_preview(fade=True)
        if was_playing_this:
            return
        if os.path.exists(path):
            self._preview_player = TrackPlayer(path, self.audio_engine)
            self._preview_player.end_reached.connect(self._on_preview_ended)
            self._preview_player.fade_in(300)
            self._preview_item = item
            item.set_preview_playing(True)

    def _on_preview_ended(self):
        if self._preview_item:
            self._preview_item.set_preview_playing(False)
        if self._preview_player:
            self._preview_player.release()
        self._preview_player = None
        self._preview_item = None

    def _stop_preview(self, fade: bool = False):
        if self._preview_player:
            if fade:
                self._preview_player.fade_out(300)
            else:
                self._preview_player.stop()
            self._preview_player.release()
            self._preview_player = None
        if self._preview_item:
            self._preview_item.set_preview_playing(False)
            self._preview_item = None

    def reject(self):
        self._stop_preview()
        super().reject()

    def accept(self):
        self._stop_preview()
        super().accept()
