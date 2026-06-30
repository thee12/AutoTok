from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autotok.cli import main
from tests.test_phase6_helpers import (
    create_fake_ffmpeg,
    create_fake_ffprobe,
    run_cli_pipeline_to_clip,
)


def test_render_create_and_inspect_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = tmp_path / "data"
    ffprobe = create_fake_ffprobe(tmp_path, width=1080, height=1920, duration=30.0)
    pipeline = run_cli_pipeline_to_clip(data_dir, tmp_path, capsys, ffprobe_path=ffprobe)
    ffmpeg = create_fake_ffmpeg(tmp_path)

    create_exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "render",
            "create",
            pipeline["audio_id"],
            pipeline["subtitle_id"],
            pipeline["clip_id"],
            "--ffmpeg-path",
            str(ffmpeg),
            "--ffprobe-path",
            str(ffprobe),
            "--json",
        ]
    )
    created: dict[str, Any] = json.loads(capsys.readouterr().out)
    render_id = created["render_id"]

    inspect_exit_code = main(
        ["--data-dir", str(data_dir), "render", "inspect", render_id, "--json"]
    )
    inspected: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert create_exit_code == 0
    assert created["status"] == "complete"
    assert created["output_metadata"]["width"] == 1080
    assert created["output_metadata"]["height"] == 1920
    assert Path(created["artifacts"]["output"]).exists()
    assert Path(created["artifacts"]["manifest"]).exists()
    assert inspect_exit_code == 0
    assert inspected["render_id"] == render_id
    assert inspected["artifacts"]["output"] == created["artifacts"]["output"]


def test_render_create_rejects_mismatched_subtitle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    ffprobe = create_fake_ffprobe(tmp_path, width=1080, height=1920, duration=30.0)
    first = run_cli_pipeline_to_clip(data_dir, tmp_path, capsys, ffprobe_path=ffprobe)
    second = run_cli_pipeline_to_clip(
        data_dir,
        tmp_path,
        capsys,
        ffprobe_path=ffprobe,
        story_text="A second story creates a different subtitle document.",
    )
    ffmpeg = create_fake_ffmpeg(tmp_path)

    exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "render",
            "create",
            first["audio_id"],
            second["subtitle_id"],
            first["clip_id"],
            "--ffmpeg-path",
            str(ffmpeg),
            "--ffprobe-path",
            str(ffprobe),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Subtitle document" in captured.err
