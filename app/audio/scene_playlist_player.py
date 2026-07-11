"""Player for a playlist entry within a scene.

Manages sequential or smart-shuffled playback through a playlist's tracks,
with optional repeat. Each ScenePlaylistPlayer drives a single TrackPlayer
at a time, auto-advancing when a track ends.
"""

import contextlib
import os

from PyQt6.QtCore import QObject, pyqtSignal

from app.shared.logging import get_logger

from ..database import DatabaseConnection, PlaylistTrack
from .engine import AudioEngine
from .player import TrackPlayer
from .shuffle import SmartShuffle

_log = get_logger(__name__)


class ScenePlaylistPlayer(QObject):
    """Plays through a playlist's tracks within a scene context.

    Signals:
        track_changed(int): emitted with audio_file_id when a new track starts
        position_changed(int): current track position in ms (forwarded from the
            active TrackPlayer); reset implicitly via track_changed on advance
        playback_finished(): emitted when the playlist finishes (no repeat)
    """

    track_changed = pyqtSignal(int)  # audio_file_id
    position_changed = pyqtSignal(int)  # position in ms of the current track
    playback_finished = pyqtSignal()

    def __init__(
        self,
        playlist_id: int,
        db: DatabaseConnection,
        engine: AudioEngine,
        is_shuffle: bool = False,
        is_repeat: bool = False,
        volume: int = 100,
    ):
        super().__init__()
        self._playlist_id = playlist_id
        self._db = db
        self._engine = engine
        self._is_shuffle = is_shuffle
        self._is_repeat = is_repeat
        self._volume = volume  # 0-100

        self._player: TrackPlayer | None = None
        self._shuffle = SmartShuffle()
        self._tracks: list[PlaylistTrack] = []
        self._audio_file_ids: list[int] = []
        self._current_index: int = 0
        self._current_audio_file_id: int | None = None
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
    def current_audio_file_id(self) -> int | None:
        return self._current_audio_file_id

    def set_volume(self, volume: int) -> None:
        """Update entry volume (0-100). Applies immediately to the current player."""
        self._volume = volume
        if self._player:
            self._player.target_volume = self._current_effective_volume()

    def fade_to_volume(self, volume: int, duration_ms: int = 500) -> None:
        """Ramp to an entry volume (0-100); later tracks start at the new level."""
        self._volume = volume
        if self._player:
            self._player.fade_to_volume(self._current_effective_volume(), duration_ms)

    def _current_effective_volume(self) -> int:
        """Entry volume scaled by the current track's own stored volume.

        The entry slider acts as a master over the playlist's per-track
        (normalization) volumes, so tracks keep their relative levels.
        """
        track = (
            self._find_track(self._current_audio_file_id)
            if self._current_audio_file_id is not None
            else None
        )
        return round(self._volume * (track.volume if track else 1.0))

    def set_shuffle(self, enabled: bool) -> None:
        """Update shuffle mode (can be toggled during playback)."""
        self._is_shuffle = enabled
        if enabled:
            self._shuffle.update_tracks(self._audio_file_ids)

    def set_repeat(self, enabled: bool) -> None:
        """Update repeat mode (can be toggled during playback)."""
        self._is_repeat = enabled

    def get_duration(self) -> int:
        """Duration (ms) of the current track, or 0 if nothing is loaded."""
        return self._player.get_duration() if self._player else 0

    def set_position(self, position_ms: int) -> None:
        """Seek the current track to ``position_ms`` (no-op if nothing loaded)."""
        if self._player:
            self._player.set_position(position_ms)

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
            self._play_file_or_advance(audio_file_id, fade_ms)

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

    def next_track(self, fade_ms: int = 500) -> None:
        """Manually skip to the next track.

        Uses the same advance logic as a natural track end (honoring shuffle and
        repeat). At the end of a non-repeating playlist there is nothing to skip
        to, so the current track is stopped and the entry finishes — matching how
        auto-advance ends. No-op when not playing or the playlist is empty.
        """
        if not self._is_playing or not self._audio_file_ids:
            return

        next_id = self._get_next_audio_file_id()
        if next_id is not None:
            self._play_file_or_advance(next_id, fade_ms)
        elif self._is_repeat:
            self._restart()
        else:
            self.stop()
            self.playback_finished.emit()

    def stop(self) -> None:
        """Stop playback and release player."""
        self._release_player()
        self._is_playing = False
        self._current_audio_file_id = None
        self._tracks_played_count = 0

    def fade_out_and_release(self, fade_ms: int) -> None:
        """Detach the current track, let it fade to silence, and go idle.

        Signals are disconnected first for the same reasons as
        _release_player: the retiring track must not advance the playlist
        or drive the scrubber while it fades. The TrackPlayer releases
        itself when the fade completes.
        """
        player = self._player
        if player is not None:
            with contextlib.suppress(TypeError):
                player.end_reached.disconnect(self._on_track_ended)
            with contextlib.suppress(TypeError):
                player.position_changed.disconnect(self.position_changed)
            self._player = None
            player.fade_out_and_release(fade_ms)
        self._is_playing = False
        self._current_audio_file_id = None
        self._tracks_played_count = 0

    def release(self) -> None:
        """Release all resources."""
        self.stop()

    def _play_file(self, audio_file_id: int, fade_ms: int = 500) -> bool:
        """Play a specific audio file by its ID. Returns True if playback started."""
        track = self._find_track(audio_file_id)
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

        self._release_player()

        self._player = TrackPlayer(track.audio_file.file_path, self._engine)
        self._player.target_volume = round(self._volume * track.volume)
        self._player.end_reached.connect(self._on_track_ended)
        # Forward the active track's position so the scene's playlist card can
        # show a scrubber. The prior player is released in _release_player above,
        # so only the current track emits.
        self._player.position_changed.connect(self.position_changed)
        self._player.fade_in(fade_ms)
        self._current_audio_file_id = audio_file_id
        self._tracks_played_count += 1

        # Update sequential index to match
        for i, afid in enumerate(self._audio_file_ids):
            if afid == audio_file_id:
                self._current_index = i
                break

        self.track_changed.emit(audio_file_id)
        return True

    def _play_file_or_advance(
        self, audio_file_id: int | None, fade_ms: int = 500
    ) -> None:
        """Try to play the given file; on failure (e.g. missing file), advance
        through the playlist until something plays or all tracks were tried."""
        attempts = 0
        max_attempts = len(self._audio_file_ids)
        next_id = audio_file_id
        while next_id is not None and attempts < max_attempts:
            if self._play_file(next_id, fade_ms):
                return
            attempts += 1
            next_id = self._get_next_audio_file_id()
        # Nothing playable. Release the current track too: on a manual skip the
        # old track is still audible (a missing next file returns from
        # _play_file *before* _release_player), so without this it would keep
        # playing while the UI reports "finished".
        self._release_player()
        self._is_playing = False
        self._current_audio_file_id = None
        self.playback_finished.emit()

    def _on_track_ended(self) -> None:
        """Handle track end - advance to next or finish."""
        if not self._is_playing:
            return

        next_id = self._get_next_audio_file_id()
        if next_id is not None:
            self._play_file_or_advance(next_id)
        else:
            # Playlist exhausted
            if self._is_repeat:
                self._restart()
            else:
                self._is_playing = False
                self._current_audio_file_id = None
                self.playback_finished.emit()

    def _get_next_audio_file_id(self) -> int | None:
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
            self._play_file_or_advance(audio_file_id)
        else:
            self._is_playing = False
            self.playback_finished.emit()

    def _find_track(self, audio_file_id: int) -> PlaylistTrack | None:
        """Find a PlaylistTrack by audio_file_id."""
        for t in self._tracks:
            if t.audio_file_id == audio_file_id:
                return t
        return None

    def _release_player(self) -> None:
        """Release the current TrackPlayer."""
        if self._player:
            # Disconnect first: TrackPlayer.end_reached is delivered via
            # QTimer.singleShot, so a manual skip can race a just-posted
            # end-of-media and advance the playlist twice (skipping a track) if
            # the old player's signals stay wired. Position forwarding is cut for
            # the same reason — the released track must not drive the scrubber.
            with contextlib.suppress(TypeError):
                self._player.end_reached.disconnect(self._on_track_ended)
            with contextlib.suppress(TypeError):
                self._player.position_changed.disconnect(self.position_changed)
            self._player.stop()
            self._player.release()
            self._player = None
