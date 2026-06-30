from __future__ import annotations

import json
from typing import Any

import pytest

from autotok.cli import main


def test_doctor_outputs_human_summary(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["doctor"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "AutoTok diagnostic: ok" in captured.out
    assert "Version:" in captured.out


def test_doctor_outputs_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["doctor", "--json"])

    captured = capsys.readouterr()
    payload: dict[str, Any] = json.loads(captured.out)
    assert exit_code == 0
    assert payload["application"] == "autotok"
    assert payload["status"] == "ok"


def test_invalid_log_level_returns_configuration_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AUTOTOK_LOG_LEVEL", "LOUD")

    exit_code = main(["doctor"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Configuration error:" in captured.err
    assert "AUTOTOK_LOG_LEVEL" in captured.err
