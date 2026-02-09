"""Shared structlog configuration for SoundManager"""

import structlog


def configure_logging() -> None:
    """Configure structlog for the application.

    Call once at startup before any loggers are created.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a configured structlog logger.

    Args:
        name: Optional logger name, typically the module name (__name__).
    """
    return structlog.get_logger(logger_name=name) if name else structlog.get_logger()
