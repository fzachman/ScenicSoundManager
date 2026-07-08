"""Tests for the shared logging configuration.

Pins the sink routing: the full info+ stream goes to the log file, while the
console (stderr) only receives warning+ — routine events (e.g. one per remote
command) must not flood a terminal run of the app.
"""

import logging

import pytest
import structlog
from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

import app.shared.logging as app_logging


class _QtContext:
    category = "default"


@pytest.fixture
def log_file(tmp_path, monkeypatch, capsys):
    """configure_logging() against a temp dir, fully undone afterwards.

    capsys is requested here (not just in tests) so pytest's sys.stderr
    replacement is in place BEFORE configure_logging binds its console
    handler to sys.stderr.
    """
    monkeypatch.setattr(app_logging, "LOG_DIR", tmp_path)
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    # Detach (don't close) pre-existing handlers — e.g. pytest's log capture —
    # so configure_logging's close-on-reconfigure loop can't break them.
    root.handlers.clear()

    app_logging.configure_logging()
    yield tmp_path / app_logging.LOG_FILE_NAME

    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    root.handlers.extend(saved_handlers)
    root.setLevel(saved_level)
    structlog.reset_defaults()
    qInstallMessageHandler(None)


def test_info_goes_to_file_not_console(log_file, capsys):
    app_logging.get_logger("test.module").info("info_event", foo=1)
    contents = log_file.read_text()
    assert "info_event" in contents
    assert "test.module" in contents
    assert "foo=1" in contents
    assert "info_event" not in capsys.readouterr().err


def test_warning_reaches_console_too(log_file, capsys):
    app_logging.get_logger("test.module").warning("warning_event")
    assert "warning_event" in log_file.read_text()
    assert "warning_event" in capsys.readouterr().err


def test_qt_warnings_go_to_file_not_console(log_file, capsys):
    # Qt library noise (e.g. QWebSocket's destructor wildcard-disconnect
    # warnings on every quit with a connected remote client) must not reach
    # the user's console — but stays diagnosable in the file.
    app_logging._qt_message_handler(
        QtMsgType.QtWarningMsg, _QtContext(), "wildcard call disconnects"
    )
    assert "wildcard call disconnects" in log_file.read_text()
    assert "wildcard" not in capsys.readouterr().err


def test_qt_critical_reaches_console(log_file, capsys):
    app_logging._qt_message_handler(
        QtMsgType.QtCriticalMsg, _QtContext(), "qt exploded"
    )
    assert "qt exploded" in log_file.read_text()
    assert "qt exploded" in capsys.readouterr().err
