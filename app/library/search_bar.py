"""Search bar component for filtering library"""

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QWidget


class SearchBar(QWidget):
    """Search bar with lightly debounced input"""

    search_changed = pyqtSignal(str)  # Emitted when search text changes

    def __init__(self, parent=None, placeholder: str = "Search..."):
        super().__init__(parent)

        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._emit_search)

        self._setup_ui(placeholder)

    def _setup_ui(self, placeholder: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(placeholder)
        self.search_input.textChanged.connect(self._on_text_changed)
        self.search_input.setClearButtonEnabled(True)
        layout.addWidget(self.search_input)

    def _on_text_changed(self, text: str):
        """Handle text change with a short debounce"""
        self._debounce_timer.start(300)

    def _emit_search(self):
        """Emit the search signal"""
        self.search_changed.emit(self.search_input.text())

    def get_text(self) -> str:
        """Get current search text"""
        return self.search_input.text()

    def set_text(self, text: str):
        """Set search text"""
        self.search_input.setText(text)

    def clear(self):
        """Clear search text"""
        self.search_input.clear()
