"""Logging utilities."""

import logging
import os


def setup_logger(name: str) -> logging.Logger:
    """Create a configured logger."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    return logging.getLogger(name)
