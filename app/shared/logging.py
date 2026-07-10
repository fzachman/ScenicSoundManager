"""Shared structlog configuration for SoundManager"""

import logging
import logging.handlers
import sys
from pathlib import Path

import structlog
from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

LOG_DIR = Path.home() / "Library" / "Logs" / "SoundManager"
LOG_FILE_NAME = "soundmanager.log"

_MAX_LOG_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3

# Qt severity -> structlog method. QtWarningMsg maps to info deliberately:
# Qt warns liberally about library internals the app can't act on (e.g.
# QWebSocket's destructor emits "QObject::disconnect: wildcard call
# disconnects from destroyed signal of ..." for every once-connected socket),
# and printing those to the user's console makes the app look broken. They
# stay in the log file; genuine Qt problems arrive as critical/fatal and
# still reach the console.
_QT_LEVEL_METHOD = {
    QtMsgType.QtDebugMsg: "debug",
    QtMsgType.QtInfoMsg: "info",
    QtMsgType.QtWarningMsg: "info",
    QtMsgType.QtCriticalMsg: "warning",
    QtMsgType.QtFatalMsg: "error",
}


def _qt_message_handler(msg_type, context, message) -> None:
    """Route Qt's own messages into structlog instead of raw stderr."""
    try:
        method = _QT_LEVEL_METHOD.get(msg_type, "warning")
        getattr(structlog.get_logger("qt"), method)(
            "qt_message", message=message, category=context.category
        )
    except Exception:  # noqa: BLE001 - never raise back into Qt's C++ caller
        pass


def configure_logging() -> None:
    """Configure structlog for the application.

    Call once at startup before any loggers are created.

    The full stream (info+) goes to ``~/Library/Logs/SoundManager/`` with
    size-based rotation; the console (stderr) only gets warning+ so terminal
    runs aren't flooded by routine events but real problems stay visible.
    Qt's own messages are routed through the same pipeline (see
    ``_QT_LEVEL_METHOD``) instead of being printed raw to stderr.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Shared shape for both sinks; also applied to any stdlib-originated
    # records so third-party log lines come out in the same format.
    pre_chain: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    structlog.configure(
        processors=[
            *pre_chain,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    def formatter(colors: bool) -> structlog.stdlib.ProcessorFormatter:
        return structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=colors),
            ],
            foreign_pre_chain=pre_chain,
        )

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / LOG_FILE_NAME,
        maxBytes=_MAX_LOG_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter(colors=False))

    root = logging.getLogger()
    # Close (not just drop) existing handlers so reconfiguration never leaks
    # open file descriptors.
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    root.addHandler(file_handler)
    root.setLevel(logging.INFO)

    # A py2app windowed build can run without usable std streams.
    if sys.stderr is not None:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(formatter(colors=True))
        root.addHandler(console_handler)

    qInstallMessageHandler(_qt_message_handler)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a configured structlog logger.

    Args:
        name: Optional logger name, typically the module name (__name__).
    """
    if name:
        # Positional arg names the underlying stdlib logger (per-module level
        # control, Console.app filtering); logger_name keeps the module tag
        # visible in the rendered line, as before.
        return structlog.get_logger(name, logger_name=name)
    return structlog.get_logger()
