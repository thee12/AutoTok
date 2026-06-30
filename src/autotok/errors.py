"""Application exception hierarchy."""

from __future__ import annotations


class AutoTokError(Exception):
    """Base class for expected AutoTok application errors."""


class ConfigurationError(AutoTokError):
    """Raised when configuration is missing, invalid, or unsafe."""


class UserInputError(AutoTokError):
    """Raised when user-provided input is invalid."""


class DependencyError(AutoTokError):
    """Raised when a required local dependency is unavailable."""
