"""Database module for SoundManager"""

from .backup import swap_database, validate_backup
from .connection import PRESET_SLOTS, DatabaseConnection
from .models import (
    AudioFile,
    Playlist,
    PlaylistTrack,
    Scene,
    SceneAudioFile,
    ScenePlaylistEntry,
    Soundboard,
    SoundboardButton,
    Tag,
)

__all__ = [
    "DatabaseConnection",
    "PRESET_SLOTS",
    "swap_database",
    "validate_backup",
    "AudioFile",
    "Tag",
    "Scene",
    "SceneAudioFile",
    "ScenePlaylistEntry",
    "Playlist",
    "PlaylistTrack",
    "Soundboard",
    "SoundboardButton",
]
