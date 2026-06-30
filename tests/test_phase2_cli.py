from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autotok.cli import main


def test_story_transform_inspect_and_approve_json(
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
            "Reach me at reader@example.com. The lights flickered twice.",
            "--title",
            "Lights",
            "--json",
        ]
    )
    imported: dict[str, Any] = json.loads(capsys.readouterr().out)
    story_id = imported["story_id"]

    transform_exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "story",
            "transform",
            story_id,
            "--target-seconds",
            "45",
            "--json",
        ]
    )
    transformed: dict[str, Any] = json.loads(capsys.readouterr().out)
    script_id = transformed["script_id"]

    inspect_exit_code = main(
        ["--data-dir", str(data_dir), "script", "inspect", script_id, "--json"]
    )
    inspected: dict[str, Any] = json.loads(capsys.readouterr().out)

    approve_exit_code = main(
        ["--data-dir", str(data_dir), "script", "approve", script_id, "--json"]
    )
    approved: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert import_exit_code == 0
    assert transform_exit_code == 0
    assert transformed["created"] is True
    assert transformed["review_status"] == "pending_review"
    assert transformed["privacy_report"]["email_redactions"] == 1
    assert "[redacted email]" in transformed["full_text"]
    assert inspect_exit_code == 0
    assert inspected["script_id"] == script_id
    assert approve_exit_code == 0
    assert approved["review_status"] == "approved"
    assert approved["approved_at"] is not None


def test_story_transform_rejects_missing_story(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        [
            "--data-dir",
            str(tmp_path / "data"),
            "story",
            "transform",
            "story_0000000000000000",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Story record was not found" in captured.err


def test_story_transform_rejects_invalid_duration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    main(["--data-dir", str(data_dir), "story", "import", "--text", "A story.", "--json"])
    story_id = json.loads(capsys.readouterr().out)["story_id"]

    exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "story",
            "transform",
            story_id,
            "--target-seconds",
            "10",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Target seconds" in captured.err
