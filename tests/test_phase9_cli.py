from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autotok.cli import main
from tests.test_phase6_helpers import create_fake_ffmpeg, create_fake_ffprobe


def test_job_create_run_resume_and_inspect_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = tmp_path / "data"
    ffprobe = create_fake_ffprobe(tmp_path, width=1080, height=1920, duration=120.0)
    ffmpeg = create_fake_ffmpeg(tmp_path)

    main(
        [
            "--data-dir",
            str(data_dir),
            "story",
            "import",
            "--text",
            "A job CLI story with enough material for a resumable local pipeline smoke test.",
            "--json",
        ]
    )
    story: dict[str, Any] = json.loads(capsys.readouterr().out)

    media_file = tmp_path / "background.mp4"
    media_file.write_bytes(b"authorized phase 9 background media")
    main(
        [
            "--data-dir",
            str(data_dir),
            "media",
            "import",
            "--file",
            str(media_file),
            "--license-note",
            "Synthetic authorized Phase 9 CLI media.",
            "--tag",
            "gameplay",
            "--ffprobe-path",
            str(ffprobe),
            "--json",
        ]
    )
    capsys.readouterr()

    create_exit = main(
        [
            "--data-dir",
            str(data_dir),
            "job",
            "create",
            "--story-id",
            str(story["story_id"]),
            "--json",
        ]
    )
    created: dict[str, Any] = json.loads(capsys.readouterr().out)
    job_id = str(created["jobs"][0]["job_id"])

    run_exit = main(
        [
            "--data-dir",
            str(data_dir),
            "job",
            "run",
            job_id,
            "--target-seconds",
            "20",
            "--tag",
            "gameplay",
            "--ffmpeg-path",
            str(ffmpeg),
            "--ffprobe-path",
            str(ffprobe),
            "--json",
        ]
    )
    run_summary: dict[str, Any] = json.loads(capsys.readouterr().out)

    resume_exit = main(
        [
            "--data-dir",
            str(data_dir),
            "job",
            "resume",
            job_id,
            "--target-seconds",
            "20",
            "--tag",
            "gameplay",
            "--ffmpeg-path",
            str(ffmpeg),
            "--ffprobe-path",
            str(ffprobe),
            "--json",
        ]
    )
    resumed: dict[str, Any] = json.loads(capsys.readouterr().out)

    inspect_exit = main(
        [
            "--data-dir",
            str(data_dir),
            "job",
            "inspect",
            job_id,
            "--json",
        ]
    )
    inspected: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert create_exit == 0
    assert run_exit == 0
    assert resume_exit == 0
    assert inspect_exit == 0
    assert run_summary["completed"] is True
    assert Path(str(run_summary["manifest_path"])).exists()
    assert resumed["job"]["status"] == "succeeded"
    assert [stage["attempt_count"] for stage in resumed["stages"]] == [1, 1, 1, 1, 1, 1]
    assert inspected["job"]["job_id"] == job_id
    assert len(inspected["artifacts"]) == 7


def test_job_run_batch_honors_limit_and_stop_after(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = tmp_path / "data"
    story_ids: list[str] = []
    for text in (
        "First batch story has enough words for the deterministic local transformer.",
        "Second batch story also has enough words for a queued local job.",
    ):
        main(["--data-dir", str(data_dir), "story", "import", "--text", text, "--json"])
        story: dict[str, Any] = json.loads(capsys.readouterr().out)
        story_ids.append(str(story["story_id"]))

    create_args = ["--data-dir", str(data_dir), "job", "create", "--batch-id", "batch_cli"]
    for story_id in story_ids:
        create_args.extend(["--story-id", story_id])
    create_args.append("--json")
    assert main(create_args) == 0
    capsys.readouterr()

    run_exit = main(
        [
            "--data-dir",
            str(data_dir),
            "job",
            "run-batch",
            "batch_cli",
            "--limit",
            "1",
            "--stop-after",
            "transform",
            "--json",
        ]
    )
    summary: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert run_exit == 0
    assert summary["job_count"] == 1
    first = summary["summaries"][0]
    assert first["completed"] is False
    assert first["stopped_after"] == "transform"
    assert first["job"]["status"] == "queued"
    assert first["stages"][0]["name"] == "transform"
    assert first["stages"][0]["status"] == "succeeded"
