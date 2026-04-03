"""Main library view widget"""

import os
from typing import List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, Qt, QMimeData
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from ..database import DatabaseConnection, AudioFile
from ..audio import AudioEngine
from .file_table import FileTableWidget
from .tag_manager import TagManager
from .search_bar import SearchBar
from .pagination_bar import PaginationBar
from .metadata import MetadataExtractor
from ..shared.dialogs import FilePickerDialog, DuplicateFilesDialog
from ..shared.styles import Styles


class LibraryWidget(QWidget):
    """Main library view for managing audio files"""

    library_updated = pyqtSignal()  # Emitted when files are added/removed

    def __init__(self, db: DatabaseConnection, audio_engine: AudioEngine, parent=None):
        super().__init__(parent)
        self.db = db
        self.audio_engine = audio_engine

        self.setAcceptDrops(True)
        self._setup_ui()
        self._load_files()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(16, 16, 16, 16)

        # Tag filter section
        self.tag_manager = TagManager(self.db, header_text="Filter by tags")
        self.tag_manager.tag_filter_changed.connect(self._on_tag_filter)
        self.tag_manager.tags_modified.connect(self._on_tags_modified)
        self.tag_manager.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.tag_manager)

        # Search and add button
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        self.search_bar = SearchBar(placeholder="Search by title or artist...")
        self.search_bar.search_changed.connect(self._on_search)
        top_bar.addWidget(self.search_bar, 1)

        add_btn = QPushButton("Add Files")
        add_btn.clicked.connect(self._add_files)
        top_bar.addWidget(add_btn)

        layout.addLayout(top_bar)

        # Pagination bar
        self.pagination_bar = PaginationBar()
        self.pagination_bar.page_changed.connect(self._apply_page)
        layout.addWidget(self.pagination_bar)

        # File table
        self.file_table = FileTableWidget(self.db, self.audio_engine)
        self.file_table.files_deleted.connect(self._on_files_deleted)
        self.file_table.tags_bulk_assigned.connect(self._on_tags_modified)
        layout.addWidget(self.file_table, 1)

        # Drop hint
        self.drop_hint = QLabel("Drop audio files here to add to library")
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_hint.setStyleSheet(Styles.empty_state_style())
        self.drop_hint.hide()
        layout.addWidget(self.drop_hint)

    def _load_files(self):
        """Load files from database"""
        files = self.db.get_all_audio_files()
        self._display_files(files)

    def _display_files(self, files: list[AudioFile]):
        """Display files in the table"""
        self.pagination_bar.set_files(files)

        # Show/hide drop hint based on whether we have files
        if not files and not self.search_bar.get_text():
            self.drop_hint.show()
            self.file_table.hide()
        else:
            self.drop_hint.hide()
            self.file_table.show()

    def _apply_page(self):
        """Apply current pagination page to file table"""
        page_files = self.pagination_bar.get_current_page_files()
        self.file_table.set_files(page_files)

    def _on_search(self, query: str):
        """Handle search query change"""
        tag_ids = self.tag_manager.get_selected_tag_ids()
        files = self.db.search_audio_files(query, tag_ids if tag_ids else None)
        self._display_files(files)

    def _on_tag_filter(self, tag_ids: list[int]):
        """Handle tag filter change"""
        query = self.search_bar.get_text()
        files = self.db.search_audio_files(query, tag_ids if tag_ids else None)
        self._display_files(files)

    def _on_tags_modified(self):
        """Handle tag creation/deletion"""
        self._load_files()

    def _on_files_deleted(self, file_ids: list[int]):
        """Handle files deleted from table"""
        self._load_files()
        self.library_updated.emit()

    def _add_files(self):
        """Open file picker to add files"""
        dialog = FilePickerDialog(self, "Select Audio Files")

        if dialog.exec():
            file_paths = dialog.selectedFiles()
            self._import_files(file_paths)

    def _import_files(self, file_paths: list[str]):
        """Import files into the library"""
        added_count = 0
        skipped_count = 0
        duplicate_paths: list[str] = []
        seen_duplicates: set[str] = set()

        for file_path in file_paths:
            if not MetadataExtractor.is_supported_format(file_path):
                skipped_count += 1
                continue

            # Check if file already exists in library
            existing = self.db.get_audio_file_by_path(file_path)
            if existing:
                skipped_count += 1
                if file_path not in seen_duplicates:
                    duplicate_paths.append(file_path)
                    seen_duplicates.add(file_path)
                continue

            # Extract metadata
            metadata = MetadataExtractor.extract(file_path)

            # Create audio file record
            audio_file = AudioFile(
                file_path=file_path,
                title=metadata["title"],
                artist=metadata["artist"],
                duration_seconds=metadata["duration_seconds"]
            )

            self.db.add_audio_file(audio_file)
            added_count += 1

        # Refresh display
        self._load_files()
        self.library_updated.emit()

        if duplicate_paths:
            dialog = DuplicateFilesDialog(self, duplicates=duplicate_paths)
            dialog.exec()

    # Drag and drop support
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_hint.setStyleSheet(Styles.empty_state_style(active=True))

    def dragLeaveEvent(self, event):
        """Handle drag leave"""
        self.drop_hint.setStyleSheet(Styles.empty_state_style())

    def dropEvent(self, event: QDropEvent):
        """Handle file drop"""
        self.drop_hint.setStyleSheet(Styles.empty_state_style())

        file_paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path):
                file_paths.append(path)
            elif os.path.isdir(path):
                # Recursively find audio files in directory
                for root, dirs, files in os.walk(path):
                    for f in files:
                        file_path = os.path.join(root, f)
                        if MetadataExtractor.is_supported_format(file_path):
                            file_paths.append(file_path)

        if file_paths:
            self._import_files(file_paths)

        event.acceptProposedAction()

    def get_selected_files(self) -> list[AudioFile]:
        """Get currently selected files"""
        return self.file_table.get_selected_files()

    def refresh(self):
        """Refresh the library view"""
        self._load_files()
