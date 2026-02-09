"""Shared components for SoundManager"""

from .logging import configure_logging, get_logger
from .styles import Styles
from .dialogs import FilePickerDialog, TagEditDialog, DuplicateFilesDialog, AudioFileSearchDialog

__all__ = [
    "configure_logging",
    "get_logger",
    "Styles",
    "FilePickerDialog",
    "TagEditDialog",
    "DuplicateFilesDialog",
    "AudioFileSearchDialog",
]
