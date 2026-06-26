"""Shared components for SoundManager"""

from .dialogs import (
    AudioFileSearchDialog,
    DuplicateFilesDialog,
    FilePickerDialog,
    TagEditDialog,
)
from .logging import configure_logging, get_logger
from .styles import Styles

__all__ = [
    "configure_logging",
    "get_logger",
    "Styles",
    "FilePickerDialog",
    "TagEditDialog",
    "DuplicateFilesDialog",
    "AudioFileSearchDialog",
]
