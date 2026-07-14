"""Remote-control facade: the single seam between remote commands and the UI.

Every remote command (WebSocket, test client, future integrations) goes
through this object; it validates parameters, translates commands into calls
on ``MainWindow`` and its tab widgets, and republishes playback/volume changes
as one coarse ``state_changed`` snapshot (the protocol's ``state`` event).
See ``docs/remote-protocol.md`` for the wire protocol it backs.
"""

from PyQt6.QtCore import QObject, pyqtSignal

from ..database import PRESET_SLOTS
from ..shared.logging import get_logger

logger = get_logger(__name__)


class RemoteError(Exception):
    """A remote command failed; maps to an ``ok: false`` protocol response."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _require_id(value, what: str) -> int:
    # bool is an int subclass; reject it explicitly so `true` isn't a valid id
    if isinstance(value, bool) or not isinstance(value, int):
        raise RemoteError("invalid_params", f"{what} must be an integer")
    return value


def _require_slot(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RemoteError("invalid_params", "preset must be an integer")
    if value not in PRESET_SLOTS:
        raise RemoteError(
            "invalid_params", f"preset must be one of {list(PRESET_SLOTS)}"
        )
    return value


class RemoteControlFacade(QObject):
    """Command surface for remote clients.

    Must be constructed AFTER ``MainWindow._connect_signals``: PyQt invokes
    slots in connection order, so MainWindow updates its now-playing state
    before the handlers here snapshot it via ``current_playback()``.
    """

    state_changed = pyqtSignal(object)  # dict snapshot, see get_state()

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        window.scenes_widget.playback_state_changed.connect(self._emit_state)
        window.scenes_widget.preset_changed.connect(self._emit_state)
        window.playlists_widget.playback_state_changed.connect(self._emit_state)
        window.master_slider.valueChanged.connect(self._emit_state)

    # --- queries ---------------------------------------------------------

    def get_state(self) -> dict:
        """Full snapshot: what's playing or paused (if anything) + master volume.

        ``playing`` and ``paused`` are mutually exclusive: at most one item is
        active app-wide (mutual exclusivity stops the old item — paused or
        playing — whenever a new one starts), and ``paused`` is only reported
        when nothing is playing.
        """
        playing = None
        paused = None
        current = self._window.current_playback()
        if current is not None:
            kind, item_id = current
            playing = self._item_state(kind, item_id)
        else:
            paused = self._paused_item()
        return {
            "playing": playing,
            "paused": paused,
            "master_volume": self._window.audio_engine.master_volume,
        }

    def get_scenes(self) -> list[dict]:
        """All scenes with their preset slots (name is null for unnamed slots)."""
        db = self._window.db
        scenes = []
        for scene in db.get_all_scenes():
            names = db.get_scene_preset_names(scene.id) if scene.id else {}
            scenes.append(
                {
                    "id": scene.id,
                    "name": scene.title,
                    "active_preset": scene.active_preset_slot,
                    "presets": [
                        {"slot": slot, "name": names.get(slot)} for slot in PRESET_SLOTS
                    ],
                }
            )
        return scenes

    def get_playlists(self) -> list[dict]:
        return [
            {"id": playlist.id, "name": playlist.name}
            for playlist in self._window.db.get_all_playlists()
        ]

    # --- commands ---------------------------------------------------------

    def play_scene(self, scene_id, preset=None) -> None:
        """Select the scene (tab + sidebar, like clicking it) and play it.

        With ``preset``, the slot is activated between selecting and playing:
        a not-yet-playing scene starts directly in that preset (no double
        transition), and one already playing just live-crossfades the preset —
        ``play_current()`` skips the already-playing scene. So a controller
        button bound to one (scene, preset) pair does the right thing whether
        that scene is playing or not.
        """
        scene_id = _require_id(scene_id, "scene_id")
        if preset is not None:
            preset = _require_slot(preset)
        if self._window.db.get_scene(scene_id) is None:
            raise RemoteError("not_found", f"no scene with id {scene_id}")
        logger.info("remote_play_scene", scene_id=scene_id, preset=preset)
        self._window.tab_widget.setCurrentWidget(self._window.scenes_widget)
        self._window.scenes_widget.select_scene(scene_id)
        if preset is not None:
            self._window.scenes_widget.switch_preset(preset)
        self._window.scenes_widget.play_current()

    def play_playlist(self, playlist_id) -> None:
        """Select the playlist (tab + sidebar, like clicking it) and play it."""
        playlist_id = _require_id(playlist_id, "playlist_id")
        if self._window.db.get_playlist(playlist_id) is None:
            raise RemoteError("not_found", f"no playlist with id {playlist_id}")
        logger.info("remote_play_playlist", playlist_id=playlist_id)
        self._window.tab_widget.setCurrentWidget(self._window.playlists_widget)
        self._window.playlists_widget.select_playlist(playlist_id)
        self._window.playlists_widget.play_current()

    def set_preset(self, preset) -> None:
        """Switch the active (playing or paused) scene to another preset.

        Selects that scene in the UI first (like ``play_scene``) so the
        editor — which preset switching runs through — has it loaded. A
        playing scene gets the live crossfade; a paused one just picks up the
        preset's settings for when it resumes.
        """
        preset = _require_slot(preset)
        active = self._window.scenes_widget.active_playback()
        if active is None:
            raise RemoteError("no_active_scene", "no scene is playing or paused")
        scene_id, _is_playing = active
        logger.info("remote_set_preset", scene_id=scene_id, preset=preset)
        self._window.tab_widget.setCurrentWidget(self._window.scenes_widget)
        self._window.scenes_widget.select_scene(scene_id)
        self._window.scenes_widget.switch_preset(preset)

    def toggle_play_pause(self) -> None:
        """Exactly the Space-key semantics."""
        self._window.toggle_play_pause()

    def next_track(self) -> None:
        """Exactly the Right-key semantics (playing playlist only)."""
        self._window.next_track()

    def set_master_volume(self, value) -> int:
        """Set the master volume (clamped to 0-100); returns the applied value.

        Goes through the slider so the existing valueChanged slot keeps the
        engine, the % label, and the QSettings persistence on one path.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise RemoteError("invalid_params", "value must be an integer")
        value = max(0, min(100, value))
        self._window.master_slider.setValue(value)
        return value

    # --- internal ---------------------------------------------------------

    def _paused_item(self) -> dict | None:
        """The item that owns playback but is paused (resumable), if any.

        Pulled from the editors' active-playback state rather than
        MainWindow's now-playing tracking, which collapses paused into idle.
        Selection is irrelevant here: browsing the sidebar while something is
        paused doesn't change what this reports.
        """
        for kind, widget in (
            ("scene", self._window.scenes_widget),
            ("playlist", self._window.playlists_widget),
        ):
            active = widget.active_playback()
            if active is not None:
                item_id, is_playing = active
                if not is_playing:
                    return self._item_state(kind, item_id)
        return None

    def _item_state(self, kind: str, item_id) -> dict:
        """The ``playing``/``paused`` wire shape for one item.

        ``preset`` is the scene's active slot (always null for playlists, or
        when the id can't be resolved, e.g. deleted mid-playback).
        """
        item: dict = {"type": kind, "id": item_id, "name": None, "preset": None}
        if item_id is None:
            return item
        if kind == "scene":
            scene = self._window.db.get_scene(item_id)
            if scene:
                item["name"] = scene.title
                item["preset"] = {
                    "slot": scene.active_preset_slot,
                    "name": scene.preset_names.get(scene.active_preset_slot),
                }
        else:
            playlist = self._window.db.get_playlist(item_id)
            item["name"] = playlist.name if playlist else None
        return item

    def _emit_state(self, *_args):
        """Republish any playback/volume change as one full snapshot."""
        self.state_changed.emit(self.get_state())
