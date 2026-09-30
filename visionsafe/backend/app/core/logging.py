"""
Structured application logging configuration.

Uses Python's standard logging with a structured format.
JSON-compatible in production; human-readable in development.
"""

import logging
import sys
from app.core.config import settings


def configure_logging() -> None:
    """Configure root logger once at application startup."""
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    fmt = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        if settings.ENVIRONMENT == "development"
        else "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
        force=True,
    )

    # Reduce noise from chatty libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("ultralytics").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured | level=%s environment=%s",
        settings.LOG_LEVEL,
        settings.ENVIRONMENT,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Use this throughout the codebase."""
    return logging.getLogger(name)
