"""Logging setup using loguru.

Call `setup_logging()` once at startup, then `from loguru import logger` anywhere.
Env vars: LOG_LEVEL (default INFO); LOG_JSON=true emits one JSON object per line
(useful for log aggregators).
"""

import os
import sys

from loguru import logger


def setup_logging() -> None:
    """Replace loguru's default sink with one driven by environment variables."""
    level = os.getenv("LOG_LEVEL", "INFO")
    logger.remove()
    if os.getenv("LOG_JSON", "false").lower() == "true":
        logger.add(sys.stdout, level=level, serialize=True)
    else:
        logger.add(
            sys.stdout,
            level=level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
                "<cyan>{name}</cyan> | {message} | {extra}"
            ),
        )
