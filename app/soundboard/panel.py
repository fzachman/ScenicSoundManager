"""Soundboard dock shell: collapsible, resizable, pop-out-able panel.

The dock is a permanent fixture below the main content (a peer of the top
bar, not a tab). It collapses to a single title-bar line, resizes by dragging
the separator above it, and pops out into a normal window via the title-bar
button. It can never be closed away entirely — closing the popped-out window
re-docks it instead.
"""

from PyQt6.QtCore import QRect, QSettings, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWIDGETSIZE_MAX,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..shared.icons import IconLibrary
from ..shared.styles import Styles
from ..shared.theme import theme_manager


class SoundboardTitleBar(QWidget):
    """Single-line dock title bar: title, collapse arrow, pop-out button.

    Deliberately minimal and identical collapsed/expanded — all board
    controls live inside the panel content, never here.
    """

    collapse_toggle_requested = pyqtSignal()
    popout_toggle_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("soundboardTitleBar")
        self._icons = IconLibrary()
        self._collapsed = False
        self._floating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 6, 12, 6)
        layout.setSpacing(8)

        self._title_label = QLabel("Soundboard")
        layout.addWidget(self._title_label)
        layout.addStretch()

        self.collapse_btn = self._make_button()
        self.collapse_btn.clicked.connect(self.collapse_toggle_requested)
        layout.addWidget(self.collapse_btn)

        self.popout_btn = self._make_button()
        self.popout_btn.clicked.connect(self.popout_toggle_requested)
        layout.addWidget(self.popout_btn)

        self._apply_theme_styles()
        theme_manager.theme_changed.connect(self._apply_theme_styles)

    def _make_button(self) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(24, 24)
        # NoFocus so a clicked button doesn't swallow the Space transport key.
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _apply_theme_styles(self) -> None:
        """Apply palette-dependent styles; re-run on theme change."""
        self.setStyleSheet(Styles.dock_title_bar_style("QWidget#soundboardTitleBar"))
        self._title_label.setStyleSheet(Styles.title_style(size=13))
        for btn in (self.collapse_btn, self.popout_btn):
            btn.setStyleSheet(Styles.compact_icon_button_style())
        # Icons are rasterized with a baked palette color: re-render them for
        # the current state without changing it.
        self.set_collapsed(self._collapsed)
        self.set_floating(self._floating)

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        # The dock sits at the bottom of the window: expanding grows upward.
        icon = "chevron-up" if collapsed else "chevron-down"
        self.collapse_btn.setIcon(self._icons.icon(icon))
        self.collapse_btn.setToolTip("Expand" if collapsed else "Collapse")

    def set_floating(self, floating: bool) -> None:
        self._floating = floating
        # Collapse is a docked-only affordance; a floating window resizes freely.
        self.collapse_btn.setVisible(not floating)
        icon = "minimize-2" if floating else "maximize-2"
        self.popout_btn.setIcon(self._icons.icon(icon))
        self.popout_btn.setToolTip("Return to main window" if floating else "Pop out")


class SoundboardDock(QDockWidget):
    """Dock shell for the soundboard: hosts the given content widget."""

    SETTINGS_GROUP = "soundboard"
    SETTINGS_COLLAPSED = "collapsed"
    SETTINGS_EXPANDED_HEIGHT = "expanded_height"
    SETTINGS_POPOUT_INITIALIZED = "popout_initialized"
    DEFAULT_EXPANDED_HEIGHT = 240
    DEFAULT_POPOUT_WIDTH_FRACTION = 0.7

    def __init__(self, content: QWidget | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        # objectName is required for QMainWindow.saveState() to include this
        # dock; without it the height/floating geometry silently isn't saved.
        self.setObjectName("soundboardDock")
        self.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        # Floatable only: no close button (the panel is permanent) and no
        # drag-to-move (pop-out goes through the title-bar button).
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetFloatable)

        self._title_bar = SoundboardTitleBar(self)
        self.setTitleBarWidget(self._title_bar)
        self._title_bar.collapse_toggle_requested.connect(self.toggle_collapsed)
        self._title_bar.popout_toggle_requested.connect(self._toggle_floating)
        self.topLevelChanged.connect(self._title_bar.set_floating)

        self._placeholder_label: QLabel | None = None
        self.setWidget(content if content is not None else self._build_placeholder())
        self._apply_theme_styles()
        theme_manager.theme_changed.connect(self._apply_theme_styles)

        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        self._collapsed = settings.value(
            self.SETTINGS_COLLAPSED, defaultValue=False, type=bool
        )
        self._expanded_height = settings.value(
            self.SETTINGS_EXPANDED_HEIGHT,
            defaultValue=self.DEFAULT_EXPANDED_HEIGHT,
            type=int,
        )
        settings.endGroup()
        self._apply_collapsed()

    def _build_placeholder(self) -> QWidget:
        """Fallback content when none is supplied (tests, tooling)."""
        content = QWidget()
        layout = QVBoxLayout(content)
        label = QLabel("Soundboard coming soon")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        self._placeholder_label = label
        return content

    def _apply_theme_styles(self) -> None:
        """Apply palette-dependent styles; re-run on theme change."""
        if self._placeholder_label is not None:
            self._placeholder_label.setStyleSheet(Styles.subtle_text_style(size=12))

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        if (
            collapsed
            and not self.isFloating()
            and self.isVisible()
            and self.height() > self._title_bar.sizeHint().height()
        ):
            self._expanded_height = self.height()
        self._collapsed = collapsed
        self._apply_collapsed()
        self._save_settings()
        if not collapsed:
            self._restore_expanded_height()

    def _apply_collapsed(self) -> None:
        content = self.widget()
        if content is not None:
            # Collapse by pinning the content to zero height rather than
            # hiding it: with the content widget hidden, QDockWidget's layout
            # caps the dock's maximum width at the title bar's sizeHint, so
            # the dock area stops stretching it full-width (and the title-bar
            # stretch collapses, pulling the buttons next to the title).
            content.setMaximumHeight(0 if self._collapsed else QWIDGETSIZE_MAX)
        if self._collapsed:
            # Pin to the title-bar line; min == max also disables the
            # separator drag while collapsed.
            height = self._title_bar.sizeHint().height()
            self.setMinimumHeight(height)
            self.setMaximumHeight(height)
        else:
            self.setMinimumHeight(self._title_bar.sizeHint().height())
            self.setMaximumHeight(QWIDGETSIZE_MAX)
        self._title_bar.set_collapsed(self._collapsed)

    def _restore_expanded_height(self) -> None:
        if self.isFloating():
            self.resize(self.width(), self._expanded_height)
            return
        window = self.parentWidget()
        if isinstance(window, QMainWindow):
            window.resizeDocks([self], [self._expanded_height], Qt.Orientation.Vertical)

    def _toggle_floating(self) -> None:
        if not self.isFloating() and self._collapsed:
            # A popped-out bare title strip is useless; expand first.
            self.set_collapsed(False)
        will_float = not self.isFloating()
        self.setFloating(will_float)
        if will_float:
            self._apply_first_popout_geometry()

    def _apply_first_popout_geometry(self) -> None:
        """Give the first-ever pop-out a distinct size and position.

        Qt floats a dock at its docked footprint (full window width, same
        spot), which is indistinguishable from staying docked. With no stored
        preference, size it to a fraction of the main window and center it
        over the window so it clearly reads as a new window. After this once,
        Qt and saveState/restoreState own the floating geometry.
        """
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        initialized = settings.value(
            self.SETTINGS_POPOUT_INITIALIZED, defaultValue=False, type=bool
        )
        if not initialized:
            window = self.parentWidget()
            if isinstance(window, QMainWindow):
                geometry = QRect(
                    0,
                    0,
                    int(window.width() * self.DEFAULT_POPOUT_WIDTH_FRACTION),
                    self._expanded_height + self._title_bar.sizeHint().height(),
                )
                geometry.moveCenter(window.geometry().center())
                self.setGeometry(geometry)
            settings.setValue(self.SETTINGS_POPOUT_INITIALIZED, True)
        settings.endGroup()

    def closeEvent(self, event):
        """A floating soundboard re-docks on close; it can't be closed away."""
        if self.isFloating():
            event.ignore()
            self.setFloating(False)
            return
        super().closeEvent(event)

    def _save_settings(self) -> None:
        settings = QSettings()
        settings.beginGroup(self.SETTINGS_GROUP)
        settings.setValue(self.SETTINGS_COLLAPSED, self._collapsed)
        settings.setValue(self.SETTINGS_EXPANDED_HEIGHT, self._expanded_height)
        settings.endGroup()
