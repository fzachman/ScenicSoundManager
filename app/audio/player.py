"""Individual track player with fade support"""

from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .engine import AudioEngine, vlc


class TrackPlayer(QObject):
    """Individual track player with volume control and fade support"""

    # Signals
    position_changed = pyqtSignal(int)  # Position in milliseconds
    state_changed = pyqtSignal(int)  # VLC state
    end_reached = pyqtSignal()

    def __init__(self, file_path: str, engine: AudioEngine | None = None):
        super().__init__()
        self.engine = engine or AudioEngine.get_instance()
        self.file_path = file_path
        self.available = self.engine.available

        # Volume settings (0-100; current holds fractional values mid-fade)
        self._target_volume = 100
        self._current_volume: float = 100

        # Fade timer
        self._fade_timer: QTimer | None = None
        self._fade_steps_remaining = 0
        self._fade_volume_step = 0.0
        self._fade_callback: Callable | None = None

        # End-of-media state. VLC parks the player in the Ended state where
        # play()/set_time() are no-ops; reviving needs an explicit restart().
        self._ended = False
        self._pending_seek_ms: int | None = None

        # Position update timer
        self._position_timer = QTimer()
        self._position_timer.timeout.connect(self._update_position)
        self._position_timer.setInterval(100)  # Update every 100ms

        # Repeat mode
        self._repeat = False

        # Media player (may be None if VLC not available)
        self.media_player: Any = None
        self.media: Any = None

        if self.available:
            # Create media player
            self.media_player = self.engine.create_player()
            self.media = self.engine.create_media(file_path)
            if self.media_player and self.media:
                assert vlc is not None  # available implies the import succeeded
                self.media_player.set_media(self.media)
                self._apply_volume(self._current_volume)

                # Set up end-reached event
                events = self.media_player.event_manager()
                events.event_attach(
                    vlc.EventType.MediaPlayerEndReached, self._on_end_reached
                )
                events.event_attach(
                    vlc.EventType.MediaPlayerPlaying, self._on_state_change
                )
                events.event_attach(
                    vlc.EventType.MediaPlayerPaused, self._on_state_change
                )
                events.event_attach(
                    vlc.EventType.MediaPlayerStopped, self._on_state_change
                )
                self.engine.register_player(self)
            else:
                self.available = False
                self.media_player = None
                self.media = None

    @property
    def target_volume(self) -> int:
        """Get the target volume (0-100)"""
        return self._target_volume

    @target_volume.setter
    def target_volume(self, value: int) -> None:
        """Set the target volume (0-100)"""
        self._target_volume = max(0, min(100, value))
        if self._is_fading():
            # Retarget the in-flight fade from wherever the ramp currently
            # is; without this the change is silently discarded until the
            # fade completes at its precomputed endpoint. The pending
            # callback (e.g. pause after a fade-out) is preserved.
            callback = self._fade_callback
            self._stop_fade()
            self._start_fade(self._current_volume, self._target_volume, 200, callback)
        else:
            self._current_volume = self._target_volume
            self._apply_volume(self._current_volume)

    @property
    def repeat(self) -> bool:
        """Get repeat mode"""
        return self._repeat

    @repeat.setter
    def repeat(self, value: bool) -> None:
        """Set repeat mode"""
        self._repeat = value

    def play(self) -> None:
        """Start or resume playback"""
        if self.media_player:
            self.media_player.play()
            self._position_timer.start()

    def pause(self) -> None:
        """Pause playback"""
        if self.media_player:
            self.media_player.pause()
        self._position_timer.stop()

    def stop(self) -> None:
        """Stop playback"""
        if self.media_player:
            self.media_player.stop()
        self._ended = False
        self._pending_seek_ms = None
        self._position_timer.stop()

    def is_playing(self) -> bool:
        """Check if currently playing"""
        if self.media_player:
            return self.media_player.is_playing()
        return False

    def get_position(self) -> int:
        """Get current position in milliseconds"""
        if self.media_player:
            return self.media_player.get_time()
        return 0

    @property
    def has_ended(self) -> bool:
        """True once the media finished with repeat off (until revived)."""
        return self._ended

    def set_position(self, position_ms: int) -> None:
        """Set playback position in milliseconds"""
        if self._ended:
            # Ended players silently ignore set_time; a scrub on a finished
            # track means "play again from here".
            self.restart(position_ms)
            return
        if self.media_player:
            self.media_player.set_time(position_ms)

    def restart(self, position_ms: int = 0) -> None:
        """Start playing again after the media ended.

        VLC needs a stop() before an Ended player accepts play(). The seek
        (if any) is deferred until the Playing state actually arrives —
        set_time() right after play() lands in a not-yet-playing player and
        is dropped (see _handle_state_change).
        """
        self._ended = False
        self._pending_seek_ms = position_ms if position_ms > 0 else None
        if self.media_player:
            self.media_player.stop()
            self.media_player.play()
            self._apply_volume(self._current_volume)
        self._position_timer.start()

    def get_duration(self) -> int:
        """Get media duration in milliseconds"""
        if self.media_player:
            return self.media_player.get_length()
        return 0

    def get_state(self) -> Any:
        """Get current player state"""
        if self.media_player:
            return self.media_player.get_state()
        return None

    def fade_in(self, duration_ms: int = 1000, start_playing: bool = True) -> None:
        """Gradually increase volume from 0 to target volume"""
        self._stop_fade()

        # Start from 0
        self._current_volume = 0
        self._apply_volume(0)

        if start_playing:
            self.play()

        self._start_fade(0, self._target_volume, duration_ms)

    def fade_out(self, duration_ms: int = 1000, pause_after: bool = True) -> None:
        """Gradually decrease volume to 0, optionally pause after"""
        self._stop_fade()

        callback = self.pause if pause_after else None
        self._start_fade(self._current_volume, 0, duration_ms, callback)

    def fade_to_volume(self, target_volume: int, duration_ms: int = 500) -> None:
        """Fade to a specific volume level"""
        self._stop_fade()
        self._target_volume = max(0, min(100, target_volume))
        self._start_fade(self._current_volume, self._target_volume, duration_ms)

    def _start_fade(
        self,
        from_volume: float,
        to_volume: int,
        duration_ms: int,
        callback: Callable | None = None,
    ) -> None:
        """Start a fade transition"""
        steps = 20
        step_duration = max(1, duration_ms // steps)
        volume_diff = to_volume - from_volume
        self._fade_volume_step = volume_diff / steps
        self._fade_steps_remaining = steps
        self._fade_callback = callback

        self._fade_timer = QTimer()
        self._fade_timer.timeout.connect(self._fade_step)
        self._fade_timer.start(step_duration)

    def _fade_step(self) -> None:
        """Execute one step of a fade transition"""
        self._fade_steps_remaining -= 1
        self._current_volume += self._fade_volume_step

        if self._fade_steps_remaining <= 0:
            # Fade complete
            self._current_volume = round(self._current_volume)
            self._apply_volume(self._current_volume)
            self._stop_fade()

            if self._fade_callback:
                self._fade_callback()
                self._fade_callback = None
        else:
            self._apply_volume(self._current_volume)

    def _stop_fade(self) -> None:
        """Stop any ongoing fade"""
        if self._fade_timer:
            self._fade_timer.stop()
            self._fade_timer = None

    def _is_fading(self) -> bool:
        """Check if a fade is in progress"""
        return self._fade_timer is not None and self._fade_timer.isActive()

    def _update_position(self) -> None:
        """Emit position update signal"""
        position = self.get_position()
        if position >= 0:
            self.position_changed.emit(position)

    def _on_end_reached(self, event) -> None:
        """Handle end of media"""
        # Use QTimer to handle this in the main thread
        QTimer.singleShot(0, self._handle_end_reached)

    def _handle_end_reached(self) -> None:
        """Handle end reached in main thread"""
        self.end_reached.emit()
        if self._repeat and self.media_player:
            # Restart playback
            self.media_player.stop()
            self.media_player.play()
        else:
            # The player is parked in VLC's Ended state: play()/set_time()
            # are no-ops until restart(). Remember that so a later scrub or
            # repeat-toggle can revive the track instead of dying silently.
            self._ended = True
            self._position_timer.stop()

    def _on_state_change(self, event) -> None:
        """Handle state change events"""
        if self.media_player:
            # Capture state immediately to avoid race condition if player is released
            # before the callback executes
            state = self.media_player.get_state()
            QTimer.singleShot(0, lambda s=state: self._handle_state_change(s))

    def _handle_state_change(self, state: Any) -> None:
        """Handle a state change in the main thread"""
        if (
            vlc is not None
            and state == vlc.State.Playing
            and self._pending_seek_ms is not None
            and self.media_player
        ):
            self.media_player.set_time(self._pending_seek_ms)
            self._pending_seek_ms = None
        self.state_changed.emit(state)

    def release(self) -> None:
        """Release player resources"""
        self._stop_fade()
        self._position_timer.stop()
        if self.media_player:
            if vlc is not None:
                events = self.media_player.event_manager()
                events.event_detach(vlc.EventType.MediaPlayerEndReached)
                events.event_detach(vlc.EventType.MediaPlayerPlaying)
                events.event_detach(vlc.EventType.MediaPlayerPaused)
                events.event_detach(vlc.EventType.MediaPlayerStopped)
            self.media_player.stop()
            self.media_player.release()
            self.media_player = None
        self.engine.unregister_player(self)

    def apply_master_volume(self) -> None:
        """Re-apply volume scaling when master volume changes"""
        self._apply_volume(self._current_volume)

    def _apply_volume(self, base_volume: float) -> None:
        if self.media_player:
            effective = int(base_volume * self.engine.master_volume / 100)
            self.media_player.audio_set_volume(effective)
