"""Dialog for selecting tags to apply to multiple audio files"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QWidget, QFrame
)
from PyQt6.QtCore import Qt

from ..database import DatabaseConnection, Tag
from ..shared.styles import Styles
from .tag_manager import TagBadge, FlowLayout


class TagSelectionDialog(QDialog):
    """Dialog for selecting one or more tags to apply in bulk"""

    def __init__(self, db: DatabaseConnection, parent=None):
        super().__init__(parent)
        self.db = db
        self._selected_tag_ids: set[int] = set()
        self._badges: dict[int, TagBadge] = {}

        self.setWindowTitle("Add Tags to Selected Files")
        self.setMinimumSize(400, 300)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        tags = self.db.get_all_tags()

        if not tags:
            empty_label = QLabel("No tags available.\nCreate tags using the tag manager above.")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet(f"color: {Styles.TEXT_MUTED}; font-size: 13px;")
            layout.addWidget(empty_label)

            button_layout = QHBoxLayout()
            button_layout.addStretch()
            cancel_btn = QPushButton("Cancel")
            cancel_btn.clicked.connect(self.reject)
            button_layout.addWidget(cancel_btn)
            layout.addLayout(button_layout)
            return

        label = QLabel("Select tags to add:")
        label.setStyleSheet(f"color: {Styles.TEXT}; font-size: 13px;")
        layout.addWidget(label)

        # Scrollable tag area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        flow = FlowLayout(container, spacing=8)

        for tag in tags:
            badge = TagBadge(tag, removable=False)
            badge.clicked.connect(self._on_tag_clicked)
            flow.addWidget(badge)
            self._badges[tag.id] = badge

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self.tag_btn = QPushButton("Tag")
        self.tag_btn.clicked.connect(self.accept)
        self.tag_btn.setEnabled(False)
        button_layout.addWidget(self.tag_btn)

        layout.addLayout(button_layout)

    def _on_tag_clicked(self, tag: Tag):
        if tag.id in self._selected_tag_ids:
            self._selected_tag_ids.discard(tag.id)
            badge = self._badges[tag.id]
            color = tag.color or Styles.TAG_COLORS[0]
            badge.set_label_style(Styles.tag_badge_style(color))
        else:
            self._selected_tag_ids.add(tag.id)
            badge = self._badges[tag.id]
            color = tag.color or Styles.TAG_COLORS[0]
            badge.set_label_style(
                Styles.tag_badge_style(color, border_color=Styles.PRIMARY)
            )
        self.tag_btn.setEnabled(len(self._selected_tag_ids) > 0)

    def get_selected_tag_ids(self) -> list[int]:
        return list(self._selected_tag_ids)
