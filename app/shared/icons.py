"""Icon library helper for bundled SVGs"""

from pathlib import Path

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from .styles import Styles

# Logical pixel size icons are rasterized at (2x for high-DPI displays).
_RENDER_SIZE = 24
_DEVICE_PIXEL_RATIO = 2.0


class IconLibrary:
    """Load icons from a local icon set directory, tinted to a palette color.

    SVGs in the icon set use ``currentColor``; ``icon()`` substitutes the
    requested color (defaulting to the active theme's muted text color) at
    render time, so no color values live in the asset files.
    """

    _cache: dict[tuple[Path, str, str], QIcon] = {}

    def __init__(self, icon_set: str = "feather", root: Path | None = None):
        if root is None:
            root = (
                Path(__file__).resolve().parent.parent / "assets" / "icons" / icon_set
            )
        self.root = root

    def icon(self, name: str, color: str | None = None) -> QIcon:
        """Return a QIcon tinted with color (default: theme muted text)."""
        tint = color or Styles.TEXT_MUTED
        key = (self.root, name, tint)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        path = self.root / f"{name}.svg"
        if not path.exists():
            return QIcon()
        svg = path.read_text(encoding="utf-8").replace("currentColor", tint)

        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        size = int(_RENDER_SIZE * _DEVICE_PIXEL_RATIO)
        pixmap = QPixmap(size, size)
        pixmap.setDevicePixelRatio(_DEVICE_PIXEL_RATIO)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()

        result = QIcon(pixmap)
        self._cache[key] = result
        return result
