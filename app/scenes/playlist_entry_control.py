"""Control widget for a playlist entry within a scene"""

from typing import cast

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ..database import ScenePlaylistEntry
from ..shared.base_control_card import SceneControlCard
from ..shared.styles import Styles


class PlaylistEntryControl(SceneControlCard):
    """Widget for controlling a playlist entry in a scene"""

    # Unique to playlist entries (TrackControl has no shuffle concept).
    shuffle_changed = pyqtSignal(int, bool)  # entry_id, is_shuffle

    MIME_TYPE = "application/x-soundmanager-scene-playlist"

    def __init__(self, entry: ScenePlaylistEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self._shuffle_mode = bool(entry.is_shuffle)

        self._init_card_state()
        self._base_style = Styles.card_frame_style(
            "PlaylistEntryControl",
            accent_color=Styles.PRIMARY,
            border_color=Styles.PRIMARY,
        )
        if self.entry.playlist:
            self.setToolTip(f"Playlist: {self.entry.playlist.name}")

        self._setup_ui()
        # Note: no setStyleSheet here — _update_play_mode_ui applies the frame
        # style for both states.
        self._update_play_mode_ui()

    # --- Hooks for the shared base ---

    @property
    def _model(self) -> ScenePlaylistEntry:
        return self.entry

    @property
    def _entity_id(self) -> int:
        # A control only exists for a persisted entry, so id is always set.
        return cast(int, self.entry.id)

    def _active_card_style(self) -> str:
        return self._base_style

    def _inactive_card_style(self) -> str:
        return Styles.card_frame_style(
            "PlaylistEntryControl",
            border_color=Styles.BORDER,
            background_color=Styles.BACKGROUND_LIGHT,
        )

    # --- UI ---

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Top row: playlist icon + title + remove
        top_row = QHBoxLayout()

        # Playlist type indicator
        type_label = QLabel("PL")
        type_label.setFixedSize(28, 28)
        type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        type_label.setStyleSheet(f"""
            QLabel {{
                background-color: {Styles.PRIMARY};
                color: white;
                border-radius: 8px;
                font-size: 10px;
                font-weight: 700;
            }}
        """)
        top_row.addWidget(type_label)

        # Title
        name = self.entry.playlist.name if self.entry.playlist else "Unknown Playlist"
        self.title_label = QLabel(name)
        self.title_label.setStyleSheet(Styles.title_style(size=14))
        self.title_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        top_row.addWidget(self.title_label, 1)

        # Play/Pause toggle button (shared builder; styled by _update_play_mode_ui)
        top_row.addWidget(self._build_play_button())

        layout.addLayout(top_row)

        # Now-playing row: shows currently playing track title
        self.now_playing_label = QLabel("")
        self.now_playing_label.setStyleSheet(
            f"color: {Styles.SUCCESS}; font-size: 11px; font-weight: 700; padding-left: 32px;"
        )
        self.now_playing_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.now_playing_label.hide()
        layout.addWidget(self.now_playing_label)

        # Volume row (shared component)
        volume_row = QHBoxLayout()
        volume_row.addWidget(self._build_volume_row())
        volume_row.addStretch()
        layout.addLayout(volume_row)

        # Bottom row: track count info + shuffle + repeat
        bottom_row = QHBoxLayout()

        # Track count from playlist
        if self.entry.playlist:
            track_count = (
                len(self.entry.playlist.tracks) if self.entry.playlist.tracks else 0
            )
            info_text = f"{track_count} track{'s' if track_count != 1 else ''}"
        else:
            info_text = "Unknown"
        self.info_label = QLabel(info_text)
        self.info_label.setStyleSheet(Styles.subtle_text_style(size=11))
        self.info_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        bottom_row.addWidget(self.info_label)

        bottom_row.addStretch()

        # Shuffle toggle (unique to playlist entries)
        self.shuffle_btn = QPushButton()
        self.shuffle_btn.setFixedSize(28, 28)
        self.shuffle_btn.setIcon(self._icons.icon("shuffle"))
        self.shuffle_btn.setIconSize(QSize(14, 14))
        self.shuffle_btn.clicked.connect(self._toggle_shuffle)
        bottom_row.addWidget(self.shuffle_btn)
        self._update_shuffle_button()

        # Repeat toggle (shared builder)
        bottom_row.addWidget(self._build_repeat_button())

        layout.addLayout(bottom_row)

    # --- Now-playing display ---

    def set_current_track(self, title: str):
        """Update the now-playing display with the current track title"""
        if title:
            self.now_playing_label.setText(f"Now playing: {title}")
            self.now_playing_label.show()
        else:
            self.now_playing_label.hide()

    # --- Shuffle (specific to PlaylistEntryControl) ---

    def _toggle_shuffle(self):
        """Toggle shuffle mode"""
        self._shuffle_mode = not self._shuffle_mode
        self.entry.is_shuffle = self._shuffle_mode
        self._update_shuffle_button()
        self.shuffle_changed.emit(self.entry.id, self._shuffle_mode)

    def _update_shuffle_button(self):
        """Update shuffle button appearance"""
        self.shuffle_btn.setStyleSheet(
            Styles.icon_toggle_button_style(self._shuffle_mode, size=28)
        )
