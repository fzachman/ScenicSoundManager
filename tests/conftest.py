"""Shared pytest fixtures for the test suite.

Sets the Qt platform to ``offscreen`` so widget/QObject construction and
QTimer activation work in headless test environments, and exposes a
session-scoped ``qapp`` fixture. A live ``QApplication`` is required for
``QTimer.start()`` to register (``isActive()`` returns ``False`` without one),
which the audio fade tests depend on.
"""

import gc
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QCoreApplication, QSettings
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Return a process-wide QApplication, creating it once per session."""
    QCoreApplication.setOrganizationName("SoundManagerTests")
    QCoreApplication.setApplicationName("SoundManagerTests")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    # Keep MainWindow-constructing tests from each binding the real remote-
    # control port (8765). Written to the SoundManagerTests settings namespace
    # only; tests that exercise the wiring re-enable it with an ephemeral port.
    settings = QSettings()
    settings.beginGroup("remote")
    settings.setValue("enabled", False)
    settings.endGroup()
    return app


@pytest.fixture(autouse=True)
def _deterministic_qt_teardown(qapp):
    """Destroy leftover Qt objects at the test boundary, not mid-test.

    Without this, a Qt object from a finished test (a QWebSocket, or any
    widget still connected to theme_manager.theme_changed) can be garbage-
    collected while a later test is mid-emit or constructing widgets;
    C++-side destruction during an arbitrary GC pass aborts the process
    ("Fatal Python error: Aborted"). Pump pending deleteLater events and
    collect while the loop is idle instead.
    """
    yield
    qapp.processEvents()
    gc.collect()
    qapp.processEvents()
