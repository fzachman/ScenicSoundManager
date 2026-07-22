"""Data models for SoundManager"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class AudioFile:
    """Represents an audio file in the library"""

    id: int | None = None
    file_path: str = ""
    title: str | None = None
    artist: str | None = None
    duration_seconds: float | None = None
    file_size: int | None = None
    content_hash: str | None = None  # hex SHA-256 of the file bytes
    created_at: datetime | None = None
    updated_at: datetime | None = None
    tags: list["Tag"] = field(default_factory=list)

    @property
    def duration_formatted(self) -> str:
        """Return duration as MM:SS format"""
        if self.duration_seconds is None:
            return "--:--"
        minutes = int(self.duration_seconds // 60)
        seconds = int(self.duration_seconds % 60)
        return f"{minutes}:{seconds:02d}"

    @property
    def display_title(self) -> str:
        """Return title or filename if no title"""
        if self.title:
            return self.title
        import os

        return os.path.basename(self.file_path)


@dataclass
class Tag:
    """Represents a user-defined tag"""

    id: int | None = None
    name: str = ""
    color: str | None = None  # Hex color
    created_at: datetime | None = None


@dataclass
class Scene:
    """Represents a scene/soundscape"""

    id: int | None = None
    title: str = ""
    position: int = 0
    active_preset_slot: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None
    tracks: list["SceneAudioFile"] = field(default_factory=list)
    playlist_entries: list["ScenePlaylistEntry"] = field(default_factory=list)
    # slot -> custom name; slots without a row display as "Preset N"
    preset_names: dict[int, str] = field(default_factory=dict)


@dataclass
class SceneAudioFile:
    """Represents an audio file within a scene with its settings"""

    id: int | None = None
    scene_id: int | None = None
    audio_file_id: int | None = None
    position: int = 0
    volume: float = 1.0  # 0.0 to 1.0
    is_repeat: bool = False
    play_mode: bool = True
    audio_file: AudioFile | None = None


@dataclass
class ScenePlaylistEntry:
    """Represents a playlist entry within a scene with per-entry settings"""

    id: int | None = None
    scene_id: int | None = None
    playlist_id: int | None = None
    position: int = 0
    volume: float = 1.0  # 0.0 to 1.0
    is_shuffle: bool = False
    is_repeat: bool = False
    play_mode: bool = True
    playlist: Optional["Playlist"] = None


@dataclass
class Playlist:
    """Represents a playlist of audio files"""

    id: int | None = None
    name: str = ""
    position: int = 0
    is_shuffle: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    tracks: list["PlaylistTrack"] = field(default_factory=list)


@dataclass
class PlaylistTrack:
    """Represents an audio file within a playlist"""

    id: int | None = None
    playlist_id: int | None = None
    audio_file_id: int | None = None
    position: int = 0
    volume: float = 1.0
    audio_file: AudioFile | None = None


@dataclass
class Soundboard:
    """Represents a soundboard of one-shot sound effect buttons.

    No position field: boards are listed alphabetically (there is no
    reorder UI for boards, only for the buttons within one).
    """

    id: int | None = None
    name: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    buttons: list["SoundboardButton"] = field(default_factory=list)


@dataclass
class SoundboardButton:
    """Represents one button (grid cell) on a soundboard"""

    id: int | None = None
    soundboard_id: int | None = None
    audio_file_id: int | None = None
    position: int = 0
    volume: float = 1.0
    audio_file: AudioFile | None = None
