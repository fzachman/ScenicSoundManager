"""Scene mixer for managing multiple track players"""

from PyQt6.QtCore import QObject, pyqtSignal

from .engine import AudioEngine
from .player import TrackPlayer


class SceneMixer(QObject):
    """Manages multiple TrackPlayers for a scene"""

    # Signals
    track_added = pyqtSignal(int, TrackPlayer)  # track_id, player
    track_removed = pyqtSignal(int)  # track_id
    all_stopped = pyqtSignal()

    def __init__(self, engine: AudioEngine | None = None):
        super().__init__()
        self.engine = engine or AudioEngine.get_instance()
        self._players: dict[int, TrackPlayer] = {}  # track_id -> player

    @property
    def master_volume(self) -> int:
        """Get master volume (0-100)"""
        return self.engine.master_volume

    @master_volume.setter
    def master_volume(self, value: int) -> None:
        """Set master volume and adjust all track volumes"""
        self.engine.master_volume = value

    def add_track(self, track_id: int, file_path: str) -> TrackPlayer:
        """Add a track to the mixer, return the player"""
        if track_id in self._players:
            # Remove existing player
            self.remove_track(track_id)

        player = TrackPlayer(file_path, self.engine)
        self._players[track_id] = player
        self.track_added.emit(track_id, player)
        return player

    def remove_track(self, track_id: int) -> None:
        """Remove a track from the mixer"""
        if track_id in self._players:
            player = self._players.pop(track_id)
            player.release()
            self.track_removed.emit(track_id)

    def get_player(self, track_id: int) -> TrackPlayer | None:
        """Get the player for a track"""
        return self._players.get(track_id)

    def get_all_players(self) -> dict[int, TrackPlayer]:
        """Get all track players"""
        return self._players.copy()

    def play_all(self, fade_duration_ms: int = 1000) -> None:
        """Play all tracks with fade in"""
        for player in self._players.values():
            player.fade_in(fade_duration_ms)

    def pause_all(self, fade_duration_ms: int = 1000) -> None:
        """Pause all tracks with fade out"""
        for player in self._players.values():
            player.fade_out(fade_duration_ms, pause_after=True)

    def stop_all(self) -> None:
        """Stop all tracks immediately"""
        for player in self._players.values():
            player.stop()
        self.all_stopped.emit()

    def fade_out_and_clear(self, fade_ms: int) -> None:
        """Fade every track to silence and remove it from the mixer.

        The mixer is empty as soon as this returns; each retired player
        keeps itself alive just long enough to finish its fade and then
        releases itself (see TrackPlayer.fade_out_and_release).
        """
        for track_id in list(self._players):
            player = self._players.pop(track_id)
            player.fade_out_and_release(fade_ms)
            self.track_removed.emit(track_id)
        self.all_stopped.emit()

    def is_any_playing(self) -> bool:
        """Check if any track is currently playing"""
        return any(player.is_playing() for player in self._players.values())

    def set_track_volume(self, track_id: int, volume: int) -> None:
        """Set volume for a specific track (0-100)"""
        player = self._players.get(track_id)
        if player:
            player.target_volume = volume

    def set_track_repeat(self, track_id: int, repeat: bool) -> None:
        """Set repeat mode for a specific track"""
        player = self._players.get(track_id)
        if player:
            player.repeat = repeat

    def clear(self) -> None:
        """Remove all tracks"""
        track_ids = list(self._players.keys())
        for track_id in track_ids:
            self.remove_track(track_id)

    def release(self) -> None:
        """Release all player resources"""
        self.clear()
