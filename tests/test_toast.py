"""Tests for the non-blocking confirmation Toast."""

import pytest
from PyQt6.QtCore import QAbstractAnimation, QPoint, Qt
from PyQt6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from app.shared.toast import Toast


@pytest.fixture
def host(qapp):
    host = QWidget()
    QVBoxLayout(host).addWidget(QLineEdit())  # something that can hold focus
    host.resize(600, 400)
    host.show()
    qapp.processEvents()
    yield host
    host.close()


def _finish_fade(toast):
    toast._fade.setCurrentTime(toast._fade.duration())


class TestToast:
    def test_message_shows_and_fades_in(self, host):
        toast = Toast(host)

        toast.show_message("Added to playlist “Battle Mix”")

        assert toast.isVisible()
        assert toast.message() == "Added to playlist “Battle Mix”"
        assert "Battle Mix" in toast.text()
        assert toast._fade.state() == QAbstractAnimation.State.Running
        assert toast._fade.endValue() == 1.0
        assert toast._hold.isActive()

    def test_never_takes_focus_or_mouse_events(self, host, qapp):
        editor = host.findChild(QLineEdit)
        editor.setFocus()
        qapp.processEvents()
        toast = Toast(host)

        toast.show_message("Added")
        qapp.processEvents()

        assert editor.hasFocus()
        assert toast.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert toast.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # Hit-testing skips it, so clicks land on whatever lies beneath.
        assert host.childAt(toast.geometry().center()) is not toast

    def test_hold_timeout_fades_out_then_hides(self, host):
        toast = Toast(host)
        toast.show_message("Added")
        _finish_fade(toast)

        toast._hold.timeout.emit()
        assert toast._fade.endValue() == 0.0
        _finish_fade(toast)

        assert not toast.isVisible()

    def test_new_message_replaces_text_and_restarts_hold(self, host):
        toast = Toast(host)
        toast.show_message("First")
        _finish_fade(toast)
        toast._hold.timeout.emit()  # fading out...

        toast.show_message("Second")

        assert toast.message() == "Second"
        assert toast._fade.endValue() == 1.0  # fading back in, not out
        assert toast._hold.isActive()

    def test_sits_bottom_center_and_follows_resizes(self, host, qapp):
        toast = Toast(host)
        toast.show_message("Added")

        def assert_placed():
            center_x = toast.geometry().center().x()
            assert abs(center_x - host.width() // 2) <= 1
            assert toast.geometry().bottom() == (
                host.height() - Toast.BOTTOM_MARGIN - 1
            )

        assert_placed()
        host.resize(800, 500)
        qapp.processEvents()
        assert_placed()

    def test_long_message_wraps_inside_the_host(self, host):
        toast = Toast(host)

        toast.show_message("Added to playlist “" + "Very Long Name " * 20 + "”")

        assert toast.wordWrap()
        assert toast.width() <= host.width() - 2 * Toast.SIDE_MARGIN
        assert toast.geometry().left() >= 0
        assert host.rect().contains(toast.geometry().topLeft() + QPoint(1, 1))

    def test_message_text_is_escaped(self, host):
        toast = Toast(host)

        toast.show_message("Added to playlist “<b>Loud</b>”")

        assert "&lt;b&gt;" in toast.text()
