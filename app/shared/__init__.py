"""Shared components for SoundManager"""

from .dialogs import (
    AudioFileSearchDialog,
    DuplicateFilesDialog,
    FilePickerDialog,
    TagEditDialog,
)
from .logging import configure_logging, get_logger
from .styles import Styles
from .volume_slider import VolumeSlider

__all__ = [
    "configure_logging",
    "get_logger",
    "Styles",
    "FilePickerDialog",
    "TagEditDialog",
    "DuplicateFilesDialog",
    "AudioFileSearchDialog",
    "VolumeSlider",
]
