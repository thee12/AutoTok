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


class PersistenceError(AutoTokError):
    """Raised when local artifact storage cannot be read or written."""


class ProviderError(AutoTokError):
    """Raised when an audio or AI provider request fails safely."""


class RenderError(AutoTokError):
    """Raised when local video rendering or render validation fails."""


class UnsupportedMediaError(AutoTokError):
    """Raised when a local media file is missing, invalid, or unsupported."""
