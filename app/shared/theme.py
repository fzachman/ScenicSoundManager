"""Runtime theme management: palette swapping and change notification.

Persistent widgets consolidate their palette-dependent styling into an
``_apply_theme_styles()`` method and connect it to ``theme_manager.
theme_changed``; PyQt auto-disconnects bound methods when the receiving
QObject is destroyed. Transient dialogs need no wiring — they are built
fresh with the active palette each time they open.
"""

from PyQt6.QtCore import QObject, QSettings, pyqtSignal

from .styles import Styles

SETTINGS_THEME_KEY = "appearance/theme"
DEFAULT_THEME = "dark"


class ThemeManager(QObject):
    """Owns the active theme; emits theme_changed after the palette swaps."""

    theme_changed = pyqtSignal(str)

    def set_theme(self, name: str) -> None:
        """Swap the active palette and notify subscribed widgets."""
        if name == Styles.active_theme:
            return
        Styles.set_theme(name)
        self.theme_changed.emit(Styles.active_theme)

    @staticmethod
    def saved_theme() -> str:
        theme = QSettings().value(
            SETTINGS_THEME_KEY, defaultValue=DEFAULT_THEME, type=str
        )
        return theme if theme in Styles.PALETTES else DEFAULT_THEME

    def apply_saved_theme(self) -> None:
        """Startup path: activate the persisted theme without signalling."""
        Styles.set_theme(self.saved_theme())

    def save_and_apply(self, name: str) -> None:
        QSettings().setValue(SETTINGS_THEME_KEY, name)
        self.set_theme(name)


theme_manager = ThemeManager()
