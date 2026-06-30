"""Playlist editor for managing tracks in a playlist"""

import os

from PyQt6.QtCore import QByteArray, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.shared.logging import get_logger

from ..audio import AudioEngine, SmartShuffle, TrackPlayer
from ..database import DatabaseConnection, Playlist, PlaylistTrack
from ..shared.icons import IconLibrary
from ..shared.layouts import clear_layout
from ..shared.styles import Styles

_log = get_logger(__name__)


class PlaylistTrackItem(QFrame):
    """Display widget for a single track in a playlist"""

    remove_requested = pyqtSignal(int)  # track_id

    def __init__(self, track: PlaylistTrack, position: int = 0, parent=None):
        super().__init__(parent)
        self.track = track
        self.position = position
        self._icons = IconLibrary()
        self._drag_start_pos = None
        self._now_playing = False

        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self._apply_style()

        self._setup_ui()

    def _apply_style(self):
        if self._now_playing:
            self.setStyleSheet(
                Styles.card_frame_style(
                    "PlaylistTrackItem",
                    accent_color=Styles.PRIMARY,
                    border_color=Styles.PRIMARY,
                    background_color=Styles.BACKGROUND_LIGHTER,
                )
            )
        else:
            self.setStyleSheet(Styles.card_frame_style("PlaylistTrackItem"))

    def set_now_playing(self, playing: bool):
        """Set now-playing highlight state"""
        self._now_playing = playing
        self._apply_style()
        # Update position label color to indicate playing
        if playing:
            self.position_label.setStyleSheet(
                f"color: {Styles.PRIMARY}; font-size: 13px; font-weight: 700;"
            )
        else:
            self.position_label.setStyleSheet(
                Styles.subtle_text_style(size=13, extra="font-weight: 700;")
            )

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Position number
        self.position_label = QLabel(str(self.position + 1))
        self.position_label.setFixedWidth(28)
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.position_label.setStyleSheet(
            Styles.subtle_text_style(size=13, extra="font-weight: 700;")
        )
        layout.addWidget(self.position_label)

        # Track info
        info_layout = QVBoxLayout()
        if self.track.audio_file:
            title_label = QLabel(self.track.audio_file.display_title)
            title_label.setStyleSheet(Styles.title_style(size=14))
            info_layout.addWidget(title_label)

            # Artist and tags row
            detail_layout = QHBoxLayout()
            detail_layout.setSpacing(6)

            if self.track.audio_file.artist:
                artist_label = QLabel(self.track.audio_file.artist)
                artist_label.setStyleSheet(Styles.subtle_text_style(size=11))
                detail_layout.addWidget(artist_label)

            # Tags
            if self.track.audio_file.tags:
                for tag in self.track.audio_file.tags:
                    tag_label = QLabel(tag.name)
                    color = tag.color or Styles.PRIMARY
                    tag_label.setStyleSheet(Styles.tag_badge_style(color))
                    detail_layout.addWidget(tag_label)

            detail_layout.addStretch()
            info_layout.addLayout(detail_layout)
        else:
            title_label = QLabel("Unknown Track")
            title_label.setStyleSheet(Styles.title_style(size=14))
            info_layout.addWidget(title_label)

        layout.addLayout(info_layout, 1)

        # Duration
        if self.track.audio_file:
            duration_label = QLabel(self.track.audio_file.duration_formatted)
            duration_label.setStyleSheet(Styles.subtle_text_style(size=12))
            layout.addWidget(duration_label)

        # Remove button
        remove_btn = QPushButton("×")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setToolTip("Remove from playlist")
        remove_btn.setStyleSheet(Styles.remove_button_style())
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.track.id))
        layout.addWidget(remove_btn)

    def update_position(self, position: int):
        """Update the displayed position number"""
        self.position = position
        self.position_label.setText(str(position + 1))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        from PyQt6.QtCore import QMimeData
        from PyQt6.QtWidgets import QApplication

        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._drag_start_pos is None:
            return
        if (
            event.position().toPoint() - self._drag_start_pos
        ).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(
            "application/x-soundmanager-playlist-track",
            QByteArray(str(self.track.id).encode()),
        )
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.setHotSpot(event.position().toPoint())
        drag.exec(Qt.DropAction.MoveAction)
        self._drag_start_pos = None

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)


class PlaylistTrackListContainer(QWidget):
    """Container for draggable playlist track items"""

    order_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._track_widgets: dict[int, PlaylistTrackItem] = {}

    def register_track(self, track_id: int, widget: PlaylistTrackItem):
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
            if isinstance(widget, PlaylistTrackItem):
                track_ids.append(widget.track.id)
        return track_ids

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-soundmanager-playlist-track"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-soundmanager-playlist-track"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat("application/x-soundmanager-playlist-track"):
            return

        data = bytes(event.mimeData().data("application/x-soundmanager-playlist-track"))
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
            if not isinstance(widget, PlaylistTrackItem):
                continue
            midpoint = widget.y() + (widget.height() / 2)
            if y < midpoint:
                return i
        return layout.count()


class PlaylistEditor(QWidget):
    """Editor for a single playlist's tracks with playback controls"""

    playlist_modified = pyqtSignal()
    playlist_renamed = pyqtSignal(int, str)  # playlist_id, new_name
    playback_state_changed = pyqtSignal(
        object, object, bool
    )  # playlist_id, playlist_name, is_playing

    def __init__(self, db: DatabaseConnection, audio_engine: AudioEngine, parent=None):
        super().__init__(parent)
        self.db = db
        self.audio_engine = audio_engine
        self._current_playlist: Playlist | None = None
        self._track_items: dict[int, PlaylistTrackItem] = {}
        self._icons = IconLibrary()

        # Playback state
        self._player: TrackPlayer | None = None
        self._shuffle = SmartShuffle()
        self._shuffle_enabled = False
        self._is_playing = False
        self._active_playlist_id: int | None = None
        self._active_playlist_name: str | None = None
        self._current_track_index: int = 0  # sequential index for non-shuffle mode
        self._current_audio_file_id: int | None = (
            None  # audio_file_id of currently playing track
        )

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Header with playlist title (clickable to edit)
        header = QHBoxLayout()
        header.setSpacing(10)

        self.title_label = QLabel("Select a playlist")
        self.title_label.setStyleSheet(Styles.title_style(size=28))
        self.title_label.mouseDoubleClickEvent = self._start_title_edit
        header.addWidget(self.title_label)

        self.title_edit = QLineEdit()
        self.title_edit.setStyleSheet(Styles.title_input_style(size=28))
        self.title_edit.editingFinished.connect(self._finish_title_edit)
        self.title_edit.hide()
        header.addWidget(self.title_edit)

        header.addStretch()

        # Playback controls
        self.shuffle_btn = QPushButton("Shuffle")
        self.shuffle_btn.setToolTip("Toggle shuffle mode")
        self.shuffle_btn.setCheckable(True)
        self.shuffle_btn.setChecked(False)
        self.shuffle_btn.clicked.connect(self._toggle_shuffle)
        self.shuffle_btn.setEnabled(False)
        self._sync_shuffle_button()
        header.addWidget(self.shuffle_btn)

        self.next_btn = QPushButton("Next")
        self.next_btn.setToolTip("Next track")
        self.next_btn.setStyleSheet(Styles.secondary_button_style(compact=True))
        self.next_btn.clicked.connect(self._next_track)
        self.next_btn.setEnabled(False)
        header.addWidget(self.next_btn)

        self.play_toggle_btn = QPushButton("Play")
        self.play_toggle_btn.setIcon(self._icons.icon("play"))
        self.play_toggle_btn.setIconSize(QSize(16, 16))
        self.play_toggle_btn.setStyleSheet(
            Styles.playback_button_style(is_active=False)
        )
        self.play_toggle_btn.clicked.connect(self._toggle_play)
        self.play_toggle_btn.setEnabled(False)
        header.addWidget(self.play_toggle_btn)

        layout.addLayout(header)

        # Add tracks button
        add_layout = QHBoxLayout()
        add_layout.setSpacing(10)
        self.add_tracks_btn = QPushButton("+ Add Tracks")
        self.add_tracks_btn.clicked.connect(self._add_tracks)
        self.add_tracks_btn.setEnabled(False)
        add_layout.addWidget(self.add_tracks_btn)
        add_layout.addStretch()
        layout.addLayout(add_layout)

        # Tracks scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.tracks_container = PlaylistTrackListContainer()
        self.tracks_container.order_changed.connect(self._on_tracks_reordered)
        self.tracks_layout = QVBoxLayout(self.tracks_container)
        self.tracks_layout.setContentsMargins(0, 8, 0, 0)
        self.tracks_layout.setSpacing(8)

        self.scroll_area.setWidget(self.tracks_container)
        layout.addWidget(self.scroll_area)
        self.scroll_area.hide()

        # Empty state
        self.empty_label = QLabel(
            "No tracks in this playlist.\nClick '+ Add Tracks' to add audio files."
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(Styles.empty_state_style())
        self.empty_label.hide()
        layout.addWidget(self.empty_label)

    def load_playlist(self, playlist: Playlist):
        """Load a playlist for editing"""
        # If switching playlists while playing a different one, keep playback going
        self._current_playlist = playlist
        self.title_label.setText(playlist.name)
        self.title_label.setToolTip("Double-click to rename")

        # Enable controls
        self.add_tracks_btn.setEnabled(True)
        has_tracks = bool(playlist.tracks)
        self.play_toggle_btn.setEnabled(has_tracks)
        self.shuffle_btn.setEnabled(has_tracks)
        self.next_btn.setEnabled(
            has_tracks and self._is_playing_this_playlist(playlist.id)
        )
        self._sync_play_button()

        # Load tracks
        self._refresh_tracks()

    def _start_title_edit(self, event):
        """Switch title label to editable line edit"""
        if not self._current_playlist:
            return
        self.title_label.hide()
        self.title_edit.setText(self._current_playlist.name)
        self.title_edit.show()
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def _finish_title_edit(self):
        """Commit the title edit"""
        self.title_edit.hide()
        self.title_label.show()

        if not self._current_playlist:
            return

        new_name = self.title_edit.text().strip()
        if not new_name or new_name == self._current_playlist.name:
            return

        self._current_playlist.name = new_name
        self.db.update_playlist(self._current_playlist)
        self.title_label.setText(new_name)
        self.playlist_renamed.emit(self._current_playlist.id, new_name)

        # Update active playlist name if this is the active one
        if self._active_playlist_id == self._current_playlist.id:
            self._active_playlist_name = new_name

    def _refresh_tracks(self):
        """Refresh track display"""
        if not self._current_playlist:
            return

        # Clear existing track items
        clear_layout(self.tracks_layout)
        self.tracks_container.clear_registry()
        self._track_items.clear()

        # Load tracks from playlist
        playlist = self.db.get_playlist(self._current_playlist.id)
        if not playlist:
            return

        self._current_playlist = playlist

        if not playlist.tracks:
            self.empty_label.show()
            self.scroll_area.hide()
        else:
            self.empty_label.hide()
            self.scroll_area.show()

            for i, track in enumerate(playlist.tracks):
                self._add_track_item(track, position=i)

        # Re-highlight now-playing track if applicable
        self._update_now_playing_highlight()

    def _add_track_item(self, track: PlaylistTrack, position: int):
        """Add a track item widget"""
        item = PlaylistTrackItem(track, position=position)
        item.remove_requested.connect(self._remove_track)

        self._track_items[track.id] = item
        self.tracks_container.register_track(track.id, item)
        self.tracks_layout.addWidget(item)

    def _add_tracks(self):
        """Show dialog to add tracks"""
        if not self._current_playlist:
            return

        from ..shared.dialogs import AudioFileSearchDialog

        existing_ids = {t.audio_file_id for t in self._current_playlist.tracks}
        dialog = AudioFileSearchDialog(
            self.db,
            self.audio_engine,
            disabled_track_ids=existing_ids,
            parent=self,
        )
        if dialog.exec():
            files = dialog.get_selected_files()
            for file in files:
                position = len(self._current_playlist.tracks)
                self.db.add_track_to_playlist(
                    self._current_playlist.id, file.id, position
                )

            self._refresh_tracks()
            self._update_shuffle_tracks()
            self.playlist_modified.emit()

    def _remove_track(self, track_id: int):
        """Remove a track from the playlist"""
        # If the currently playing track is being removed, advance first
        removed_track = None
        for t in self._current_playlist.tracks:
            if t.id == track_id:
                removed_track = t
                break

        if (
            removed_track
            and self._is_playing
            and self._active_playlist_id == self._current_playlist.id
            and self._current_audio_file_id == removed_track.audio_file_id
        ):
            # Stop current playback, will auto-advance or stop
            self._release_player()

        self.db.remove_track_from_playlist(track_id)
        self._refresh_tracks()
        self._persist_track_order()
        self._update_shuffle_tracks()

        # If no tracks left, stop playback
        if self._current_playlist and not self._current_playlist.tracks:
            if (
                self._is_playing
                and self._active_playlist_id == self._current_playlist.id
            ):
                self._stop_playback()
            self.play_toggle_btn.setEnabled(False)
            self.shuffle_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
        else:
            self.play_toggle_btn.setEnabled(True)
            self.shuffle_btn.setEnabled(True)

        self.playlist_modified.emit()

    def _on_tracks_reordered(self, track_ids: list[int]):
        if not self._current_playlist or not track_ids:
            return
        self._persist_track_order(track_ids)
        self._update_position_numbers()
        self._update_shuffle_tracks()
        self.playlist_modified.emit()

    def _update_position_numbers(self):
        """Update position labels after reorder"""
        layout = self.tracks_container.layout()
        if not layout:
            return
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if isinstance(widget, PlaylistTrackItem):
                widget.update_position(i)

    def _persist_track_order(self, track_ids: list[int] | None = None):
        if not self._current_playlist:
            return
        if track_ids is None:
            track_ids = self.tracks_container.track_ids_in_order()
        if not track_ids:
            return
        self.db.reorder_playlist_tracks(self._current_playlist.id, track_ids)

    # -- Playback controls --

    # Public entry points for the application keyboard shortcuts (MainWindow).
    # They wrap the private play/pause logic so MainWindow needn't reach into
    # editor internals.

    def toggle_playback(self) -> None:
        """Play/pause the open playlist (Space, when this tab is focused)."""
        self._toggle_play()

    def pause_active(self) -> None:
        """Pause the playing playlist, regardless of which one is open."""
        if self._is_playing:
            self._pause_playback()

    def next_track(self) -> None:
        """Advance the playing playlist to its next track (no-op otherwise)."""
        self._next_track()

    def play_current(self) -> None:
        """Start the open playlist unless it is already the one playing."""
        if self._current_playlist is None:
            return
        already_playing = (
            self._active_playlist_id == self._current_playlist.id and self._is_playing
        )
        if not already_playing:
            self._toggle_play()

    def _toggle_play(self):
        """Toggle play/pause for the current playlist"""
        if not self._current_playlist or not self._current_playlist.tracks:
            return

        if self._is_playing_this_playlist(self._current_playlist.id):
            if self._is_playing:
                self._pause_playback()
            else:
                self._resume_playback()
        else:
            self._start_playback()

    def _start_playback(self):
        """Start playing the current playlist from the beginning"""
        if not self._current_playlist or not self._current_playlist.tracks:
            return

        # Stop any previous playback
        self._stop_playback()

        self._active_playlist_id = self._current_playlist.id
        self._active_playlist_name = self._current_playlist.name
        self._current_track_index = 0

        # Initialize shuffle with audio_file_ids
        audio_file_ids = [
            t.audio_file_id for t in self._current_playlist.tracks if t.audio_file_id
        ]
        self._shuffle.update_tracks(audio_file_ids)

        # Pick first track
        if self._shuffle_enabled:
            audio_file_id = self._shuffle.next()
        else:
            audio_file_id = audio_file_ids[0] if audio_file_ids else None

        # Mark playing *before* _play_audio_file: the now-playing highlight is
        # gated on _is_playing, so setting it afterward leaves the very first
        # track un-highlighted until the next auto/manual advance.
        self._is_playing = True

        if audio_file_id is not None:
            self._play_audio_file(audio_file_id)

        self.next_btn.setEnabled(True)
        self._sync_play_button()
        self.playback_state_changed.emit(
            self._active_playlist_id, self._active_playlist_name, True
        )

    def _pause_playback(self):
        """Pause current playback"""
        if self._player:
            self._player.fade_out(500, pause_after=True)
        self._is_playing = False
        self._sync_play_button()
        self.playback_state_changed.emit(
            self._active_playlist_id, self._active_playlist_name, False
        )

    def _resume_playback(self):
        """Resume paused playback"""
        if self._player:
            self._player.fade_in(500)
        self._is_playing = True
        self._sync_play_button()
        self.playback_state_changed.emit(
            self._active_playlist_id, self._active_playlist_name, True
        )

    def _stop_playback(self):
        """Stop playback completely"""
        self._release_player()
        was_playing = self._is_playing
        self._is_playing = False
        self._current_audio_file_id = None
        old_playlist_id = self._active_playlist_id
        self._active_playlist_id = None
        self._active_playlist_name = None
        self._current_track_index = 0
        self.next_btn.setEnabled(False)
        self._update_now_playing_highlight()
        self._sync_play_button()
        if was_playing:
            self.playback_state_changed.emit(old_playlist_id, None, False)

    def _play_audio_file(self, audio_file_id: int) -> bool:
        """Play a specific audio file from the playlist. Returns True if playback started."""
        # Find the track in the current playlist
        track = None
        for t in self._current_playlist.tracks:
            if t.audio_file_id == audio_file_id:
                track = t
                break
        if not track or not track.audio_file:
            _log.warning("playlist_track_missing_data", audio_file_id=audio_file_id)
            return False

        if not os.path.exists(track.audio_file.file_path):
            _log.warning(
                "audio_file_missing",
                audio_file_id=audio_file_id,
                file_path=track.audio_file.file_path,
            )
            return False

        # Release previous player
        self._release_player()

        # Create new player
        self._player = TrackPlayer(track.audio_file.file_path, self.audio_engine)
        self._player.end_reached.connect(self._on_track_ended)
        self._player.fade_in(500)
        self._current_audio_file_id = audio_file_id

        # Update sequential index to match
        for i, t in enumerate(self._current_playlist.tracks):
            if t.audio_file_id == audio_file_id:
                self._current_track_index = i
                break

        self._update_now_playing_highlight()
        return True

    def _advance_to_next_playable(self) -> None:
        """Advance to the next playable track, skipping missing files.

        Bounded by track count to avoid infinite loops when sequential mode
        wraps around.
        """
        attempts = 0
        max_attempts = (
            len(self._current_playlist.tracks) if self._current_playlist else 0
        )
        audio_file_id = self._get_next_audio_file_id()
        while audio_file_id is not None and attempts < max_attempts:
            if self._play_audio_file(audio_file_id):
                return
            attempts += 1
            audio_file_id = self._get_next_audio_file_id()
        self._stop_playback()

    def _next_track(self):
        """Advance to the next track"""
        if not self._current_playlist or not self._current_playlist.tracks:
            return
        if not self._is_playing_this_playlist(self._current_playlist.id):
            return

        self._advance_to_next_playable()

    def _get_next_audio_file_id(self) -> int | None:
        """Get the next audio_file_id to play"""
        if not self._current_playlist or not self._current_playlist.tracks:
            return None

        if self._shuffle_enabled:
            return self._shuffle.next()
        else:
            # Sequential: advance index
            self._current_track_index += 1
            if self._current_track_index >= len(self._current_playlist.tracks):
                # Wrap around to start
                self._current_track_index = 0
            track = self._current_playlist.tracks[self._current_track_index]
            return track.audio_file_id

    def _on_track_ended(self):
        """Handle track end - auto-advance to next"""
        if not self._is_playing:
            return
        self._advance_to_next_playable()

    def _toggle_shuffle(self):
        """Toggle shuffle mode"""
        self._shuffle_enabled = self.shuffle_btn.isChecked()
        self._sync_shuffle_button()

        # If currently playing, update shuffle with remaining tracks
        if self._is_playing and self._active_playlist_id and self._current_playlist:
            audio_file_ids = [
                t.audio_file_id
                for t in self._current_playlist.tracks
                if t.audio_file_id
            ]
            self._shuffle.update_tracks(audio_file_ids)

    def _update_shuffle_tracks(self):
        """Update the SmartShuffle track list when playlist changes"""
        if self._current_playlist:
            audio_file_ids = [
                t.audio_file_id
                for t in self._current_playlist.tracks
                if t.audio_file_id
            ]
            self._shuffle.update_tracks(audio_file_ids)

    def _release_player(self):
        """Release the current track player"""
        if self._player:
            self._player.stop()
            self._player.release()
            self._player = None

    def _update_now_playing_highlight(self):
        """Update which track item is highlighted as now-playing"""
        for item in self._track_items.values():
            is_current = (
                self._is_playing
                and self._active_playlist_id
                == (self._current_playlist.id if self._current_playlist else None)
                and self._current_audio_file_id == item.track.audio_file_id
            )
            item.set_now_playing(is_current)

    def _is_playing_this_playlist(self, playlist_id: int) -> bool:
        """Check if the given playlist is the active one"""
        return self._active_playlist_id == playlist_id

    def _sync_play_button(self):
        """Sync play/pause button appearance with state"""
        is_active = (
            self._current_playlist
            and self._is_playing_this_playlist(self._current_playlist.id)
            and self._is_playing
        )
        if is_active:
            self.play_toggle_btn.setText("Pause")
            self.play_toggle_btn.setIcon(self._icons.icon("pause"))
        else:
            self.play_toggle_btn.setText("Play")
            self.play_toggle_btn.setIcon(self._icons.icon("play"))
        self.play_toggle_btn.setStyleSheet(
            Styles.playback_button_style(is_active=is_active)
        )

    def _sync_shuffle_button(self):
        """Sync shuffle button appearance with state"""
        if self._shuffle_enabled:
            self.shuffle_btn.setStyleSheet(
                Styles.toggle_on_style(radius=10, extra="padding: 8px 16px;")
            )
        else:
            self.shuffle_btn.setStyleSheet(
                Styles.toggle_off_style(radius=10, extra="padding: 8px 16px;")
            )

    def stop_all(self):
        """Stop all playback immediately (called by MainWindow on close)"""
        self._stop_playback()

    def clear(self):
        """Clear the editor"""
        # Stop if this playlist is playing
        if self._current_playlist and self._is_playing_this_playlist(
            self._current_playlist.id
        ):
            self._stop_playback()

        self._track_items.clear()
        self._current_playlist = None
        self.title_edit.hide()
        self.title_label.show()
        self.title_label.setText("Select a playlist")
        self.title_label.setToolTip("")
        self.add_tracks_btn.setEnabled(False)
        self.play_toggle_btn.setEnabled(False)
        self.shuffle_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self._sync_play_button()
        self.empty_label.hide()
        self.scroll_area.hide()

        # Clear track items
        clear_layout(self.tracks_layout)
        self.tracks_container.clear_registry()

    def refresh(self):
        """Refresh the current playlist"""
        if self._current_playlist:
            playlist = self.db.get_playlist(self._current_playlist.id)
            if playlist:
                self.load_playlist(playlist)
