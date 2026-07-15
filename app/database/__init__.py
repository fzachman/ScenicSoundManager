"""Database module for SoundManager"""

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
