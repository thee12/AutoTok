from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from autotok.cli import main


def test_media_import_inspect_and_select_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    media_path = tmp_path / "gameplay.mp4"
    media_path.write_bytes(b"synthetic video fixture")
    ffprobe_path = create_fake_ffprobe(tmp_path)

    import_exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "media",
            "import",
            "--file",
            str(media_path),
            "--license-note",
            "User-owned gameplay capture.",
            "--usage-note",
            "Approved for local AutoTok tests.",
            "--tag",
            "gameplay",
            "--tag",
            "calm",
            "--ffprobe-path",
            str(ffprobe_path),
            "--json",
        ]
    )
    imported: dict[str, Any] = json.loads(capsys.readouterr().out)
    media_id = imported["media_id"]

    inspect_exit_code = main(["--data-dir", str(data_dir), "media", "inspect", media_id, "--json"])
    inspected: dict[str, Any] = json.loads(capsys.readouterr().out)

    select_exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "media",
            "select",
            "--target-seconds",
            "5",
            "--orientation",
            "portrait",
            "--tag",
            "gameplay",
            "--seed",
            "7",
            "--json",
        ]
    )
    selected: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert import_exit_code == 0
    assert imported["metadata"]["orientation"] == "portrait"
    assert imported["tags"] == ["calm", "gameplay"]
    assert Path(imported["artifacts"]["media"]).exists()
    assert inspect_exit_code == 0
    assert inspected["media_id"] == media_id
    assert select_exit_code == 0
    assert selected["media_id"] == media_id
    assert selected["duration_seconds"] == 5.0
    assert selected["requested_orientation"] == "portrait"
    assert Path(selected["artifacts"]["record"]).exists()


def test_media_select_rejects_empty_catalog(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        [
            "--data-dir",
            str(tmp_path / "data"),
            "media",
            "select",
            "--target-seconds",
            "5",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "No cataloged background media" in captured.err


def create_fake_ffprobe(tmp_path: Path) -> Path:
    payload = {
        "format": {"duration": "12.0", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1080,
                "height": 1920,
                "avg_frame_rate": "30/1",
            }
        ],
    }
    script = tmp_path / "fake_ffprobe.py"
    script.write_text(
        f"import json\nprint(json.dumps({json.dumps(payload)}))\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        command = tmp_path / "fake_ffprobe.cmd"
        command.write_text(f'@echo off\n"{sys.executable}" "{script}" %*\n', encoding="utf-8")
        return command
    command = tmp_path / "fake_ffprobe"
    command.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
    command.chmod(command.stat().st_mode | stat.S_IXUSR)
    return command
