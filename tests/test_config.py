from __future__ import annotations

from pathlib import Path

import pytest

from autotok.config import AppConfig, ConfigError


def test_config_uses_safe_defaults() -> None:
    config = AppConfig.from_environment({})

    assert config.environment == "local"
    assert config.log_level == "INFO"
    assert config.data_dir == Path("data")


def test_config_reads_environment_values() -> None:
    config = AppConfig.from_environment(
        {
            "AUTOTOK_ENV": "test",
            "AUTOTOK_LOG_LEVEL": "debug",
            "AUTOTOK_DATA_DIR": "tmp/autotok",
        }
    )

    assert config.environment == "test"
    assert config.log_level == "DEBUG"
    assert config.data_dir == Path("tmp/autotok")


def test_config_rejects_invalid_log_level() -> None:
    with pytest.raises(ConfigError, match="AUTOTOK_LOG_LEVEL"):
        AppConfig.from_environment({"AUTOTOK_LOG_LEVEL": "TRACE"})
