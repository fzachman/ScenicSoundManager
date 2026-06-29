"""Individual track control widget"""

import os
from typing import cast

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
)

from ..audio import TrackPlayer
from ..database import SceneAudioFile
from ..shared.base_control_card import SceneControlCard
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
        self._updating_position = False

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

        # Middle row: position slider
        position_row = QHBoxLayout()

        self.position_label = QLabel("0:00")
        self.position_label.setFixedWidth(45)
        self.position_label.setStyleSheet(Styles.subtle_text_style(size=11))
        self.position_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        position_row.addWidget(self.position_label)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setMinimum(0)
        self.position_slider.setMaximum(1000)
        self.position_slider.setValue(0)
        self.position_slider.sliderPressed.connect(self._on_position_pressed)
        self.position_slider.sliderReleased.connect(self._on_position_released)
        position_row.addWidget(self.position_slider, 1)

        self.duration_label = QLabel(
            self.track.audio_file.duration_formatted
            if self.track.audio_file
            else "--:--"
        )
        self.duration_label.setFixedWidth(45)
        self.duration_label.setStyleSheet(Styles.subtle_text_style(size=11))
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.duration_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        position_row.addWidget(self.duration_label)

        layout.addLayout(position_row)

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
            self.player.position_changed.connect(self._update_position)
            self.player.end_reached.connect(self._on_end_reached)

    def set_player(self, player: TrackPlayer):
        """Set the track player"""
        self.player = player
        self._connect_player_signals()

        # Apply current settings
        self.player.target_volume = int(self.track.volume * 100)
        self.player.repeat = self.track.is_repeat

    def _update_position(self, position_ms: int):
        """Update position display"""
        if self._updating_position:
            return

        if self.player:
            duration = self.player.get_duration()
            if duration > 0:
                self.position_slider.setValue(int(position_ms * 1000 / duration))

            # Update time label
            seconds = position_ms // 1000
            minutes = seconds // 60
            seconds = seconds % 60
            self.position_label.setText(f"{minutes}:{seconds:02d}")

    def _on_position_pressed(self):
        """Handle position slider press"""
        self._updating_position = True

    def _on_position_released(self):
        """Handle position slider release"""
        if self.player:
            duration = self.player.get_duration()
            if duration > 0:
                position = int(self.position_slider.value() * duration / 1000)
                self.player.set_position(position)

        self._updating_position = False

    def _on_end_reached(self):
        """Handle end of playback"""
        self.position_slider.setValue(0)
        self.position_label.setText("0:00")
