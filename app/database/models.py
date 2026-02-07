"""Data models for SoundManager"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class AudioFile:
    """Represents an audio file in the library"""
    id: Optional[int] = None
    file_path: str = ""
    title: Optional[str] = None
    artist: Optional[str] = None
    duration_seconds: Optional[float] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
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
    id: Optional[int] = None
    name: str = ""
    color: Optional[str] = None  # Hex color
    created_at: Optional[datetime] = None


@dataclass
class Scene:
    """Represents a scene/soundscape"""
    id: Optional[int] = None
    title: str = ""
    position: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tracks: list["SceneAudioFile"] = field(default_factory=list)
    playlist_entries: list["ScenePlaylistEntry"] = field(default_factory=list)


@dataclass
class SceneAudioFile:
    """Represents an audio file within a scene with its settings"""
    id: Optional[int] = None
    scene_id: Optional[int] = None
    audio_file_id: Optional[int] = None
    position: int = 0
    volume: float = 1.0  # 0.0 to 1.0
    is_repeat: bool = False
    play_mode: bool = True
    audio_file: Optional[AudioFile] = None


@dataclass
class ScenePlaylistEntry:
    """Represents a playlist entry within a scene with per-entry settings"""
    id: Optional[int] = None
    scene_id: Optional[int] = None
    playlist_id: Optional[int] = None
    position: int = 0
    is_shuffle: bool = False
    is_repeat: bool = False
    play_mode: bool = True
    playlist: Optional["Playlist"] = None


@dataclass
class Playlist:
    """Represents a playlist of audio files"""
    id: Optional[int] = None
    name: str = ""
    position: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tracks: list["PlaylistTrack"] = field(default_factory=list)


@dataclass
class PlaylistTrack:
    """Represents an audio file within a playlist"""
    id: Optional[int] = None
    playlist_id: Optional[int] = None
    audio_file_id: Optional[int] = None
    position: int = 0
    audio_file: Optional[AudioFile] = None
