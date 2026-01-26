"""Icon library helper for bundled SVGs"""

from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QIcon


class IconLibrary:
    """Load icons from a local icon set directory"""

    def __init__(self, icon_set: str = "feather", root: Optional[Path] = None):
        if root is None:
            root = Path(__file__).resolve().parent.parent / "assets" / "icons" / icon_set
        self.root = root

    def icon(self, name: str) -> QIcon:
        """Return a QIcon for the given icon name"""
        return QIcon(str(self.root / f"{name}.svg"))
