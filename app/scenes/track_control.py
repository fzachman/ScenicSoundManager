"""Individual track control widget"""

import os
from typing import cast

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from ..audio import TrackPlayer
from ..database import SceneAudioFile
from ..shared.base_control_card import SceneControlCard
from ..shared.position_scrubber import PositionScrubber
from ..shared.styles import Styles


class TrackControl(SceneControlCard):
    """Widget for controlling a single track in a scene"""

    MIME_TYPE = "application/x-soundmanager-track"

    def __init__(
        self, track: SceneAudioFile, player: TrackPlayer | None = None, parent=None
    ):
        super().__init__(parent)
        self.track = track
        self.player = player

        self._init_card_state()
        self._base_style = Styles.card_frame_style("TrackControl")
        self.setStyleSheet(self._base_style)
        if self.track.audio_file:
            self.setToolTip(self.track.audio_file.file_path)

        self._setup_ui()
        self._connect_player_signals()
        self._update_play_mode_ui()

    # --- Hooks for the shared base ---

    @property
    def _model(self) -> SceneAudioFile:
        return self.track

    @property
    def _entity_id(self) -> int:
        # A control only exists for a persisted track, so id is always set.
        return cast(int, self.track.id)

    def _active_card_style(self) -> str:
        return Styles.card_frame_style(
            "TrackControl",
            accent_color=Styles.SUCCESS,
            border_color=Styles.SUCCESS,
            background_color=Styles.BACKGROUND_LIGHT,
        )

    def _inactive_card_style(self) -> str:
        return self._base_style

    def _after_play_mode_update(self) -> None:
        # TrackControl refreshes the repeat button after a play-mode restyle.
        self._update_repeat_button()

    def _on_volume_applied(self, value: int) -> None:
        if self.player:
            self.player.target_volume = value

    def _on_repeat_applied(self) -> None:
        if self.player:
            self.player.repeat = self._repeat_mode

    # --- UI ---

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Top row: title, play, remove
        top_row = QHBoxLayout()

        # Title
        title = (
            self.track.audio_file.display_title if self.track.audio_file else "Unknown"
        )
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(Styles.title_style(size=14))
        self.title_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        top_row.addWidget(self.title_label, 1)

        # File missing indicator
        if self.track.audio_file and not os.path.exists(
            self.track.audio_file.file_path
        ):
            missing_label = QLabel("⚠️ File not found")
            missing_label.setStyleSheet(
                f"color: {Styles.WARNING}; font-size: 11px; font-weight: 700;"
            )
            top_row.addWidget(missing_label)

        # Play/Pause button (shared builder; styled by _update_play_mode_ui)
        top_row.addWidget(self._build_play_button())

        layout.addLayout(top_row)

        # Middle row: position scrubber (shared component). Duration comes from
        # file metadata so the length shows before playback starts; position is
        # driven by the player once connected.
        self.scrubber = PositionScrubber()
        self.scrubber.set_duration_text(
            self.track.audio_file.duration_formatted
            if self.track.audio_file
            else "--:--"
        )
        self.scrubber.seek.connect(self._on_seek)
        # Stable public handles (tests / external refs poke these).
        self.position_slider = self.scrubber.slider
        self.position_label = self.scrubber.position_label
        self.duration_label = self.scrubber.duration_label
        layout.addWidget(self.scrubber)

        # Bottom row: volume (shared component) and repeat (shared builder)
        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self._build_volume_row())
        bottom_row.addStretch()
        bottom_row.addWidget(self._build_repeat_button())
        layout.addLayout(bottom_row)

    # --- Player integration (specific to TrackControl) ---

    def _connect_player_signals(self):
        """Connect to player signals if available"""
        if self.player:
            self.player.position_changed.connect(self._on_player_position)
            self.player.end_reached.connect(self.scrubber.reset)

    def set_player(self, player: TrackPlayer):
        """Set the track player"""
        self.player = player
        self._connect_player_signals()

        # Apply current settings
        self.player.target_volume = round(self.track.volume * 100)
        self.player.repeat = self.track.is_repeat

    def _on_player_position(self, position_ms: int):
        """Forward the player's position to the scrubber."""
        if self.player:
            self.scrubber.set_progress(position_ms, self.player.get_duration())

    def _on_seek(self, fraction: float):
        """Map the scrubber's 0..1 release fraction to ms and seek the player."""
        if self.player:
            duration = self.player.get_duration()
            # Don't seek before VLC reports a length (get_duration() can be 0 or
            # -1); otherwise a release would jump to 0 / an invalid time.
            if duration > 0:
                self.player.set_position(int(fraction * duration))
