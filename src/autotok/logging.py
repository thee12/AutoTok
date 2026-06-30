"""Logging helpers for AutoTok."""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure standard-library logging for CLI and local runs."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
