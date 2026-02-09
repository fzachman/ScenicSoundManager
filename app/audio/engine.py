"""Audio engine using python-vlc"""

import os
import sys
import weakref
from typing import Optional, Any

from app.shared.logging import get_logger

_log = get_logger(__name__)

# Try to import VLC, but handle the case where it's not available
VLC_AVAILABLE = False
vlc = None

try:
    import vlc as _vlc
    vlc = _vlc
    VLC_AVAILABLE = True
except (OSError, ImportError) as e:
    _log.warning("vlc_not_available", error=str(e))
    _log.warning("audio_playback_disabled")


class AudioEngine:
    """Manages VLC instance and provides factory for creating players"""

    _instance: Optional["AudioEngine"] = None

    def __init__(self):
        self.vlc_instance = None
        self.available = False
        self._master_volume = 100  # 0-100
        self._players: "weakref.WeakSet[Any]" = weakref.WeakSet()

        if not VLC_AVAILABLE:
            return

        # Configure VLC to look for bundled libraries if running from app bundle
        self._configure_vlc_paths()

        try:
            self.vlc_instance = vlc.Instance("--no-xlib")  # Disable X11 on macOS
            self.available = True
        except Exception as e:
            _log.warning("vlc_init_failed", error=str(e))

    @classmethod
    def get_instance(cls) -> "AudioEngine":
        """Get or create the singleton AudioEngine instance"""
        if cls._instance is None:
            cls._instance = AudioEngine()
        return cls._instance

    @classmethod
    def is_available(cls) -> bool:
        """Check if VLC audio is available"""
        return VLC_AVAILABLE and cls.get_instance().available

    def _configure_vlc_paths(self) -> None:
        """Configure paths for bundled VLC libraries in app bundle"""
        if getattr(sys, "frozen", False):
            # Running in a py2app bundle
            bundle_dir = os.path.dirname(sys.executable)
            resources_dir = os.path.join(bundle_dir, "..", "Resources")
            vlc_lib_path = os.path.join(resources_dir, "lib", "libvlc.dylib")
            vlc_plugin_path = os.path.join(resources_dir, "plugins")

            if os.path.exists(vlc_lib_path):
                os.environ["PYTHON_VLC_LIB_PATH"] = vlc_lib_path
            if os.path.exists(vlc_plugin_path):
                os.environ["VLC_PLUGIN_PATH"] = vlc_plugin_path

    def create_media(self, file_path: str) -> Optional[Any]:
        """Create a VLC Media object from a file path"""
        if not self.available or not self.vlc_instance:
            return None
        return self.vlc_instance.media_new(file_path)

    def create_player(self) -> Optional[Any]:
        """Create a new VLC MediaPlayer instance"""
        if not self.available or not self.vlc_instance:
            return None
        return self.vlc_instance.media_player_new()

    def release(self) -> None:
        """Release VLC resources"""
        if self.vlc_instance:
            self.vlc_instance.release()
            self.vlc_instance = None
        AudioEngine._instance = None

    @property
    def master_volume(self) -> int:
        """Get master volume (0-100)"""
        return self._master_volume

    @master_volume.setter
    def master_volume(self, value: int) -> None:
        """Set master volume and update active players"""
        self._master_volume = max(0, min(100, value))
        for player in list(self._players):
            player.apply_master_volume()

    def register_player(self, player: Any) -> None:
        """Register a player for master volume updates"""
        self._players.add(player)

    def unregister_player(self, player: Any) -> None:
        """Unregister a player"""
        if player in self._players:
            self._players.discard(player)
