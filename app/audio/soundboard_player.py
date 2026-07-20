"""One-shot soundboard playback: a single reusable player slot"""

import os

from PyQt6.QtCore import QObject, pyqtSignal

from ..shared.logging import get_logger
from .engine import AudioEngine
from .player import TrackPlayer

_log = get_logger(__name__)


class SoundboardPlayer(QObject):
    """Single-slot player for soundboard one-shots.

    At most one soundboard sound plays at a time: triggering a different
    button hard-stops the current sound (no fade) and plays the new one;
    triggering the same button while it plays stops it (play/stop toggle).
    A ``TrackPlayer`` is created per press and released on stop/end — only
    one is ever live, and it registers with the engine so master volume
    applies. Deliberately independent of the scene/playlist
    mutual-exclusivity chain: soundboard sounds play over whatever is active.
    """

    button_started = pyqtSignal(int)
    button_stopped = pyqtSignal(int)

    def __init__(self, engine: AudioEngine | None = None):
        super().__init__()
        self.engine = engine or AudioEngine.get_instance()
        self._player: TrackPlayer | None = None
        self._current_button_id: int | None = None

    @property
    def current_button_id(self) -> int | None:
        """The button whose sound occupies the slot (None when idle)."""
        return self._current_button_id

    def is_playing(self) -> bool:
        """Whether a soundboard sound is currently playing."""
        return self._player is not None and self._player.is_playing()

    def trigger(self, button_id: int, file_path: str, volume: float = 1.0) -> None:
        """Play a button's sound.

        The same button while its sound plays = stop (toggle); any other
        button hard-stops the current sound and plays instead.
        """
        if button_id == self._current_button_id and self.is_playing():
            self.stop()
            return
        self.stop()
        if not os.path.exists(file_path):
            _log.warning(
                "soundboard_file_missing", button_id=button_id, file_path=file_path
            )
            return
        player = TrackPlayer(file_path, engine=self.engine)
        player.target_volume = round(volume * 100)
        player.end_reached.connect(self._on_end_reached)
        self._player = player
        self._current_button_id = button_id
        player.play()
        self.button_started.emit(button_id)

    def set_current_volume(self, button_id: int, volume: float) -> None:
        """Live-apply a button's volume; no-op unless its sound is in the slot."""
        if button_id == self._current_button_id and self._player is not None:
            self._player.target_volume = round(volume * 100)

    def stop(self) -> None:
        """Hard-stop the current sound (no fade), if any."""
        stopped_button_id = self._release_slot()
        if stopped_button_id is not None:
            self.button_stopped.emit(stopped_button_id)

    def clear(self) -> None:
        """Silent teardown (app close): release, no signals."""
        self._release_slot()

    def _on_end_reached(self) -> None:
        """Natural end: empty the slot so the next press plays again."""
        self.stop()

    def _release_slot(self) -> int | None:
        player, self._player = self._player, None
        button_id, self._current_button_id = self._current_button_id, None
        if player is not None:
            player.end_reached.disconnect(self._on_end_reached)
            player.release()  # stops playback and detaches VLC events
        return button_id
