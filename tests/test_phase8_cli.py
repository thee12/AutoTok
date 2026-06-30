from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autotok.cli import main

FIXTURE = Path("tests/fixtures/reddit_listing.json")


def test_story_assess_gate_and_override_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = tmp_path / "data"
    main(
        [
            "--data-dir",
            str(data_dir),
            "story",
            "import",
            "--text",
            "The diner lost power before lunch. Everyone used phone flashlights while the cook "
            "finished the soup, shared extra bread, cleaned tables, and the whole block ate "
            "together outside before sunset.",
            "--json",
        ]
    )
    story_id = json.loads(capsys.readouterr().out)["story_id"]

    assess_exit = main(["--data-dir", str(data_dir), "story", "assess", story_id, "--json"])
    assessed: dict[str, Any] = json.loads(capsys.readouterr().out)

    gate_exit = main(["--data-dir", str(data_dir), "story", "gate", story_id, "--json"])
    gated: dict[str, Any] = json.loads(capsys.readouterr().out)

    override_exit = main(
        [
            "--data-dir",
            str(data_dir),
            "story",
            "override",
            story_id,
            "--decision",
            "needs_review",
            "--reason",
            "Checking override trail.",
            "--reviewer",
            "tester",
            "--json",
        ]
    )
    overridden: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert assess_exit == 0
    assert assessed["story_id"] == story_id
    assert assessed["effective_decision"] == "approved"
    assert gate_exit == 0
    assert gated["gate_id"] == assessed["gate_id"]
    assert override_exit == 0
    assert overridden["effective_decision"] == "needs_review"
    assert overridden["override_events"][0]["reviewer"] == "tester"


def test_discovered_story_transform_requires_approved_gate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = tmp_path / "data"
    main(
        [
            "--data-dir",
            str(data_dir),
            "source",
            "discover",
            "reddit",
            "--subreddit",
            "autotok_test",
            "--fixture-json",
            str(FIXTURE),
            "--json",
        ]
    )
    discovery_id = json.loads(capsys.readouterr().out)["discovery_id"]
    main(
        [
            "--data-dir",
            str(data_dir),
            "source",
            "import",
            discovery_id,
            "t3_abc123",
            "--json",
        ]
    )
    story_id = json.loads(capsys.readouterr().out)["story_id"]

    blocked_exit = main(["--data-dir", str(data_dir), "story", "transform", story_id, "--json"])
    blocked = capsys.readouterr()

    assess_exit = main(
        [
            "--data-dir",
            str(data_dir),
            "story",
            "assess",
            story_id,
            "--min-words",
            "1",
            "--min-duration-seconds",
            "1",
            "--auto-approve-min-score",
            "1",
            "--json",
        ]
    )
    assessed: dict[str, Any] = json.loads(capsys.readouterr().out)

    transform_exit = main(["--data-dir", str(data_dir), "story", "transform", story_id, "--json"])
    transformed: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert blocked_exit == 1
    assert "must pass `autotok story assess`" in blocked.err
    assert assess_exit == 0
    assert assessed["effective_decision"] == "approved"
    assert transform_exit == 0
    assert transformed["story_id"] == story_id


def test_story_transform_rejects_nonapproved_existing_gate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = tmp_path / "data"
    main(["--data-dir", str(data_dir), "story", "import", "--text", "Tiny.", "--json"])
    story_id = json.loads(capsys.readouterr().out)["story_id"]
    main(["--data-dir", str(data_dir), "story", "assess", story_id, "--json"])
    capsys.readouterr()

    exit_code = main(["--data-dir", str(data_dir), "story", "transform", story_id])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "content gate must be approved" in captured.err
