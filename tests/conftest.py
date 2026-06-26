"""Shared pytest fixtures for the test suite.

Sets the Qt platform to ``offscreen`` so widget/QObject construction and
QTimer activation work in headless test environments, and exposes a
session-scoped ``qapp`` fixture. A live ``QApplication`` is required for
``QTimer.start()`` to register (``isActive()`` returns ``False`` without one),
which the audio fade tests depend on.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    """Return a process-wide QApplication, creating it once per session."""
    QCoreApplication.setOrganizationName("SoundManagerTests")
    QCoreApplication.setApplicationName("SoundManagerTests")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
