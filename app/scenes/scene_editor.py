"""Scene editor for managing tracks in a scene"""

import os
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QDialog, QLineEdit
)
from PyQt6.QtCore import pyqtSignal, Qt, QSize

from ..database import DatabaseConnection, Scene, SceneAudioFile, ScenePlaylistEntry, AudioFile
from ..audio import AudioEngine, SceneMixer, TrackPlayer, ScenePlaylistPlayer
from ..library import TagManager
from ..shared.styles import Styles
from ..shared.icons import IconLibrary
from .track_control import TrackControl
from .playlist_entry_control import PlaylistEntryControl


class AudioFileSearchDialog(QDialog):
    """Dialog for searching and selecting audio files to add to a scene"""

    def __init__(self, db: DatabaseConnection, audio_engine: AudioEngine,
                 disabled_track_ids: Optional[set[int]] = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.audio_engine = audio_engine
        self.selected_files: list[AudioFile] = []
        self._disabled_track_ids: set[int] = disabled_track_ids or set()
        self._preview_player: Optional[TrackPlayer] = None
        self._preview_file_id: Optional[int] = None
        self._preview_item: Optional["FileSelectItem"] = None

        self.setWindowTitle("Add Audio Files")
        self.setMinimumSize(500, 400)
        self._setup_ui()
        self._load_files()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Search bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by title or artist...")
        self.search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # Tag filter
        self.tag_manager = TagManager(
            self.db,
            allow_manage=False,
            header_text="Filter by tags",
        )
        self.tag_manager.tag_filter_changed.connect(self._on_tag_filter)
        layout.addWidget(self.tag_manager)

        # File list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.files_container = QWidget()
        self.files_layout = QVBoxLayout(self.files_container)
        self.files_layout.setContentsMargins(0, 0, 0, 0)
        self.files_layout.setSpacing(4)
        self.files_layout.addStretch()

        scroll.setWidget(self.files_container)
        layout.addWidget(scroll)

        # Selected count
        self.selected_label = QLabel("0 files selected")
        self.selected_label.setStyleSheet(f"color: {Styles.TEXT_MUTED};")
        layout.addWidget(self.selected_label)

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

    def _load_files(self, query: str = ""):
        """Load files from database"""
        # Clear existing
        while self.files_layout.count() > 1:  # Keep stretch
            item = self.files_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Load files
        tag_ids = self.tag_manager.get_selected_tag_ids()
        if query or tag_ids:
            files = self.db.search_audio_files(query, tag_ids if tag_ids else None)
        else:
            files = self.db.get_all_audio_files()

        if self._preview_file_id and self._preview_file_id not in {f.id for f in files}:
            self._stop_preview()

        for file in files:
            disabled = file.id in self._disabled_track_ids
            item = FileSelectItem(file, disabled=disabled)
            item.selection_changed.connect(self._on_selection_changed)
            item.preview_requested.connect(self._on_preview_requested)
            # Check if already selected
            if not disabled and file.id in [f.id for f in self.selected_files]:
                item.set_selected(True)
            if self._preview_file_id == file.id:
                self._preview_item = item
                item.set_preview_playing(True)
            self.files_layout.insertWidget(self.files_layout.count() - 1, item)

    def _on_search(self, query: str):
        """Handle search"""
        self._load_files(query)

    def _on_tag_filter(self, tag_ids: list[int]):
        """Handle tag filter change"""
        self._load_files(self.search_input.text())

    def _on_selection_changed(self, file: AudioFile, selected: bool):
        """Handle file selection change"""
        if selected:
            if file not in self.selected_files:
                self.selected_files.append(file)
        else:
            self.selected_files = [f for f in self.selected_files if f.id != file.id]

        count = len(self.selected_files)
        self.selected_label.setText(f"{count} file{'s' if count != 1 else ''} selected")
        self.add_btn.setEnabled(count > 0)

    def get_selected_files(self) -> list[AudioFile]:
        """Get selected files"""
        return self.selected_files

    def _on_preview_requested(self, file: AudioFile, item: "FileSelectItem"):
        """Toggle preview playback for a file"""
        if self._preview_player:
            self._preview_player.fade_out(300)
            self._preview_player.release()
            self._preview_player = None
            if self._preview_item:
                self._preview_item.set_preview_playing(False)
            if self._preview_file_id == file.id:
                self._preview_file_id = None
                self._preview_item = None
                return

        if os.path.exists(file.file_path):
            self._preview_player = TrackPlayer(file.file_path, self.audio_engine)
            self._preview_player.end_reached.connect(self._on_preview_ended)
            self._preview_player.fade_in(300)
            self._preview_file_id = file.id
            self._preview_item = item
            item.set_preview_playing(True)

    def _on_preview_ended(self):
        """Handle preview playback ended"""
        if self._preview_item:
            self._preview_item.set_preview_playing(False)
        if self._preview_player:
            self._preview_player.release()
        self._preview_player = None
        self._preview_file_id = None
        self._preview_item = None

    def _stop_preview(self):
        """Stop any active preview playback"""
        if self._preview_player:
            self._preview_player.stop()
            self._preview_player.release()
            self._preview_player = None
        if self._preview_item:
            self._preview_item.set_preview_playing(False)
        self._preview_file_id = None
        self._preview_item = None

    def accept(self):
        self._stop_preview()
        super().accept()

    def reject(self):
        self._stop_preview()
        super().reject()


class FileSelectItem(QFrame):
    """Selectable file item in search dialog"""

    selection_changed = pyqtSignal(AudioFile, bool)
    preview_requested = pyqtSignal(AudioFile, object)

    def __init__(self, file: AudioFile, disabled: bool = False, parent=None):
        super().__init__(parent)
        self.file = file
        self._selected = False
        self._disabled = disabled
        self._preview_playing = False
        self._icons = IconLibrary()

        self.setFrameStyle(QFrame.Shape.StyledPanel)
        if not disabled:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Title and artist
        info_layout = QVBoxLayout()
        title_label = QLabel(file.display_title)
        text_color = Styles.TEXT_MUTED if disabled else ""
        title_label.setStyleSheet(f"font-weight: bold; color: {text_color};" if disabled else "font-weight: bold;")
        info_layout.addWidget(title_label)

        if file.artist:
            artist_label = QLabel(file.artist)
            artist_label.setStyleSheet(f"color: {Styles.TEXT_MUTED}; font-size: 11px;")
            info_layout.addWidget(artist_label)

        layout.addLayout(info_layout, 1)

        # "Already added" label for disabled items
        if disabled:
            added_label = QLabel("Already added")
            added_label.setStyleSheet(f"color: {Styles.TEXT_MUTED}; font-size: 11px; font-style: italic;")
            layout.addWidget(added_label)

        # Duration
        duration_label = QLabel(file.duration_formatted)
        duration_label.setStyleSheet(f"color: {Styles.TEXT_MUTED};")
        layout.addWidget(duration_label)

        # Preview button
        self.preview_btn = QPushButton()
        self.preview_btn.setFixedSize(16, 16)
        self.preview_btn.setIcon(self._icons.icon("play-solid"))
        self.preview_btn.setIconSize(QSize(12, 12))
        self.preview_btn.setStyleSheet(Styles.small_play_button_style())
        self.preview_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.preview_btn.clicked.connect(self._on_preview_clicked)
        layout.addWidget(self.preview_btn)

    def _update_style(self):
        """Update visual style based on selection and disabled state"""
        if self._disabled:
            self.setStyleSheet(f"""
                FileSelectItem {{
                    background-color: {Styles.BACKGROUND};
                    border: 1px solid {Styles.BORDER};
                    border-radius: 4px;
                    opacity: 0.5;
                }}
            """)
        elif self._selected:
            self.setStyleSheet(f"""
                FileSelectItem {{
                    background-color: {Styles.PRIMARY};
                    border: 1px solid {Styles.PRIMARY};
                    border-radius: 4px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                FileSelectItem {{
                    background-color: {Styles.BACKGROUND_LIGHT};
                    border: 1px solid {Styles.BORDER};
                    border-radius: 4px;
                }}
                FileSelectItem:hover {{
                    background-color: {Styles.BACKGROUND_LIGHTER};
                }}
            """)

    def set_selected(self, selected: bool):
        """Set selection state"""
        self._selected = selected
        self._update_style()

    def set_preview_playing(self, playing: bool):
        """Update preview button appearance"""
        self._preview_playing = playing
        if playing:
            self.preview_btn.setIcon(self._icons.icon("pause-solid"))
            self.preview_btn.setIconSize(QSize(12, 12))
            self.preview_btn.setStyleSheet(Styles.small_stop_button_style())
        else:
            self.preview_btn.setIcon(self._icons.icon("play-solid"))
            self.preview_btn.setIconSize(QSize(12, 12))
            self.preview_btn.setStyleSheet(Styles.small_play_button_style())

    def _on_preview_clicked(self):
        """Handle preview click"""
        self.preview_requested.emit(self.file, self)

    def mousePressEvent(self, event):
        """Handle click - disabled items cannot be selected"""
        if self._disabled:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._selected = not self._selected
            self._update_style()
            self.selection_changed.emit(self.file, self._selected)


class SceneEditor(QWidget):
    """Editor for a single scene's tracks"""

    scene_modified = pyqtSignal()
    playback_state_changed = pyqtSignal(object, object, bool)  # scene_id, scene_title, is_playing

    def __init__(self, db: DatabaseConnection, audio_engine: AudioEngine, parent=None):
        super().__init__(parent)
        self.db = db
        self.audio_engine = audio_engine
        self.mixer = SceneMixer(audio_engine)
        self._active_scene_id: Optional[int] = None
        self._active_scene_title: Optional[str] = None
        self._scene_playing = False
        self._current_scene: Optional[Scene] = None
        self._track_controls: dict[int, TrackControl] = {}
        self._playlist_entry_controls: dict[int, PlaylistEntryControl] = {}
        self._playlist_players: dict[int, ScenePlaylistPlayer] = {}  # entry_id -> player
        self._icons = IconLibrary()

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header with scene title and master controls
        header = QHBoxLayout()

        self.title_label = QLabel("Select a scene")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 18px;")
        header.addWidget(self.title_label)

        header.addStretch()

        # Master controls
        self.play_toggle_btn = QPushButton("Play")
        self.play_toggle_btn.setIcon(self._icons.icon("play"))
        self.play_toggle_btn.setIconSize(QSize(16, 16))
        self.play_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Styles.SUCCESS};
                padding: 10px 20px;
            }}
            QPushButton:hover {{
                background-color: #218838;
            }}
        """)
        self.play_toggle_btn.clicked.connect(self._toggle_scene_play)
        self.play_toggle_btn.setEnabled(False)
        header.addWidget(self.play_toggle_btn)

        layout.addLayout(header)

        # Add tracks / playlist buttons
        add_layout = QHBoxLayout()
        self.add_tracks_btn = QPushButton("+ Add Tracks")
        self.add_tracks_btn.clicked.connect(self._add_tracks)
        self.add_tracks_btn.setEnabled(False)
        add_layout.addWidget(self.add_tracks_btn)

        self.add_playlist_btn = QPushButton("+ Add Playlist")
        self.add_playlist_btn.clicked.connect(self._add_playlist_entry)
        self.add_playlist_btn.setEnabled(False)
        add_layout.addWidget(self.add_playlist_btn)

        add_layout.addStretch()
        layout.addLayout(add_layout)

        # Tracks scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.tracks_container = TrackListContainer()
        self.tracks_container.order_changed.connect(self._on_tracks_reordered)
        self.tracks_layout = QVBoxLayout(self.tracks_container)
        self.tracks_layout.setContentsMargins(0, 8, 0, 0)
        self.tracks_layout.setSpacing(8)

        scroll.setWidget(self.tracks_container)
        layout.addWidget(scroll)

        # Empty state
        self.empty_label = QLabel("No tracks in this scene.\nClick '+ Add Tracks' or '+ Add Playlist' to get started.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {Styles.TEXT_MUTED}; padding: 40px;")
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

        # Load tracks and playlist entries
        self._refresh_tracks()

    def _refresh_tracks(self):
        """Refresh track and playlist entry display"""
        if not self._current_scene:
            return

        # Clear existing track controls and playlist entry controls
        while self.tracks_layout.count() > 0:
            item = self.tracks_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
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
        else:
            self.empty_label.hide()

            is_active_scene = self._is_current_scene_active()
            for track in scene.tracks:
                self._add_track_control(track, is_active_scene)

            # Add playlist entries below audio tracks
            for entry in scene.playlist_entries:
                self._add_playlist_entry_control(entry)

    def _add_track_control(self, track: SceneAudioFile, use_active_players: bool):
        """Add a track control widget"""
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
                    player.target_volume = int(track.volume * 100)
                    player.repeat = track.is_repeat
                    if created_player and track.play_mode:
                        player.fade_in(500)

        # Create control widget
        control = TrackControl(track, player)
        control.volume_changed.connect(self._on_track_volume_changed)
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
            self.db, self.audio_engine,
            disabled_track_ids=existing_ids, parent=self,
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
        control = PlaylistEntryControl(entry)
        control.shuffle_changed.connect(self._on_playlist_entry_shuffle_changed)
        control.repeat_changed.connect(self._on_playlist_entry_repeat_changed)
        control.play_mode_changed.connect(self._on_playlist_entry_play_mode_changed)
        control.remove_requested.connect(self._remove_playlist_entry)

        self._playlist_entry_controls[entry.id] = control
        self.tracks_layout.addWidget(control)

    def _add_playlist_entry(self):
        """Show dialog to add a playlist to the scene"""
        if not self._current_scene:
            return

        from .playlist_picker_dialog import PlaylistPickerDialog

        existing_playlist_ids = {e.playlist_id for e in self._current_scene.playlist_entries}
        dialog = PlaylistPickerDialog(
            self.db,
            disabled_playlist_ids=existing_playlist_ids,
            parent=self,
        )
        if dialog.exec():
            playlist = dialog.get_selected_playlist()
            if playlist:
                position = len(self._current_scene.playlist_entries)
                self.db.add_playlist_to_scene(self._current_scene.id, playlist.id, position)
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

    def _on_playlist_entry_shuffle_changed(self, entry_id: int, is_shuffle: bool):
        """Handle playlist entry shuffle toggle change"""
        if not self._current_scene:
            return
        for entry in self._current_scene.playlist_entries:
            if entry.id == entry_id:
                entry.is_shuffle = is_shuffle
                self.db.update_scene_playlist_entry(entry)
                break
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
                self.db.update_scene_playlist_entry(entry)
                break
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
                self.db.update_scene_playlist_entry(entry)
                break

        if self._is_current_scene_active() and self._scene_playing:
            self._apply_playlist_entry_play_mode(entry_id, play_mode)

    def _apply_playlist_entry_play_mode(self, entry_id: int, play_mode: bool):
        """Start or pause a playlist entry based on play mode"""
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

    def _start_playlist_entry(self, entry: ScenePlaylistEntry):
        """Create and start a ScenePlaylistPlayer for a playlist entry."""
        player = ScenePlaylistPlayer(
            playlist_id=entry.playlist_id,
            db=self.db,
            engine=self.audio_engine,
            is_shuffle=entry.is_shuffle,
            is_repeat=entry.is_repeat,
        )
        self._playlist_players[entry.id] = player
        player.start(500)

    def _stop_all_playlist_players(self):
        """Stop and release all scene playlist players."""
        for player in self._playlist_players.values():
            player.release()
        self._playlist_players.clear()

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
        """Handle track volume change"""
        # Update in mixer
        self.mixer.set_track_volume(track_id, int(volume * 100))

        # Save to database
        tracks = self.db.get_scene_tracks(self._current_scene.id)
        for track in tracks:
            if track.id == track_id:
                track.volume = volume
                self.db.update_track_settings(track)
                break

    def _on_track_repeat_changed(self, track_id: int, is_repeat: bool):
        """Handle track repeat change"""
        # Update in mixer
        self.mixer.set_track_repeat(track_id, is_repeat)

        # Save to database
        tracks = self.db.get_scene_tracks(self._current_scene.id)
        for track in tracks:
            if track.id == track_id:
                track.is_repeat = is_repeat
                self.db.update_track_settings(track)
                break

    def _on_track_play_mode_changed(self, track_id: int, play_mode: bool):
        """Handle track play mode change"""
        if not self._current_scene:
            return

        tracks = self.db.get_scene_tracks(self._current_scene.id)
        for track in tracks:
            if track.id == track_id:
                track.play_mode = play_mode
                self.db.update_track_settings(track)
                break

        if self._is_current_scene_active() and self._scene_playing:
            self._apply_track_play_mode(track_id, play_mode)

    def _on_tracks_reordered(self, track_ids: list[int]):
        if not self._current_scene or not track_ids:
            return
        self._persist_track_order(track_ids)
        self.scene_modified.emit()

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
        self.playback_state_changed.emit(self._active_scene_id, self._active_scene_title, True)

    def _pause_scene_playback(self):
        """Pause all currently playing tracks and playlist entries"""
        self.mixer.pause_all(1000)
        for player in self._playlist_players.values():
            player.pause(1000)
        self._scene_playing = False
        self._sync_scene_play_button()
        self.playback_state_changed.emit(self._active_scene_id, self._active_scene_title, False)

    def _play_track(self, track: SceneAudioFile):
        """Ensure a track has a player and start playback"""
        if not track.audio_file:
            return
        import os
        if not os.path.exists(track.audio_file.file_path):
            return

        player = self.mixer.get_player(track.id)
        if not player:
            player = self.mixer.add_track(track.id, track.audio_file.file_path)
        player.target_volume = int(track.volume * 100)
        player.repeat = track.is_repeat
        control = self._track_controls.get(track.id)
        if control and control.player is not player:
            control.set_player(player)
        player.fade_in(500)

    def _apply_track_play_mode(self, track_id: int, play_mode: bool):
        """Start or pause a track based on play mode"""
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
        self.mixer.stop_all()
        self.mixer.clear()
        self._stop_all_playlist_players()
        self._scene_playing = False
        self._active_scene_id = None
        self._active_scene_title = None
        self.playback_state_changed.emit(None, None, False)
        self._sync_scene_play_button()

    def _is_current_scene_active(self) -> bool:
        return bool(self._current_scene and self._current_scene.id == self._active_scene_id)

    def _sync_scene_play_button(self):
        """Sync play button with current scene playback state"""
        is_playing = self._is_current_scene_active() and self._scene_playing
        if is_playing:
            self.play_toggle_btn.setText("Pause")
            self.play_toggle_btn.setIcon(self._icons.icon("pause"))
            self.play_toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Styles.WARNING};
                    color: #000;
                    padding: 10px 20px;
                }}
                QPushButton:hover {{
                    background-color: #E0A800;
                }}
            """)
        else:
            self.play_toggle_btn.setText("Play")
            self.play_toggle_btn.setIcon(self._icons.icon("play"))
            self.play_toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Styles.SUCCESS};
                    padding: 10px 20px;
                }}
                QPushButton:hover {{
                    background-color: #218838;
                }}
            """)

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

        # Clear track and playlist entry controls
        while self.tracks_layout.count() > 0:
            item = self.tracks_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.tracks_container.clear_registry()

    def refresh(self):
        """Refresh the current scene"""
        if self._current_scene:
            scene = self.db.get_scene(self._current_scene.id)
            if scene:
                self.load_scene(scene)

    def _persist_track_order(self, track_ids: Optional[list[int]] = None):
        if not self._current_scene:
            return
        if track_ids is None:
            track_ids = self.tracks_container.track_ids_in_order()
        if not track_ids:
            return
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
            widget = item.widget()
            if isinstance(widget, TrackControl):
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
            widget = item.widget()
            if not isinstance(widget, TrackControl):
                continue
            midpoint = widget.y() + (widget.height() / 2)
            if y < midpoint:
                return i
        return layout.count()
