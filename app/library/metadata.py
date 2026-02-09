"""Metadata extraction using mutagen"""

import os
from typing import Optional

from mutagen import File
from mutagen.easyid3 import EasyID3

from app.shared.logging import get_logger

_log = get_logger(__name__)


class MetadataExtractor:
    """Extract metadata from audio files using mutagen"""

    @staticmethod
    def extract(file_path: str) -> dict:
        """
        Extract metadata from an audio file.

        Returns:
            dict with keys: title, artist, duration_seconds
        """
        result = {
            "title": None,
            "artist": None,
            "duration_seconds": None
        }

        try:
            audio = File(file_path, easy=True)

            if audio is None:
                # File not recognized, use filename as title
                result["title"] = os.path.splitext(os.path.basename(file_path))[0]
                return result

            # Extract title
            title = audio.get("title")
            if title and len(title) > 0:
                result["title"] = title[0]
            else:
                result["title"] = os.path.splitext(os.path.basename(file_path))[0]

            # Extract artist
            artist = audio.get("artist")
            if artist and len(artist) > 0:
                result["artist"] = artist[0]

            # Extract duration
            if hasattr(audio, "info") and audio.info:
                result["duration_seconds"] = audio.info.length

        except Exception as e:
            # On error, use filename as title
            result["title"] = os.path.splitext(os.path.basename(file_path))[0]
            _log.error("metadata_extraction_failed", file_path=file_path, error=str(e))

        return result

    @staticmethod
    def is_supported_format(file_path: str) -> bool:
        """Check if a file is a supported audio format"""
        supported_extensions = {
            ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"
        }
        _, ext = os.path.splitext(file_path.lower())
        return ext in supported_extensions
