"""Application configuration for AutoTok."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from autotok.errors import ConfigurationError

DEFAULT_ENVIRONMENT = "local"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_DATA_DIR = Path("data")
VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


class ConfigError(ConfigurationError):
    """Raised when configuration cannot be loaded or validated."""


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Validated application configuration.

    Phase 0 intentionally keeps configuration small. Precedence is environment
    variables first, then safe built-in defaults.
    """

    environment: str = DEFAULT_ENVIRONMENT
    log_level: str = DEFAULT_LOG_LEVEL
    data_dir: Path = DEFAULT_DATA_DIR

    @classmethod
    def from_environment(cls, environ: dict[str, str] | None = None) -> AppConfig:
        """Load configuration from environment variables and defaults."""
        source = os.environ if environ is None else environ
        config = cls(
            environment=source.get("AUTOTOK_ENV", DEFAULT_ENVIRONMENT).strip()
            or DEFAULT_ENVIRONMENT,
            log_level=source.get("AUTOTOK_LOG_LEVEL", DEFAULT_LOG_LEVEL).strip().upper(),
            data_dir=Path(source.get("AUTOTOK_DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser(),
        )
        config.validate()
        return config

    def validate(self) -> None:
        """Validate configuration values and raise actionable errors."""
        if not self.environment:
            raise ConfigError("AUTOTOK_ENV must not be empty.")
        if self.log_level not in VALID_LOG_LEVELS:
            allowed = ", ".join(sorted(VALID_LOG_LEVELS))
            raise ConfigError(f"AUTOTOK_LOG_LEVEL must be one of: {allowed}.")
        if not str(self.data_dir):
            raise ConfigError("AUTOTOK_DATA_DIR must not be empty.")
