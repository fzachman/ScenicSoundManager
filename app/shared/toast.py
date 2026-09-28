"""Non-blocking confirmation toast.

A pill that fades in near the bottom of its host widget, holds, then fades
out. It never takes focus and mouse events pass through it, so the user can
keep working (e.g. arrow to the next library row and preview it) while it
shows. A new message replaces the current one and restarts the hold.
"""

import html

from PyQt6.QtCore import QEvent, QPropertyAnimation, Qt, QTimer
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

from .styles import Styles
from .theme import theme_manager


class Toast(QLabel):
    HOLD_MS = 2500
    FADE_IN_MS = 150
    FADE_OUT_MS = 400
    BOTTOM_MARGIN = 40  # clears a hint line along the host's bottom edge
    SIDE_MARGIN = 24

    def __init__(self, host: QWidget):
        super().__init__(host)
        self._message = ""
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.finished.connect(self._on_fade_finished)
        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.timeout.connect(self._fade_out)

        host.installEventFilter(self)
        self.hide()
        self._apply_theme_styles()
        theme_manager.theme_changed.connect(self._apply_theme_styles)

    def message(self) -> str:
        """The plain-text message last shown."""
        return self._message

    def show_message(self, message: str) -> None:
        self._message = message
        self._render()
        self.raise_()
        self.show()
        self._animate_to(1.0, self.FADE_IN_MS)
        self._hold.start(self.HOLD_MS)

    def _render(self) -> None:
        check = f'<span style="color: {Styles.SUCCESS};">✓</span>'
        self.setText(f"{check}&nbsp;&nbsp;{html.escape(self._message)}")
        self.setWordWrap(False)
        self.adjustSize()
        host = self.parentWidget()
        limit = host.width() - 2 * self.SIDE_MARGIN if host else 0
        if 0 < limit < self.width():
            # Long names wrap instead of running off the host's edges.
            self.setWordWrap(True)
            self.resize(limit, self.heightForWidth(limit))
        self._reposition()

    def _reposition(self) -> None:
        host = self.parentWidget()
        if host is None:
            return
        x = (host.width() - self.width()) // 2
        y = host.height() - self.height() - self.BOTTOM_MARGIN
        self.move(max(x, 0), max(y, 0))

    def _animate_to(self, opacity: float, duration_ms: int) -> None:
        self._fade.stop()
        self._fade.setDuration(duration_ms)
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(opacity)
        self._fade.start()

    def _fade_out(self) -> None:
        self._animate_to(0.0, self.FADE_OUT_MS)

    def _on_fade_finished(self) -> None:
        if self._opacity.opacity() <= 0.0:
            self.hide()

    def eventFilter(self, obj, event):
        if obj is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self._reposition()
        return super().eventFilter(obj, event)

    def _apply_theme_styles(self) -> None:
        """Re-apply palette-dependent styles; connected to theme_changed."""
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {Styles.BACKGROUND_LIGHTER};
                color: {Styles.TEXT};
                border: 1px solid {Styles.BORDER};
                border-radius: 16px;
                padding: 8px 18px;
                font-size: 13px;
                font-weight: 600;
            }}
        """)
        if self._message:
            self._render()  # the ✓ color is baked into the rich text
