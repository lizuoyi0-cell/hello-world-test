"""Logging setup for taskman.

Provides a single ``configure_logging`` entry point that wires up a rotating
file handler plus a console handler. Logs every user action through the
``taskman`` logger hierarchy.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

DEFAULT_LOG_DIR = Path(os.environ.get("TASKMAN_LOG_DIR", Path.home() / ".taskman"))
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "taskman.log"

_configured = False


def configure_logging(level: int = logging.INFO, log_file: Path | None = None) -> logging.Logger:
    """Configure the root ``taskman`` logger.

    Safe to call multiple times; subsequent calls are no-ops so importing
    modules don't stack handlers.
    """
    global _configured
    logger = logging.getLogger("taskman")
    if _configured:
        return logger

    log_path = Path(log_file) if log_file else DEFAULT_LOG_FILE
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=512 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    console_handler.setLevel(logging.WARNING)
    logger.addHandler(console_handler)

    logger.propagate = False
    _configured = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``taskman`` namespace."""
    return logging.getLogger(f"taskman.{name}")
