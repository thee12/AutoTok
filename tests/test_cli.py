from __future__ import annotations

import json
from pathlib import Path
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


def test_story_import_and_inspect_text_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"

    import_exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "story",
            "import",
            "--text",
            "  My local story.  ",
            "--title",
            "Example",
            "--json",
        ]
    )

    imported = json.loads(capsys.readouterr().out)
    story_id = imported["story_id"]
    assert import_exit_code == 0
    assert imported["created"] is True
    assert imported["normalized_text"] == "My local story."

    inspect_exit_code = main(["--data-dir", str(data_dir), "story", "inspect", story_id, "--json"])

    inspected = json.loads(capsys.readouterr().out)
    assert inspect_exit_code == 0
    assert inspected["story_id"] == story_id
    assert inspected["source"]["title"] == "Example"


def test_story_import_file_human_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = tmp_path / "data"
    story_file = tmp_path / "story.txt"
    story_file.write_text("A UTF-8 story with café.", encoding="utf-8")

    exit_code = main(["--data-dir", str(data_dir), "story", "import", "--file", str(story_file)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Imported story: story_" in captured.out
    assert "Source type: manual_file" in captured.out
    assert story_file.read_text(encoding="utf-8") == "A UTF-8 story with café."


def test_story_import_empty_text_returns_user_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["--data-dir", str(tmp_path), "story", "import", "--text", "   "])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "AutoTok error:" in captured.err
    assert "empty" in captured.err


def test_invalid_log_level_returns_configuration_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AUTOTOK_LOG_LEVEL", "LOUD")

    exit_code = main(["doctor"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Configuration error:" in captured.err
    assert "AUTOTOK_LOG_LEVEL" in captured.err
