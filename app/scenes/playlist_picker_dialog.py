"""Dialog for selecting a playlist to add to a scene"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..database import DatabaseConnection, Playlist
from ..shared.layouts import clear_layout
from ..shared.styles import Styles


class PlaylistSelectItem(QFrame):
    """Selectable playlist item in picker dialog"""

    clicked = pyqtSignal(object)  # emits self

    def __init__(self, playlist: Playlist, disabled: bool = False, parent=None):
        super().__init__(parent)
        self.playlist = playlist
        self._selected = False
        self._disabled = disabled

        self.setFrameStyle(QFrame.Shape.StyledPanel)
        if not disabled:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Playlist type indicator
        type_label = QLabel("PL")
        type_label.setFixedSize(28, 28)
        type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        color = Styles.TEXT_MUTED if disabled else Styles.PRIMARY
        type_label.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: white;
                border-radius: 4px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        layout.addWidget(type_label)

        # Playlist info
        info_layout = QVBoxLayout()
        text_color = Styles.TEXT_MUTED if disabled else ""
        title_label = QLabel(playlist.name)
        title_label.setStyleSheet(
            f"font-weight: bold; color: {text_color};"
            if disabled
            else "font-weight: bold;"
        )
        info_layout.addWidget(title_label)

        track_count = len(playlist.tracks) if playlist.tracks else 0
        count_label = QLabel(f"{track_count} track{'s' if track_count != 1 else ''}")
        count_label.setStyleSheet(f"color: {Styles.TEXT_MUTED}; font-size: 11px;")
        info_layout.addWidget(count_label)

        layout.addLayout(info_layout, 1)

        # "Already added" label for disabled items
        if disabled:
            added_label = QLabel("Already added")
            added_label.setStyleSheet(
                f"color: {Styles.TEXT_MUTED}; font-size: 11px; font-style: italic;"
            )
            layout.addWidget(added_label)

    def _update_style(self):
        """Update visual style based on selection and disabled state"""
        if self._disabled:
            self.setStyleSheet(f"""
                PlaylistSelectItem {{
                    background-color: {Styles.BACKGROUND};
                    border: 1px solid {Styles.BORDER};
                    border-radius: 4px;
                }}
            """)
        elif self._selected:
            self.setStyleSheet(f"""
                PlaylistSelectItem {{
                    background-color: {Styles.PRIMARY};
                    border: 1px solid {Styles.PRIMARY};
                    border-radius: 4px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                PlaylistSelectItem {{
                    background-color: {Styles.BACKGROUND_LIGHT};
                    border: 1px solid {Styles.BORDER};
                    border-radius: 4px;
                }}
                PlaylistSelectItem:hover {{
                    background-color: {Styles.BACKGROUND_LIGHTER};
                }}
            """)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._update_style()

    def mousePressEvent(self, event):
        if self._disabled:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self)


class PlaylistPickerDialog(QDialog):
    """Dialog for selecting a playlist to add to a scene (single-select)"""

    def __init__(
        self,
        db: DatabaseConnection,
        disabled_playlist_ids: set[int] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.db = db
        self._disabled_ids = disabled_playlist_ids or set()
        self.selected_playlist: Playlist | None = None
        self._items: list[PlaylistSelectItem] = []
        self._selected_item: PlaylistSelectItem | None = None

        self.setWindowTitle("Add Playlist to Scene")
        self.setMinimumSize(400, 350)
        self._setup_ui()
        self._load_playlists()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search playlists...")
        self.search_input.textChanged.connect(self._on_search)
        layout.addWidget(self.search_input)

        # Playlist list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()

        scroll.setWidget(self.list_container)
        layout.addWidget(scroll)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self.add_btn = QPushButton("Add Selected")
        self.add_btn.clicked.connect(self.accept)
        self.add_btn.setEnabled(False)
        button_layout.addWidget(self.add_btn)

        layout.addLayout(button_layout)

    def _load_playlists(self, query: str = ""):
        """Load playlists from database"""
        clear_layout(self.list_layout, keep_trailing_items=1)
        self._items.clear()
        self._selected_item = None
        self.add_btn.setEnabled(False)

        # Load playlists
        if query:
            playlists = self.db.search_playlists(query)
        else:
            playlists = self.db.get_all_playlists()

        # Load track counts for each playlist
        for playlist in playlists:
            full = self.db.get_playlist(playlist.id)
            if full:
                playlist.tracks = full.tracks

        for playlist in playlists:
            disabled = playlist.id in self._disabled_ids
            item = PlaylistSelectItem(playlist, disabled=disabled)
            item.clicked.connect(self._on_item_clicked)
            self._items.append(item)
            self.list_layout.insertWidget(self.list_layout.count() - 1, item)

    def _on_search(self, query: str):
        self._load_playlists(query)

    def _on_item_clicked(self, item: PlaylistSelectItem):
        """Handle item click - single select"""
        if self._selected_item and self._selected_item is not item:
            self._selected_item.set_selected(False)

        if self._selected_item is item:
            # Toggle off
            item.set_selected(False)
            self._selected_item = None
            self.selected_playlist = None
            self.add_btn.setEnabled(False)
        else:
            item.set_selected(True)
            self._selected_item = item
            self.selected_playlist = item.playlist
            self.add_btn.setEnabled(True)

    def get_selected_playlist(self) -> Playlist | None:
        return self.selected_playlist
