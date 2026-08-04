"""Icon library helper for bundled SVGs"""

import tempfile
from pathlib import Path

from PyQt6.QtGui import QIcon

from .styles import Styles


class IconLibrary:
    """Load icons from a local icon set directory, tinted to a palette color.

    SVGs in the icon set use ``currentColor``; ``icon()`` substitutes the
    requested color (defaulting to the active theme's muted text color),
    writes the tinted copy to a per-process temp dir, and returns a QIcon
    backed by that SVG file. Backing the icon with an SVG file (rather than
    a pre-rendered pixmap) keeps Qt's SVG icon engine, which renders at
    whatever size each widget requests (setIconSize, HiDPI) — a fixed
    pixmap ignores the requested size on 2x displays and overflows buttons.
    """

    _cache: dict[tuple[Path, str, str], QIcon] = {}
    _tint_dir: Path | None = None

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

        if IconLibrary._tint_dir is None:
            IconLibrary._tint_dir = Path(tempfile.mkdtemp(prefix="soundmanager-icons-"))
        tinted_path = (
            IconLibrary._tint_dir / f"{self.root.name}-{name}-{tint.lstrip('#')}.svg"
        )
        # QIcon renders lazily, so the file must outlive this call; it lives
        # for the whole process (the temp dir is never cleaned mid-run).
        if not tinted_path.exists():
            tinted_path.write_text(svg, encoding="utf-8")

        result = QIcon(str(tinted_path))
        self._cache[key] = result
        return result
