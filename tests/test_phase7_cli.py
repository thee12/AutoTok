from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autotok.cli import main

FIXTURE = Path("tests/fixtures/reddit_listing.json")


def test_source_discover_inspect_and_import_fixture_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = tmp_path / "data"

    discover_exit = main(
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
    discovered: dict[str, Any] = json.loads(capsys.readouterr().out)
    discovery_id = str(discovered["discovery_id"])

    assert discover_exit == 0
    assert discovered["created"] is True
    assert discovered["provider"] == "reddit"
    assert [post["source_id"] for post in discovered["posts"]] == ["t3_abc123", "t3_def456"]

    inspect_exit = main(["--data-dir", str(data_dir), "source", "inspect", discovery_id, "--json"])
    inspected: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert inspect_exit == 0
    assert inspected["discovery_id"] == discovery_id

    import_exit = main(
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
    imported: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert import_exit == 0
    assert imported["story_id"].startswith("story_")
    assert imported["source"]["source_type"] == "reddit_post"
    assert imported["source"]["source_identifier"] == "t3_abc123"
    assert imported["source"]["source_url"].startswith("https://www.reddit.com/")
    assert imported["source_discovery"]["discovery_id"] == discovery_id


def test_source_discover_live_without_token_returns_user_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "--data-dir",
            str(tmp_path / "data"),
            "source",
            "discover",
            "reddit",
            "--subreddit",
            "autotok_test",
            "--limit",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "AUTOTOK_REDDIT_OAUTH_TOKEN" in captured.err
