"""
Structured JSON logging setup.
Uses python-json-logger to emit machine-parseable logs in production
and coloured human-readable logs in development.
"""
import logging
import sys

from pythonjsonlogger import jsonlogger

from core.config import settings


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Extend the default JSON formatter with extra standard fields."""

    def add_fields(
        self,
        log_record: dict,
        record: logging.LogRecord,
        message_dict: dict,
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["env"] = settings.APP_ENV


def setup_logging() -> None:
    """
    Configure root logger.

    - In development: simple text format to stdout.
    - In production / non-dev: structured JSON to stdout.
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)

    if settings.APP_ENV == "development":
        fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    else:
        formatter = CustomJsonFormatter(
            "%(asctime)s %(level)s %(logger)s %(message)s"
        )
        handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove any existing handlers to avoid duplicates when module is reloaded
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Silence noisy third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Call setup_logging() first."""
    return logging.getLogger(name)
