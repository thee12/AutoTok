from __future__ import annotations

from pathlib import Path

import pytest

from autotok.config import AppConfig, ConfigError


def test_config_uses_safe_defaults() -> None:
    config = AppConfig.from_environment({})

    assert config.environment == "local"
    assert config.log_level == "INFO"
    assert config.data_dir == Path("data")
    assert config.reddit_oauth_token is None
    assert config.reddit_user_agent == "AutoTok/0.1 local-source-ingestion"
    assert config.reddit_timeout_seconds == 20


def test_config_reads_environment_values() -> None:
    config = AppConfig.from_environment(
        {
            "AUTOTOK_ENV": "test",
            "AUTOTOK_LOG_LEVEL": "debug",
            "AUTOTOK_DATA_DIR": "tmp/autotok",
            "AUTOTOK_REDDIT_OAUTH_TOKEN": " token ",
            "AUTOTOK_REDDIT_USER_AGENT": "AutoTok tests",
            "AUTOTOK_REDDIT_TIMEOUT_SECONDS": "9",
        }
    )

    assert config.environment == "test"
    assert config.log_level == "DEBUG"
    assert config.data_dir == Path("tmp/autotok")
    assert config.reddit_oauth_token == "token"
    assert config.reddit_user_agent == "AutoTok tests"
    assert config.reddit_timeout_seconds == 9


def test_config_applies_cli_data_dir_override() -> None:
    config = AppConfig.from_environment({"AUTOTOK_DATA_DIR": "data"}).with_overrides(
        data_dir=Path("other-data")
    )

    assert config.data_dir == Path("other-data")


def test_config_rejects_invalid_log_level() -> None:
    with pytest.raises(ConfigError, match="AUTOTOK_LOG_LEVEL"):
        AppConfig.from_environment({"AUTOTOK_LOG_LEVEL": "TRACE"})


def test_config_rejects_invalid_reddit_timeout() -> None:
    with pytest.raises(ConfigError, match="AUTOTOK_REDDIT_TIMEOUT_SECONDS"):
        AppConfig.from_environment({"AUTOTOK_REDDIT_TIMEOUT_SECONDS": "0"})
