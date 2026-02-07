"""Player for a playlist entry within a scene.

Manages sequential or smart-shuffled playback through a playlist's tracks,
with optional repeat. Each ScenePlaylistPlayer drives a single TrackPlayer
at a time, auto-advancing when a track ends.
"""

import os
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from .engine import AudioEngine
from .player import TrackPlayer
from .shuffle import SmartShuffle
from ..database import DatabaseConnection, PlaylistTrack


class ScenePlaylistPlayer(QObject):
    """Plays through a playlist's tracks within a scene context.

    Signals:
        track_changed(int): emitted with audio_file_id when a new track starts
        playback_finished(): emitted when the playlist finishes (no repeat)
    """

    track_changed = pyqtSignal(int)  # audio_file_id
    playback_finished = pyqtSignal()

    def __init__(
        self,
        playlist_id: int,
        db: DatabaseConnection,
        engine: AudioEngine,
        is_shuffle: bool = False,
        is_repeat: bool = False,
    ):
        super().__init__()
        self._playlist_id = playlist_id
        self._db = db
        self._engine = engine
        self._is_shuffle = is_shuffle
        self._is_repeat = is_repeat

        self._player: Optional[TrackPlayer] = None
        self._shuffle = SmartShuffle()
        self._tracks: list[PlaylistTrack] = []
        self._audio_file_ids: list[int] = []
        self._current_index: int = 0
        self._current_audio_file_id: Optional[int] = None
        self._is_playing = False
        self._tracks_played_count = 0

        self._load_tracks()

    @property
    def playlist_id(self) -> int:
        return self._playlist_id

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    @property
    def current_audio_file_id(self) -> Optional[int]:
        return self._current_audio_file_id

    def set_shuffle(self, enabled: bool) -> None:
        """Update shuffle mode (can be toggled during playback)."""
        self._is_shuffle = enabled
        if enabled:
            self._shuffle.update_tracks(self._audio_file_ids)

    def set_repeat(self, enabled: bool) -> None:
        """Update repeat mode (can be toggled during playback)."""
        self._is_repeat = enabled

    def _load_tracks(self) -> None:
        """Load playlist tracks from the database."""
        self._tracks = self._db.get_playlist_tracks(self._playlist_id)
        self._audio_file_ids = [
            t.audio_file_id for t in self._tracks if t.audio_file_id
        ]
        if self._is_shuffle and self._audio_file_ids:
            self._shuffle.update_tracks(self._audio_file_ids)

    def start(self, fade_ms: int = 500) -> None:
        """Start playback from the beginning."""
        if not self._audio_file_ids:
            return

        self._is_playing = True
        self._current_index = 0
        self._tracks_played_count = 0

        if self._is_shuffle:
            self._shuffle.reset()
            audio_file_id = self._shuffle.next()
        else:
            audio_file_id = self._audio_file_ids[0]

        if audio_file_id is not None:
            self._play_file(audio_file_id, fade_ms)

    def pause(self, fade_ms: int = 500) -> None:
        """Pause current playback."""
        if self._player:
            self._player.fade_out(fade_ms, pause_after=True)
        self._is_playing = False

    def resume(self, fade_ms: int = 500) -> None:
        """Resume from pause."""
        if self._player:
            self._player.fade_in(fade_ms)
        self._is_playing = True

    def stop(self) -> None:
        """Stop playback and release player."""
        self._release_player()
        self._is_playing = False
        self._current_audio_file_id = None
        self._tracks_played_count = 0

    def release(self) -> None:
        """Release all resources."""
        self.stop()

    def _play_file(self, audio_file_id: int, fade_ms: int = 500) -> None:
        """Play a specific audio file by its ID."""
        track = self._find_track(audio_file_id)
        if not track or not track.audio_file:
            return
        if not os.path.exists(track.audio_file.file_path):
            return

        self._release_player()

        self._player = TrackPlayer(track.audio_file.file_path, self._engine)
        self._player.end_reached.connect(self._on_track_ended)
        self._player.fade_in(fade_ms)
        self._current_audio_file_id = audio_file_id
        self._tracks_played_count += 1

        # Update sequential index to match
        for i, afid in enumerate(self._audio_file_ids):
            if afid == audio_file_id:
                self._current_index = i
                break

        self.track_changed.emit(audio_file_id)

    def _on_track_ended(self) -> None:
        """Handle track end - advance to next or finish."""
        if not self._is_playing:
            return

        next_id = self._get_next_audio_file_id()
        if next_id is not None:
            self._play_file(next_id)
        else:
            # Playlist exhausted
            if self._is_repeat:
                self._restart()
            else:
                self._is_playing = False
                self._current_audio_file_id = None
                self.playback_finished.emit()

    def _get_next_audio_file_id(self) -> Optional[int]:
        """Get the next audio file ID to play."""
        if not self._audio_file_ids:
            return None

        if self._is_shuffle:
            if self._shuffle.cycle_complete:
                # All tracks played once in this shuffle cycle
                return None
            return self._shuffle.next()
        else:
            next_index = self._current_index + 1
            if next_index >= len(self._audio_file_ids):
                # Reached end of sequential list
                return None
            self._current_index = next_index
            return self._audio_file_ids[next_index]

    def _restart(self) -> None:
        """Restart the playlist (for repeat mode)."""
        self._tracks_played_count = 0
        if self._is_shuffle:
            self._shuffle.reset()
            audio_file_id = self._shuffle.next()
        else:
            self._current_index = 0
            audio_file_id = self._audio_file_ids[0] if self._audio_file_ids else None

        if audio_file_id is not None:
            self._play_file(audio_file_id)
        else:
            self._is_playing = False
            self.playback_finished.emit()

    def _find_track(self, audio_file_id: int) -> Optional[PlaylistTrack]:
        """Find a PlaylistTrack by audio_file_id."""
        for t in self._tracks:
            if t.audio_file_id == audio_file_id:
                return t
        return None

    def _release_player(self) -> None:
        """Release the current TrackPlayer."""
        if self._player:
            self._player.stop()
            self._player.release()
            self._player = None
