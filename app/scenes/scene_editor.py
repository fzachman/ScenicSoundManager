"""Scene editor for managing tracks in a scene"""

import os

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.shared.logging import get_logger

from ..audio import AudioEngine, SceneMixer, ScenePlaylistPlayer
from ..database import (
    PRESET_SLOTS,
    DatabaseConnection,
    Scene,
    SceneAudioFile,
    ScenePlaylistEntry,
)
from ..shared.dialogs import AudioFileSearchDialog, TextInputDialog
from ..shared.icons import IconLibrary
from ..shared.layouts import clear_layout
from ..shared.styles import Styles
from .playlist_entry_control import PlaylistEntryControl
from .track_control import TrackControl

_log = get_logger(__name__)

# Duration of the crossfade when switching presets while a scene plays.
PRESET_FADE_MS = 1500


class SceneEditor(QWidget):
    """Editor for a single scene's tracks"""

    scene_modified = pyqtSignal()
    playback_state_changed = pyqtSignal(
        object, object, bool
    )  # scene_id, scene_title, is_playing

    def __init__(self, db: DatabaseConnection, audio_engine: AudioEngine, parent=None):
        super().__init__(parent)
        self.db = db
        self.audio_engine = audio_engine
        self.mixer = SceneMixer(audio_engine)
        self._active_scene_id: int | None = None
        self._active_scene_title: str | None = None
        self._scene_playing = False
        self._current_scene: Scene | None = None
        self._preset_slot: int = 1
        self._track_controls: dict[int, TrackControl] = {}
        self._playlist_entry_controls: dict[int, PlaylistEntryControl] = {}
        self._playlist_players: dict[
            int, ScenePlaylistPlayer
        ] = {}  # entry_id -> player
        self._icons = IconLibrary()

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Header with scene title and master controls
        header = QHBoxLayout()
        header.setSpacing(12)

        self.title_label = QLabel("Select a scene")
        self.title_label.setStyleSheet(Styles.title_style(size=28))
        header.addWidget(self.title_label)

        header.addStretch()

        # Master controls
        self.play_toggle_btn = QPushButton("Play")
        self.play_toggle_btn.setIcon(self._icons.icon("play"))
        self.play_toggle_btn.setIconSize(QSize(16, 16))
        self.play_toggle_btn.setStyleSheet(
            Styles.playback_button_style(is_active=False)
        )
        self.play_toggle_btn.clicked.connect(self._toggle_scene_play)
        self.play_toggle_btn.setEnabled(False)
        header.addWidget(self.play_toggle_btn)

        layout.addLayout(header)

        # Add tracks / playlist buttons
        add_layout = QHBoxLayout()
        add_layout.setSpacing(10)
        self.add_tracks_btn = QPushButton("+ Add Tracks")
        self.add_tracks_btn.clicked.connect(self._add_tracks)
        self.add_tracks_btn.setEnabled(False)
        add_layout.addWidget(self.add_tracks_btn)

        self.add_playlist_btn = QPushButton("+ Add Playlist")
        self.add_playlist_btn.clicked.connect(self._add_playlist_entry)
        self.add_playlist_btn.setEnabled(False)
        add_layout.addWidget(self.add_playlist_btn)

        add_layout.addStretch()

        # Preset buttons (right-aligned). Exclusivity is enforced by
        # _sync_preset_buttons rather than a QButtonGroup so the checked
        # style swap follows the codebase's stylesheet-in-code convention.
        self._preset_buttons: dict[int, QPushButton] = {}
        for slot in PRESET_SLOTS:
            btn = QPushButton(f"Preset {slot}")
            btn.setCheckable(True)
            btn.setEnabled(False)
            btn.setStyleSheet(Styles.toggle_off_style())
            # clicked (not toggled): programmatic setChecked in
            # _sync_preset_buttons must never re-enter the handler.
            btn.clicked.connect(lambda _checked, s=slot: self._on_preset_clicked(s))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, s=slot: self._show_preset_menu(s, pos)
            )
            self._preset_buttons[slot] = btn
            add_layout.addWidget(btn)

        layout.addLayout(add_layout)

        # Tracks scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.tracks_container = TrackListContainer()
        self.tracks_container.order_changed.connect(self._on_tracks_reordered)
        self.tracks_layout = QVBoxLayout(self.tracks_container)
        self.tracks_layout.setContentsMargins(0, 8, 0, 0)
        self.tracks_layout.setSpacing(8)

        self.scroll_area.setWidget(self.tracks_container)
        layout.addWidget(self.scroll_area)
        self.scroll_area.hide()

        # Empty state
        self.empty_label = QLabel(
            "No tracks in this scene.\nClick '+ Add Tracks' or '+ Add Playlist' to get started."
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(Styles.empty_state_style())
        self.empty_label.hide()
        layout.addWidget(self.empty_label)

    def load_scene(self, scene: Scene):
        """Load a scene for editing"""
        self._current_scene = scene
        self.title_label.setText(scene.title)

        # Enable controls
        self.add_tracks_btn.setEnabled(True)
        self.add_playlist_btn.setEnabled(True)
        self.play_toggle_btn.setEnabled(True)
        self._sync_scene_play_button()

        self._preset_slot = scene.active_preset_slot
        for btn in self._preset_buttons.values():
            btn.setEnabled(True)
        self._sync_preset_buttons()

        # Load tracks and playlist entries
        self._refresh_tracks()

    def _refresh_tracks(self):
        """Refresh track and playlist entry display"""
        if not self._current_scene:
            return

        # Clear existing track controls and playlist entry controls
        clear_layout(self.tracks_layout)
        self.tracks_container.clear_registry()
        self._track_controls.clear()
        self._playlist_entry_controls.clear()

        # Load scene with tracks and playlist entries from DB
        scene = self.db.get_scene(self._current_scene.id)
        if not scene:
            return

        self._current_scene = scene

        has_content = bool(scene.tracks) or bool(scene.playlist_entries)
        if not has_content:
            self.empty_label.show()
            self.scroll_area.hide()
        else:
            self.empty_label.hide()
            self.scroll_area.show()

            is_active_scene = self._is_current_scene_active()
            for track in scene.tracks:
                self._add_track_control(track, is_active_scene)

            # Add playlist entries below audio tracks
            for entry in scene.playlist_entries:
                self._add_playlist_entry_control(entry)

    def _add_track_control(self, track: SceneAudioFile, use_active_players: bool):
        """Add a track control widget"""
        assert track.id is not None
        player = None
        created_player = False
        if use_active_players and track.audio_file:
            import os

            if os.path.exists(track.audio_file.file_path):
                player = self.mixer.get_player(track.id)
                if not player and self._scene_playing:
                    player = self.mixer.add_track(track.id, track.audio_file.file_path)
                    created_player = True
                if player:
                    player.target_volume = round(track.volume * 100)
                    player.repeat = track.is_repeat
                    if created_player and track.play_mode:
                        player.fade_in(500)

        # Create control widget
        control = TrackControl(track, player)
        control.volume_changed.connect(self._on_track_volume_changed)
        control.volume_committed.connect(self._on_track_volume_committed)
        control.repeat_changed.connect(self._on_track_repeat_changed)
        control.play_mode_changed.connect(self._on_track_play_mode_changed)
        control.remove_requested.connect(self._remove_track)

        self._track_controls[track.id] = control
        self.tracks_container.register_track(track.id, control)
        self.tracks_layout.addWidget(control)

    def _add_tracks(self):
        """Show dialog to add tracks"""
        if not self._current_scene:
            return

        existing_ids = {t.audio_file_id for t in self._current_scene.tracks}
        dialog = AudioFileSearchDialog(
            self.db,
            self.audio_engine,
            disabled_track_ids=existing_ids,
            parent=self,
        )
        if dialog.exec():
            files = dialog.get_selected_files()
            for file in files:
                position = len(self._current_scene.tracks)
                self.db.add_track_to_scene(self._current_scene.id, file.id, position)

            self._refresh_tracks()
            self.scene_modified.emit()

    def _add_playlist_entry_control(self, entry: ScenePlaylistEntry):
        """Add a playlist entry control widget"""
        assert entry.id is not None
        control = PlaylistEntryControl(entry)
        control.volume_changed.connect(self._on_playlist_entry_volume_changed)
        control.volume_committed.connect(self._on_playlist_entry_volume_committed)
        control.shuffle_changed.connect(self._on_playlist_entry_shuffle_changed)
        control.repeat_changed.connect(self._on_playlist_entry_repeat_changed)
        control.play_mode_changed.connect(self._on_playlist_entry_play_mode_changed)
        control.remove_requested.connect(self._remove_playlist_entry)
        control.next_requested.connect(self._on_playlist_entry_next)
        control.seek_requested.connect(self._on_playlist_entry_seek)

        # Register before refreshing now-playing: _update_playlist_entry_now_playing
        # looks the control up in this dict and would early-return if it ran first
        # (so a mid-playback re-add would lose its now-playing title + scrubber).
        self._playlist_entry_controls[entry.id] = control
        self.tracks_layout.addWidget(control)

        # Restore now-playing for an entry whose player is already active.
        player = self._playlist_players.get(entry.id)
        if player and player.current_audio_file_id:
            self._update_playlist_entry_now_playing(
                entry.id, player.current_audio_file_id
            )

    def _add_playlist_entry(self):
        """Show dialog to add a playlist to the scene"""
        if not self._current_scene:
            return

        from .playlist_picker_dialog import PlaylistPickerDialog

        existing_playlist_ids = {
            e.playlist_id for e in self._current_scene.playlist_entries
        }
        dialog = PlaylistPickerDialog(
            self.db,
            disabled_playlist_ids=existing_playlist_ids,
            parent=self,
        )
        if dialog.exec():
            playlist = dialog.get_selected_playlist()
            if playlist:
                position = len(self._current_scene.playlist_entries)
                self.db.add_playlist_to_scene(
                    self._current_scene.id, playlist.id, position
                )
                self._refresh_tracks()
                self.scene_modified.emit()

    def _remove_playlist_entry(self, entry_id: int):
        """Remove a playlist entry from the scene"""
        # Stop player if running
        player = self._playlist_players.pop(entry_id, None)
        if player:
            player.release()
        self.db.remove_playlist_from_scene(entry_id)
        self._refresh_tracks()
        self.scene_modified.emit()

    def _on_playlist_entry_volume_changed(self, entry_id: int, volume: float):
        """Live playlist-entry volume update during slider movement.

        Forwards to the running player and keeps the in-memory entry fresh.
        Persistence is deferred to _on_playlist_entry_volume_committed (slider
        release / discrete change) so a drag is one DB write, not one per tick.
        """
        if self._current_scene:
            for entry in self._current_scene.playlist_entries:
                if entry.id == entry_id:
                    entry.volume = volume
                    break
        # Forward to running player if active
        player = self._playlist_players.get(entry_id)
        if player:
            player.set_volume(round(volume * 100))

    def _on_playlist_entry_volume_committed(self, entry_id: int, volume: float):
        """Persist a playlist entry's volume once the user settles."""
        if not self._current_scene:
            return
        for entry in self._current_scene.playlist_entries:
            if entry.id == entry_id:
                entry.volume = volume
                break
        self.db.update_scene_playlist_entry_setting(entry_id, volume=volume)

    def _on_playlist_entry_shuffle_changed(self, entry_id: int, is_shuffle: bool):
        """Handle playlist entry shuffle toggle change"""
        if not self._current_scene:
            return
        for entry in self._current_scene.playlist_entries:
            if entry.id == entry_id:
                entry.is_shuffle = is_shuffle
                break
        self.db.update_scene_playlist_entry_setting(entry_id, is_shuffle=is_shuffle)
        # Forward to running player if active
        player = self._playlist_players.get(entry_id)
        if player:
            player.set_shuffle(is_shuffle)

    def _on_playlist_entry_repeat_changed(self, entry_id: int, is_repeat: bool):
        """Handle playlist entry repeat toggle change"""
        if not self._current_scene:
            return
        for entry in self._current_scene.playlist_entries:
            if entry.id == entry_id:
                entry.is_repeat = is_repeat
                break
        self.db.update_scene_playlist_entry_setting(entry_id, is_repeat=is_repeat)
        # Forward to running player if active
        player = self._playlist_players.get(entry_id)
        if player:
            player.set_repeat(is_repeat)

    def _on_playlist_entry_play_mode_changed(self, entry_id: int, play_mode: bool):
        """Handle playlist entry play mode change"""
        if not self._current_scene:
            return

        for entry in self._current_scene.playlist_entries:
            if entry.id == entry_id:
                entry.play_mode = play_mode
                break
        self.db.update_scene_playlist_entry_setting(entry_id, play_mode=play_mode)

        if self._is_current_scene_active() and self._scene_playing:
            self._apply_playlist_entry_play_mode(entry_id, play_mode)

    def _apply_playlist_entry_play_mode(self, entry_id: int, play_mode: bool):
        """Start or pause a playlist entry based on play mode"""
        if not self._current_scene:
            return
        if play_mode:
            entry = next(
                (e for e in self._current_scene.playlist_entries if e.id == entry_id),
                None,
            )
            if entry:
                existing = self._playlist_players.get(entry_id)
                if existing:
                    existing.resume(500)
                else:
                    self._start_playlist_entry(entry)
        else:
            player = self._playlist_players.get(entry_id)
            if player:
                player.pause(500)

    def _start_playlist_entry(self, entry: ScenePlaylistEntry, fade_ms: int = 500):
        """Create and start a ScenePlaylistPlayer for a playlist entry."""
        assert entry.id is not None and entry.playlist_id is not None
        player = ScenePlaylistPlayer(
            playlist_id=entry.playlist_id,
            db=self.db,
            engine=self.audio_engine,
            is_shuffle=entry.is_shuffle,
            is_repeat=entry.is_repeat,
            volume=round(entry.volume * 100),
        )
        player.track_changed.connect(
            lambda audio_file_id, eid=entry.id: self._update_playlist_entry_now_playing(
                eid, audio_file_id
            )
        )
        player.position_changed.connect(
            lambda position_ms, eid=entry.id: self._update_playlist_entry_position(
                eid, position_ms
            )
        )
        player.playback_finished.connect(
            lambda eid=entry.id: self._on_playlist_entry_finished(eid)
        )
        self._playlist_players[entry.id] = player
        player.start(fade_ms)

    def _update_playlist_entry_now_playing(self, entry_id: int, audio_file_id: int):
        """Update the now-playing display for a playlist entry control."""
        control = self._playlist_entry_controls.get(entry_id)
        if not control or not self._current_scene:
            return
        # A new track is starting: zero the scrubber (the next position tick
        # repopulates it once the new track reports its length).
        control.reset_position()
        # Look up audio file title from the playlist's tracks
        entry = next(
            (e for e in self._current_scene.playlist_entries if e.id == entry_id),
            None,
        )
        if entry and entry.playlist and entry.playlist.tracks:
            for track in entry.playlist.tracks:
                if track.audio_file_id == audio_file_id and track.audio_file:
                    control.set_current_track(track.audio_file.display_title)
                    return
        control.set_current_track("")

    def _update_playlist_entry_position(self, entry_id: int, position_ms: int):
        """Forward the active player's position to the entry's scrubber."""
        control = self._playlist_entry_controls.get(entry_id)
        player = self._playlist_players.get(entry_id)
        if control and player:
            control.update_position(position_ms, player.get_duration())

    def _on_playlist_entry_next(self, entry_id: int):
        """Skip to the next track in a playing playlist entry."""
        player = self._playlist_players.get(entry_id)
        if player:
            player.next_track()

    def _on_playlist_entry_seek(self, entry_id: int, fraction: float):
        """Seek within the entry's current track (fraction is 0..1)."""
        player = self._playlist_players.get(entry_id)
        if player:
            duration = player.get_duration()
            if duration > 0:
                player.set_position(int(fraction * duration))

    def _on_playlist_entry_finished(self, entry_id: int):
        """Handle playlist entry playback finished (no repeat)."""
        control = self._playlist_entry_controls.get(entry_id)
        if control:
            control.set_current_track("")
            control.reset_position()
        # Drop the spent player. Its inner TrackPlayer is already released, so a
        # cached reference would make a later resume() a silent no-op; clearing
        # it means the next play starts the entry fresh from the top.
        player = self._playlist_players.pop(entry_id, None)
        if player:
            player.release()

    def _stop_all_playlist_players(self):
        """Stop and release all scene playlist players."""
        for player in self._playlist_players.values():
            player.release()
        self._playlist_players.clear()
        # Clear now-playing labels and scrubbers
        for control in self._playlist_entry_controls.values():
            control.set_current_track("")
            control.reset_position()

    def _remove_track(self, track_id: int):
        """Remove a track from the scene"""
        # Stop player
        self.mixer.remove_track(track_id)

        # Remove from database
        self.db.remove_track_from_scene(track_id)

        # Refresh display
        self._refresh_tracks()
        self._persist_track_order()
        self.scene_modified.emit()

    def _on_track_volume_changed(self, track_id: int, volume: float):
        """Live volume update during slider movement.

        Updates the running audio only. Persistence is deferred to
        _on_track_volume_committed (slider release / discrete change) so a drag
        is a single DB write rather than one per tick.
        """
        self.mixer.set_track_volume(track_id, round(volume * 100))

    def _on_track_volume_committed(self, track_id: int, volume: float):
        """Persist a track's volume once the user settles."""
        self.db.update_scene_track_setting(track_id, volume=volume)

    def _on_track_repeat_changed(self, track_id: int, is_repeat: bool):
        """Handle track repeat change"""
        self.mixer.set_track_repeat(track_id, is_repeat)
        self.db.update_scene_track_setting(track_id, is_repeat=is_repeat)

    def _on_track_play_mode_changed(self, track_id: int, play_mode: bool):
        """Handle track play mode change"""
        if not self._current_scene:
            return

        self.db.update_scene_track_setting(track_id, play_mode=play_mode)

        if self._is_current_scene_active() and self._scene_playing:
            self._apply_track_play_mode(track_id, play_mode)

    def _on_tracks_reordered(self, track_ids: list[int]):
        if not self._current_scene or not track_ids:
            return
        self._persist_track_order(track_ids)
        self.scene_modified.emit()

    # --- Presets ---

    def _sync_preset_buttons(self):
        """Reflect names + the active slot on the three preset buttons."""
        names = self._current_scene.preset_names if self._current_scene else {}
        for slot, btn in self._preset_buttons.items():
            btn.setText(names.get(slot) or f"Preset {slot}")
            btn.setChecked(slot == self._preset_slot)
            btn.setStyleSheet(
                Styles.toggle_on_style()
                if slot == self._preset_slot
                else Styles.toggle_off_style()
            )

    def _on_preset_clicked(self, slot: int):
        if not self._current_scene:
            return
        if slot == self._preset_slot:
            # Clicking the checked button unchecks it visually; re-assert.
            self._sync_preset_buttons()
            return
        self._switch_preset(slot)

    def _show_preset_menu(self, slot: int, pos):
        """Right-click menu for a preset button.

        The modal rename dialog must NOT open directly inside the
        context-menu signal (mid right-press): re-entering the event loop
        there can leave the mouse grab stuck on the button and deaden the
        whole window. Routing through a QMenu popup first — the pattern the
        rest of the app uses — releases the grab before the dialog opens.
        """
        if not self._current_scene:
            return
        btn = self._preset_buttons[slot]
        menu = QMenu(btn)
        rename_action = menu.addAction("Rename Preset…")
        assert rename_action is not None
        rename_action.triggered.connect(lambda: self._rename_preset(slot))
        menu.exec(btn.mapToGlobal(pos))

    def _rename_preset(self, slot: int):
        if not self._current_scene or self._current_scene.id is None:
            return
        current = self._current_scene.preset_names.get(slot) or f"Preset {slot}"
        dialog = TextInputDialog(
            self, title="Rename Preset", label="Preset name:", default=current
        )
        if dialog.exec():
            name = dialog.get_text()
            if name and name != current:
                self.db.rename_scene_preset(self._current_scene.id, slot, name)
                self._current_scene.preset_names[slot] = name
                self._sync_preset_buttons()

    def _switch_preset(self, slot: int):
        """Activate a preset: persist the slot, swap every card's state to
        the preset's settings, and transition live playback smoothly."""
        if not self._current_scene or self._current_scene.id is None:
            return
        scene_id = self._current_scene.id
        self.db.set_active_preset_slot(scene_id, slot)
        self._preset_slot = slot
        self._current_scene.active_preset_slot = slot
        self._sync_preset_buttons()

        new_tracks = {t.id: t for t in self.db.get_scene_tracks(scene_id, slot=slot)}
        new_entries = {
            e.id: e for e in self.db.get_scene_playlist_entries(scene_id, slot=slot)
        }

        live = self._is_current_scene_active() and self._scene_playing
        paused = self._is_current_scene_active() and not self._scene_playing

        for track in self._current_scene.tracks:
            new = new_tracks.get(track.id)
            if not new:
                continue
            was_on = track.play_mode
            control = self._track_controls.get(track.id) if track.id else None
            if control:
                # control._model IS this track object, so the silent setters
                # keep the in-memory scene in sync too.
                control.set_volume(new.volume)
                control.set_repeat(new.is_repeat)
                control.set_play_mode(new.play_mode)
            else:
                track.volume = new.volume
                track.is_repeat = new.is_repeat
                track.play_mode = new.play_mode

            if live and track.id is not None:
                player = self.mixer.get_player(track.id)
                if new.play_mode and was_on and player:
                    player.repeat = new.is_repeat
                    player.fade_to_volume(round(new.volume * 100), PRESET_FADE_MS)
                elif new.play_mode and not was_on:
                    self._play_track(track, fade_ms=PRESET_FADE_MS)
                elif not new.play_mode and player:
                    player.fade_out(PRESET_FADE_MS, pause_after=True)
            elif paused and track.id is not None:
                # Silent players: snap settings so resume uses the new preset.
                player = self.mixer.get_player(track.id)
                if player:
                    player.target_volume = round(new.volume * 100)
                    player.repeat = new.is_repeat

        for entry in self._current_scene.playlist_entries:
            new_entry = new_entries.get(entry.id)
            if not new_entry:
                continue
            was_on = entry.play_mode
            entry_control = (
                self._playlist_entry_controls.get(entry.id) if entry.id else None
            )
            if entry_control:
                entry_control.set_volume(new_entry.volume)
                entry_control.set_repeat(new_entry.is_repeat)
                entry_control.set_shuffle(new_entry.is_shuffle)
                entry_control.set_play_mode(new_entry.play_mode)
            else:
                entry.volume = new_entry.volume
                entry.is_repeat = new_entry.is_repeat
                entry.is_shuffle = new_entry.is_shuffle
                entry.play_mode = new_entry.play_mode

            entry_player = self._playlist_players.get(entry.id) if entry.id else None
            if entry_player:
                entry_player.set_shuffle(new_entry.is_shuffle)
                entry_player.set_repeat(new_entry.is_repeat)
            if live:
                if new_entry.play_mode and was_on and entry_player:
                    entry_player.fade_to_volume(
                        round(new_entry.volume * 100), PRESET_FADE_MS
                    )
                elif new_entry.play_mode and not was_on:
                    if entry_player:
                        entry_player.set_volume(round(new_entry.volume * 100))
                        entry_player.resume(PRESET_FADE_MS)
                    else:
                        self._start_playlist_entry(entry, fade_ms=PRESET_FADE_MS)
                elif not new_entry.play_mode and entry_player:
                    entry_player.pause(PRESET_FADE_MS)
            elif paused and entry_player:
                entry_player.set_volume(round(new_entry.volume * 100))

        _log.info("preset_switched", scene_id=scene_id, slot=slot, live=live)

    # Public entry points for the application keyboard shortcuts (MainWindow).
    # They wrap the private play/pause logic so MainWindow needn't reach into
    # editor internals.

    def toggle_playback(self) -> None:
        """Play/pause the open scene (Space, when this tab is focused)."""
        self._toggle_scene_play()

    def pause_active(self) -> None:
        """Pause the playing scene, regardless of which one is open."""
        if self._scene_playing:
            self._pause_scene_playback()

    def play_current(self) -> None:
        """Start the open scene unless it is already the one playing."""
        if self._current_scene and not (
            self._is_current_scene_active() and self._scene_playing
        ):
            self._start_scene_playback()

    def active_playback(self) -> tuple[int, bool] | None:
        """(scene_id, is_playing) of the scene that owns playback, or None.

        The active scene is independent of the one open in the editor: it is
        set when playback starts and survives pause (paused = active with
        is_playing False), so browsing the sidebar doesn't affect it.
        """
        if self._active_scene_id is None:
            return None
        return (self._active_scene_id, self._scene_playing)

    def _toggle_scene_play(self):
        """Toggle scene play/pause"""
        if not self._current_scene:
            return

        if not self._is_current_scene_active():
            self._start_scene_playback()
            return

        if self._scene_playing:
            self._pause_scene_playback()
        else:
            self._start_scene_playback()

    def _start_scene_playback(self):
        """Start playback for all tracks in play mode and playlist entries"""
        if not self._current_scene:
            return

        self._activate_scene(self._current_scene)
        for track in self._current_scene.tracks:
            if track.play_mode:
                self._play_track(track)

        # Start or resume playlist entry players (only those in play mode)
        for entry in self._current_scene.playlist_entries:
            if entry.play_mode:
                existing = self._playlist_players.get(entry.id)
                if existing:
                    existing.resume(500)
                else:
                    self._start_playlist_entry(entry)

        self._scene_playing = True
        self._sync_scene_play_button()
        self.playback_state_changed.emit(
            self._active_scene_id, self._active_scene_title, True
        )

    def _pause_scene_playback(self):
        """Pause all currently playing tracks and playlist entries"""
        self.mixer.pause_all(1000)
        for player in self._playlist_players.values():
            player.pause(1000)
        self._scene_playing = False
        self._sync_scene_play_button()
        self.playback_state_changed.emit(
            self._active_scene_id, self._active_scene_title, False
        )

    def _play_track(self, track: SceneAudioFile, fade_ms: int = 500):
        """Ensure a track has a player and start playback"""
        assert track.id is not None
        if not track.audio_file:
            return
        if not os.path.exists(track.audio_file.file_path):
            _log.warning(
                "audio_file_missing",
                audio_file_id=track.audio_file.id,
                file_path=track.audio_file.file_path,
            )
            return

        player = self.mixer.get_player(track.id)
        if not player:
            player = self.mixer.add_track(track.id, track.audio_file.file_path)
        player.target_volume = round(track.volume * 100)
        player.repeat = track.is_repeat
        control = self._track_controls.get(track.id)
        if control and control.player is not player:
            control.set_player(player)
        player.fade_in(fade_ms)

    def _apply_track_play_mode(self, track_id: int, play_mode: bool):
        """Start or pause a track based on play mode"""
        if not self._current_scene:
            return
        if play_mode:
            track = next(
                (t for t in self._current_scene.tracks if t.id == track_id),
                None,
            )
            if track:
                self._play_track(track)
        else:
            player = self.mixer.get_player(track_id)
            if player:
                player.fade_out(500, pause_after=True)

    def _activate_scene(self, scene: Scene):
        """Set the active scene for playback, stopping any prior scene"""
        if self._active_scene_id is not None and self._active_scene_id != scene.id:
            self._stop_active_scene()

        self._active_scene_id = scene.id
        self._active_scene_title = scene.title

    def _stop_active_scene(self):
        """Stop playback and clear the active scene"""
        was_active = self._active_scene_id is not None
        self.mixer.stop_all()
        self.mixer.clear()
        self._stop_all_playlist_players()
        self._scene_playing = False
        self._active_scene_id = None
        self._active_scene_title = None
        if was_active:
            # Emitting only when a scene was actually active (playing OR
            # paused) lets callers invoke this unconditionally without
            # broadcasting spurious idle states to remote clients.
            self.playback_state_changed.emit(None, None, False)
        self._sync_scene_play_button()

    def _is_current_scene_active(self) -> bool:
        return bool(
            self._current_scene and self._current_scene.id == self._active_scene_id
        )

    def _sync_scene_play_button(self):
        """Sync play button with current scene playback state"""
        is_playing = self._is_current_scene_active() and self._scene_playing
        if is_playing:
            self.play_toggle_btn.setText("Pause")
            self.play_toggle_btn.setIcon(self._icons.icon("pause"))
        else:
            self.play_toggle_btn.setText("Play")
            self.play_toggle_btn.setIcon(self._icons.icon("play"))
        self.play_toggle_btn.setStyleSheet(
            Styles.playback_button_style(is_active=is_playing)
        )

    def stop_all(self):
        """Stop all playback immediately"""
        self._stop_active_scene()

    def clear(self):
        """Clear the editor"""
        if self._is_current_scene_active():
            self._stop_active_scene()
        self._track_controls.clear()
        self._playlist_entry_controls.clear()
        self._current_scene = None
        self.title_label.setText("Select a scene")
        self.add_tracks_btn.setEnabled(False)
        self.add_playlist_btn.setEnabled(False)
        self.play_toggle_btn.setEnabled(False)
        self._sync_scene_play_button()
        self._preset_slot = 1
        for btn in self._preset_buttons.values():
            btn.setEnabled(False)
        self._sync_preset_buttons()
        self.empty_label.hide()
        self.scroll_area.hide()

        # Clear track and playlist entry controls
        clear_layout(self.tracks_layout)
        self.tracks_container.clear_registry()

    def refresh(self):
        """Refresh the current scene"""
        if self._current_scene:
            scene = self.db.get_scene(self._current_scene.id)
            if scene:
                self.load_scene(scene)

    def _persist_track_order(self, track_ids: list[int] | None = None):
        if not self._current_scene:
            return
        if track_ids is None:
            track_ids = self.tracks_container.track_ids_in_order()
        if not track_ids:
            return
        assert self._current_scene.id is not None
        self.db.reorder_tracks(self._current_scene.id, track_ids)
        track_by_id = {track.id: track for track in self._current_scene.tracks}
        new_tracks = []
        for position, track_id in enumerate(track_ids):
            track = track_by_id.get(track_id)
            if track:
                track.position = position
                new_tracks.append(track)
        self._current_scene.tracks = new_tracks


class TrackListContainer(QWidget):
    """Container for draggable track controls"""

    order_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._track_widgets: dict[int, TrackControl] = {}

    def register_track(self, track_id: int, widget: TrackControl):
        self._track_widgets[track_id] = widget

    def clear_registry(self):
        self._track_widgets.clear()

    def track_ids_in_order(self) -> list[int]:
        layout = self.layout()
        if not layout:
            return []
        track_ids: list[int] = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget() if item else None
            if isinstance(widget, TrackControl) and widget.track.id is not None:
                track_ids.append(widget.track.id)
        return track_ids

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-soundmanager-track"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-soundmanager-track"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat("application/x-soundmanager-track"):
            return

        data = bytes(event.mimeData().data("application/x-soundmanager-track"))
        try:
            track_id = int(data.decode())
        except ValueError:
            return

        widget = self._track_widgets.get(track_id)
        if not widget:
            return

        layout = self.layout()
        if not layout:
            return

        insert_index = self._index_for_y(event.position().y())
        current_index = layout.indexOf(widget)
        if current_index == -1:
            return
        if insert_index > current_index:
            insert_index -= 1
        layout.removeWidget(widget)
        layout.insertWidget(insert_index, widget)
        event.acceptProposedAction()
        self.order_changed.emit(self.track_ids_in_order())

    def _index_for_y(self, y: float) -> int:
        layout = self.layout()
        if not layout:
            return 0
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget() if item else None
            if not isinstance(widget, TrackControl):
                continue
            midpoint = widget.y() + (widget.height() / 2)
            if y < midpoint:
                return i
        return layout.count()
