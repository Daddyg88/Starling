"""
Logging: writes STARLING's diary into the logs folder.

    logs/starling.log   - everything that happens
    logs/errors.log  - only problems (easy to send me when something breaks)
"""

import logging
import sys
from logging.handlers import RotatingFileHandler

from core import paths

_ROOT_NAME = "starling"
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(level_name="INFO", logs_dir=None):
    """Set up logging once. Calling it again does nothing harmful."""
    logger = logging.getLogger(_ROOT_NAME)
    if getattr(logger, "_starling_ready", False):
        return logger

    level = getattr(logging, str(level_name).upper(), logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    folder = logs_dir or paths.LOGS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_FORMAT)

    # Log files are capped at about 1 MB each (3 old copies kept),
    # so they can never quietly fill up your hard drive.
    main_file = RotatingFileHandler(
        folder / "starling.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    main_file.setFormatter(formatter)
    logger.addHandler(main_file)

    error_file = RotatingFileHandler(
        folder / "errors.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    error_file.setLevel(logging.ERROR)
    error_file.setFormatter(formatter)
    logger.addHandler(error_file)

    # Warnings and errors also show in the window.
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING)
    console.setFormatter(formatter)
    logger.addHandler(console)

    logger._starling_ready = True
    return logger


def get_logger(name):
    """Get a logger for one part of STARLING, e.g. get_logger('database')."""
    return logging.getLogger("%s.%s" % (_ROOT_NAME, name))


def shutdown_logging():
    """Close the log files (needed so the files can be moved or deleted)."""
    logger = logging.getLogger(_ROOT_NAME)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    logger._starling_ready = False
