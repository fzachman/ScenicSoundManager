"""Soundboard: one-shot sound effects panel docked below the main content."""

from .board_widget import SoundboardButtonCell, SoundboardContent
from .edit_dialog import SoundboardEditDialog
from .panel import SoundboardDock, SoundboardTitleBar

__all__ = [
    "SoundboardButtonCell",
    "SoundboardContent",
    "SoundboardDock",
    "SoundboardEditDialog",
    "SoundboardTitleBar",
]
