"""Get Info dialog for viewing and editing metadata of multiple audio files"""

from enum import Enum

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..database import AudioFile, DatabaseConnection, Tag
from ..shared.layouts import FlowLayout
from ..shared.logging import get_logger
from ..shared.styles import Styles
from .tag_manager import TagBadge


def _tag_id(tag: Tag) -> int:
    """The id of a persisted tag (tags here always come from the DB)."""
    assert tag.id is not None
    return tag.id


log = get_logger(__name__)


class TagState(Enum):
    NONE = "none"
    PARTIAL = "partial"
    ALL = "all"


class GetInfoDialog(QDialog):
    """Dialog for viewing and bulk-editing metadata of multiple audio files"""

    def __init__(
        self, db: DatabaseConnection, audio_files: list[AudioFile], parent=None
    ):
        super().__init__(parent)
        self.db = db
        self._audio_files = audio_files
        self._file_ids = [f.id for f in audio_files if f.id is not None]
        self._total = len(audio_files)

        self._tag_states: dict[int, TagState] = {}
        self._original_tag_states: dict[int, TagState] = {}
        self._tag_counts: dict[int, int] = {}
        self._badges: dict[int, TagBadge] = {}
        self._all_tags: list[Tag] = []

        self._artist_changed = False

        self.setWindowTitle("Info")
        self.setMinimumSize(450, 400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Header — file count
        header = QLabel(f"{self._total} file{'s' if self._total != 1 else ''} selected")
        header.setStyleSheet(f"color: {Styles.TEXT_MUTED}; font-size: 13px;")
        layout.addWidget(header)

        # Artist section
        self._setup_artist_section(layout)

        # Tags section
        self._setup_tags_section(layout)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

    def _setup_artist_section(self, parent_layout: QVBoxLayout):
        label = QLabel("Artist")
        label.setStyleSheet(f"color: {Styles.TEXT}; font-size: 13px; font-weight: 600;")
        parent_layout.addWidget(label)

        self._artist_combo = QComboBox()
        self._artist_combo.setEditable(True)
        self._artist_combo.setStyleSheet(self._combobox_style())

        # Collect unique artist values (including None/empty as distinct)
        unique_values: set[str | None] = set()
        non_empty_artists: set[str] = set()
        for f in self._audio_files:
            unique_values.add(f.artist or None)
            if f.artist:
                non_empty_artists.add(f.artist)

        sorted_artists = sorted(non_empty_artists, key=str.lower)

        # Add empty option first (to allow clearing)
        self._artist_combo.addItem("")
        for artist in sorted_artists:
            self._artist_combo.addItem(artist)

        # Determine initial state — only pre-fill if ALL files have the same value
        if len(unique_values) == 1 and len(non_empty_artists) == 1:
            self._artist_combo.setCurrentText(next(iter(non_empty_artists)))
        elif len(unique_values) == 1:
            # All files have no artist
            self._artist_combo.setCurrentIndex(0)
        else:
            # Mixed — default to empty option with placeholder hint
            self._artist_combo.setCurrentIndex(0)
            line_edit = self._artist_combo.lineEdit()
            if line_edit is not None:
                line_edit.setPlaceholderText("Multiple values")
                palette = line_edit.palette()
                palette.setColor(
                    QPalette.ColorRole.PlaceholderText, QColor(Styles.TEXT_SUBTLE)
                )
                line_edit.setPalette(palette)

        # Connect AFTER setting initial value to avoid false positive
        self._artist_combo.currentTextChanged.connect(self._on_artist_changed)

        parent_layout.addWidget(self._artist_combo)

    def _setup_tags_section(self, parent_layout: QVBoxLayout):
        label = QLabel("Tags")
        label.setStyleSheet(f"color: {Styles.TEXT}; font-size: 13px; font-weight: 600;")
        parent_layout.addWidget(label)

        self._all_tags = self.db.get_all_tags()

        if not self._all_tags:
            empty_label = QLabel(
                "No tags available.\nCreate tags using the tag manager."
            )
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet(f"color: {Styles.TEXT_MUTED}; font-size: 13px;")
            parent_layout.addWidget(empty_label)
            return

        # Compute per-tag counts from the audio files' tag lists
        tags_by_file = self.db._batch_load_tags(self._file_ids)
        for _file_id, file_tags in tags_by_file.items():
            for tag in file_tags:
                tid = _tag_id(tag)
                self._tag_counts[tid] = self._tag_counts.get(tid, 0) + 1

        # Determine initial states
        for tag in self._all_tags:
            tid = _tag_id(tag)
            count = self._tag_counts.get(tid, 0)
            if count == 0:
                state = TagState.NONE
            elif count == self._total:
                state = TagState.ALL
            else:
                state = TagState.PARTIAL
            self._tag_states[tid] = state
            self._original_tag_states[tid] = state

        # Scrollable tag area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        flow = FlowLayout(container, spacing=8)

        for tag in self._all_tags:
            badge = TagBadge(tag, removable=False)
            badge.clicked.connect(self._on_tag_clicked)
            flow.addWidget(badge)
            tid = _tag_id(tag)
            self._badges[tid] = badge
            self._apply_tag_style(tag, self._tag_states[tid])

        scroll.setWidget(container)
        parent_layout.addWidget(scroll, 1)

    def _apply_tag_style(self, tag: Tag, state: TagState):
        badge = self._badges[_tag_id(tag)]
        color = tag.color or Styles.TAG_COLORS[0]

        if state == TagState.ALL:
            badge.set_label_style(
                Styles.tag_badge_style(
                    color, border_color=Styles.PRIMARY, border_style="solid"
                )
            )
            badge.label.setText(tag.name)
        elif state == TagState.PARTIAL:
            count = self._tag_counts.get(_tag_id(tag), 0)
            badge.set_label_style(
                Styles.tag_badge_style(
                    color, border_color=Styles.PRIMARY, border_style="dashed"
                )
            )
            badge.label.setText(f"{tag.name} ({count}/{self._total})")
        else:
            badge.set_label_style(Styles.tag_badge_style(color))
            badge.label.setText(tag.name)

        badge.label.adjustSize()

    def _on_tag_clicked(self, tag: Tag):
        tid = _tag_id(tag)
        current = self._tag_states[tid]
        if current in (TagState.NONE, TagState.PARTIAL):
            self._tag_states[tid] = TagState.ALL
            self._apply_tag_style(tag, TagState.ALL)
        else:
            self._tag_states[tid] = TagState.NONE
            self._apply_tag_style(tag, TagState.NONE)

    def _on_artist_changed(self, text: str):
        self._artist_changed = True

    def get_artist_value(self) -> str | None:
        """Return the new artist value, or None if unchanged."""
        if not self._artist_changed:
            return None
        return self._artist_combo.currentText().strip() or None

    def get_artist_should_clear(self) -> bool:
        """Return True if the user explicitly cleared the artist field."""
        return self._artist_changed and not self._artist_combo.currentText().strip()

    def get_tags_to_add(self) -> list[int]:
        """Tag IDs that should be added to all files."""
        return [
            tag_id
            for tag_id, state in self._tag_states.items()
            if state == TagState.ALL
            and self._original_tag_states[tag_id] != TagState.ALL
        ]

    def get_tags_to_remove(self) -> list[int]:
        """Tag IDs that should be removed from all files."""
        return [
            tag_id
            for tag_id, state in self._tag_states.items()
            if state == TagState.NONE
            and self._original_tag_states[tag_id] != TagState.NONE
        ]

    @staticmethod
    def _combobox_style() -> str:
        return f"""
            QComboBox {{
                background-color: {Styles.BACKGROUND_ELEVATED};
                color: {Styles.TEXT};
                border: 1px solid {Styles.BORDER};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }}
            QComboBox QLineEdit::placeholder {{
                color: {Styles.TEXT_SUBTLE};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {Styles.TEXT_MUTED};
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Styles.BACKGROUND_ELEVATED};
                color: {Styles.TEXT};
                border: 1px solid {Styles.BORDER};
                selection-background-color: {Styles.PRIMARY};
            }}
        """
