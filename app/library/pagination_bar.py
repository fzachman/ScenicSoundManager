"""Pagination bar widget for library file list"""

import math

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, QSettings

from ..shared.styles import Styles


class PaginationBar(QWidget):
    """Pagination controls with page size selector and navigation"""

    page_changed = pyqtSignal()

    SETTINGS_GROUP = "library/pagination"
    SETTINGS_PAGE_SIZE = "page_size"

    PAGE_SIZE_OPTIONS = ["25", "50", "100", "All"]
    DEFAULT_PAGE_SIZE = "50"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_files = []
        self._current_page = 0
        self._page_size = 50  # 0 means "All"
        self._page_buttons = []

        self._setup_ui()
        self._restore_page_size()
        self._update_display()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # File count label (left side)
        self.count_label = QLabel()
        self.count_label.setStyleSheet(Styles.subtle_text_style(size=12))
        layout.addWidget(self.count_label)

        layout.addStretch()

        # Page size selector
        size_label = QLabel("Show:")
        size_label.setStyleSheet(Styles.subtle_text_style(size=12))
        layout.addWidget(size_label)

        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(self.PAGE_SIZE_OPTIONS)
        self.page_size_combo.setFixedWidth(70)
        self.page_size_combo.setStyleSheet(self._combobox_style())
        self.page_size_combo.currentTextChanged.connect(self._on_page_size_changed)
        layout.addWidget(self.page_size_combo)

        # Navigation buttons
        self.first_btn = self._nav_button("\u00ab")
        self.first_btn.clicked.connect(lambda: self._go_to_page(0))
        layout.addWidget(self.first_btn)

        self.prev_btn = self._nav_button("\u2039")
        self.prev_btn.clicked.connect(lambda: self._go_to_page(self._current_page - 1))
        layout.addWidget(self.prev_btn)

        # Page number container
        self._page_btn_layout = QHBoxLayout()
        self._page_btn_layout.setSpacing(2)
        layout.addLayout(self._page_btn_layout)

        self.next_btn = self._nav_button("\u203a")
        self.next_btn.clicked.connect(lambda: self._go_to_page(self._current_page + 1))
        layout.addWidget(self.next_btn)

        self.last_btn = self._nav_button("\u00bb")
        self.last_btn.clicked.connect(lambda: self._go_to_page(self._total_pages - 1))
        layout.addWidget(self.last_btn)

    def _nav_button(self, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(28, 24)
        btn.setStyleSheet(self._nav_button_style())
        return btn

    def set_files(self, files: list, preserve_page: bool = False):
        """Store full file list and optionally reset to page 0"""
        self._all_files = files
        if not preserve_page:
            self._current_page = 0
        # Clamp current page to valid range
        max_page = max(0, self._total_pages - 1)
        self._current_page = min(self._current_page, max_page)
        self._update_display()
        self.page_changed.emit()

    def sort_files(self, key_func, reverse: bool = False):
        """Sort the full file list and re-paginate, preserving current page"""
        self._all_files.sort(key=key_func, reverse=reverse)
        max_page = max(0, self._total_pages - 1)
        self._current_page = min(self._current_page, max_page)
        self._update_display()
        self.page_changed.emit()

    def get_current_page_files(self) -> list:
        """Return the slice of files for the current page"""
        if self._page_size == 0:  # "All"
            return self._all_files
        start = self._current_page * self._page_size
        end = min(start + self._page_size, len(self._all_files))
        return self._all_files[start:end]

    @property
    def _total_pages(self) -> int:
        if self._page_size == 0 or len(self._all_files) == 0:
            return 1
        return math.ceil(len(self._all_files) / self._page_size)

    def _go_to_page(self, page: int):
        page = max(0, min(page, self._total_pages - 1))
        if page == self._current_page:
            return
        self._current_page = page
        self._update_display()
        self.page_changed.emit()

    def _on_page_size_changed(self, text: str):
        if text == "All":
            self._page_size = 0
        else:
            self._page_size = int(text)
        self._current_page = 0
        self._save_page_size()
        self._update_display()
        self.page_changed.emit()

    def _update_display(self):
        total = len(self._all_files)
        total_pages = self._total_pages
        show_all = self._page_size == 0

        # Update count label
        if total == 0:
            self.count_label.setText("0 files")
        elif show_all:
            self.count_label.setText(f"{total} file{'s' if total != 1 else ''}")
        else:
            start = self._current_page * self._page_size + 1
            end = min(start + self._page_size - 1, total)
            self.count_label.setText(f"{start}\u2013{end} of {total} files")

        # Enable/disable nav buttons
        has_prev = self._current_page > 0 and not show_all
        has_next = self._current_page < total_pages - 1 and not show_all
        self.first_btn.setEnabled(has_prev)
        self.prev_btn.setEnabled(has_prev)
        self.next_btn.setEnabled(has_next)
        self.last_btn.setEnabled(has_next)

        # Show/hide nav when "All" or single page
        nav_visible = not show_all and total_pages > 1
        self.first_btn.setVisible(nav_visible)
        self.prev_btn.setVisible(nav_visible)
        self.next_btn.setVisible(nav_visible)
        self.last_btn.setVisible(nav_visible)

        # Rebuild page number buttons
        self._rebuild_page_buttons(total_pages, nav_visible)

    def _rebuild_page_buttons(self, total_pages: int, visible: bool):
        # Clear existing
        for btn in self._page_buttons:
            self._page_btn_layout.removeWidget(btn)
            btn.deleteLater()
        self._page_buttons.clear()

        if not visible:
            return

        # Window of up to 5 pages centered on current
        max_buttons = 5
        window_start = max(0, self._current_page - max_buttons // 2)
        window_end = min(total_pages, window_start + max_buttons)
        # Adjust start if window_end hit the limit
        window_start = max(0, window_end - max_buttons)

        for page in range(window_start, window_end):
            btn = QPushButton(str(page + 1))
            btn.setFixedSize(28, 24)
            is_current = page == self._current_page
            btn.setStyleSheet(self._page_button_style(is_current))
            btn.clicked.connect(lambda checked, p=page: self._go_to_page(p))
            self._page_btn_layout.addWidget(btn)
            self._page_buttons.append(btn)

    def _save_page_size(self):
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        settings.setValue(self.SETTINGS_PAGE_SIZE, self.page_size_combo.currentText())
        settings.endGroup()

    def _restore_page_size(self):
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        saved = settings.value(self.SETTINGS_PAGE_SIZE, self.DEFAULT_PAGE_SIZE)
        settings.endGroup()

        index = self.page_size_combo.findText(str(saved))
        if index >= 0:
            self.page_size_combo.blockSignals(True)
            self.page_size_combo.setCurrentIndex(index)
            self.page_size_combo.blockSignals(False)
            if saved == "All":
                self._page_size = 0
            else:
                self._page_size = int(saved)

    @staticmethod
    def _combobox_style() -> str:
        return f"""
            QComboBox {{
                background-color: {Styles.BACKGROUND_ELEVATED};
                color: {Styles.TEXT};
                border: 1px solid {Styles.BORDER};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 12px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 16px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {Styles.TEXT_MUTED};
                margin-right: 4px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Styles.BACKGROUND_ELEVATED};
                color: {Styles.TEXT};
                border: 1px solid {Styles.BORDER};
                selection-background-color: {Styles.PRIMARY};
            }}
        """

    @staticmethod
    def _nav_button_style() -> str:
        return f"""
            QPushButton {{
                background-color: {Styles.BACKGROUND_LIGHTER};
                color: {Styles.TEXT};
                border: 1px solid {Styles.BORDER};
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: {Styles.BACKGROUND_HOVER};
            }}
            QPushButton:disabled {{
                color: {Styles.TEXT_SUBTLE};
                background-color: {Styles.BACKGROUND_ELEVATED};
                border-color: {Styles.BORDER};
            }}
        """

    @staticmethod
    def _page_button_style(is_current: bool) -> str:
        if is_current:
            return f"""
                QPushButton {{
                    background-color: {Styles.PRIMARY};
                    color: {Styles.TEXT};
                    border: 1px solid {Styles.PRIMARY};
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                    padding: 0;
                }}
            """
        return f"""
            QPushButton {{
                background-color: {Styles.BACKGROUND_LIGHTER};
                color: {Styles.TEXT};
                border: 1px solid {Styles.BORDER};
                border-radius: 4px;
                font-size: 12px;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: {Styles.BACKGROUND_HOVER};
            }}
        """
