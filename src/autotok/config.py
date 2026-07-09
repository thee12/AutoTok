"""Application configuration for AutoTok."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from autotok.errors import ConfigurationError

DEFAULT_ENVIRONMENT = "local"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FORMAT = "text"
DEFAULT_DATA_DIR = Path("data")
DEFAULT_TTS_PROVIDER = "local_wav"
DEFAULT_TTS_TIMEOUT_SECONDS = 30
DEFAULT_REDDIT_USER_AGENT = "AutoTok/0.1 local-source-ingestion"
DEFAULT_REDDIT_TIMEOUT_SECONDS = 20
VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
VALID_LOG_FORMATS = {"text", "json"}
VALID_TTS_PROVIDERS = {"local_wav", "pyttsx3"}


class ConfigError(ConfigurationError):
    """Raised when configuration cannot be loaded or validated."""


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Validated application configuration.

    Precedence is command-line overrides, then environment variables, then safe
    built-in defaults.
    """

    environment: str = DEFAULT_ENVIRONMENT
    log_level: str = DEFAULT_LOG_LEVEL
    log_format: str = DEFAULT_LOG_FORMAT
    data_dir: Path = DEFAULT_DATA_DIR
    tts_provider: str = DEFAULT_TTS_PROVIDER
    tts_timeout_seconds: int = DEFAULT_TTS_TIMEOUT_SECONDS
    reddit_oauth_token: str | None = None
    reddit_user_agent: str = DEFAULT_REDDIT_USER_AGENT
    reddit_timeout_seconds: int = DEFAULT_REDDIT_TIMEOUT_SECONDS

    @classmethod
    def from_environment(cls, environ: dict[str, str] | None = None) -> AppConfig:
        """Load configuration from environment variables and defaults."""
        source = os.environ if environ is None else environ
        token = source.get("AUTOTOK_REDDIT_OAUTH_TOKEN")
        config = cls(
            environment=source.get("AUTOTOK_ENV", DEFAULT_ENVIRONMENT).strip()
            or DEFAULT_ENVIRONMENT,
            log_level=source.get("AUTOTOK_LOG_LEVEL", DEFAULT_LOG_LEVEL).strip().upper(),
            log_format=source.get("AUTOTOK_LOG_FORMAT", DEFAULT_LOG_FORMAT).strip().lower()
            or DEFAULT_LOG_FORMAT,
            data_dir=Path(source.get("AUTOTOK_DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser(),
            tts_provider=source.get("AUTOTOK_TTS_PROVIDER", DEFAULT_TTS_PROVIDER).strip()
            or DEFAULT_TTS_PROVIDER,
            tts_timeout_seconds=_parse_int(
                source.get("AUTOTOK_TTS_TIMEOUT_SECONDS"),
                default=DEFAULT_TTS_TIMEOUT_SECONDS,
                name="AUTOTOK_TTS_TIMEOUT_SECONDS",
            ),
            reddit_oauth_token=token.strip() if token is not None and token.strip() else None,
            reddit_user_agent=source.get(
                "AUTOTOK_REDDIT_USER_AGENT", DEFAULT_REDDIT_USER_AGENT
            ).strip()
            or DEFAULT_REDDIT_USER_AGENT,
            reddit_timeout_seconds=_parse_int(
                source.get("AUTOTOK_REDDIT_TIMEOUT_SECONDS"),
                default=DEFAULT_REDDIT_TIMEOUT_SECONDS,
                name="AUTOTOK_REDDIT_TIMEOUT_SECONDS",
            ),
        )
        config.validate()
        return config

    def with_overrides(
        self,
        *,
        data_dir: Path | None = None,
        tts_provider: str | None = None,
        tts_timeout_seconds: int | None = None,
    ) -> AppConfig:
        """Return a validated copy with command-line overrides applied."""
        config = replace(
            self,
            data_dir=self.data_dir if data_dir is None else data_dir.expanduser(),
            tts_provider=self.tts_provider if tts_provider is None else tts_provider,
            tts_timeout_seconds=(
                self.tts_timeout_seconds if tts_timeout_seconds is None else tts_timeout_seconds
            ),
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
        if self.log_format not in VALID_LOG_FORMATS:
            allowed = ", ".join(sorted(VALID_LOG_FORMATS))
            raise ConfigError(f"AUTOTOK_LOG_FORMAT must be one of: {allowed}.")
        if not str(self.data_dir):
            raise ConfigError("AUTOTOK_DATA_DIR must not be empty.")
        if self.tts_provider not in VALID_TTS_PROVIDERS:
            allowed = ", ".join(sorted(VALID_TTS_PROVIDERS))
            raise ConfigError(f"AUTOTOK_TTS_PROVIDER must be one of: {allowed}.")
        if self.tts_timeout_seconds <= 0:
            raise ConfigError("AUTOTOK_TTS_TIMEOUT_SECONDS must be greater than zero.")
        if not self.reddit_user_agent:
            raise ConfigError("AUTOTOK_REDDIT_USER_AGENT must not be empty.")
        if self.reddit_timeout_seconds <= 0:
            raise ConfigError("AUTOTOK_REDDIT_TIMEOUT_SECONDS must be greater than zero.")


def _parse_int(value: str | None, *, default: int, name: str) -> int:
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer.") from exc
