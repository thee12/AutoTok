from __future__ import annotations

import json
import struct
import subprocess
import wave
from pathlib import Path
from typing import Any

import pytest

from autotok.cli import main


def test_script_narrate_generates_audio_after_approval(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    script_id = import_transform_and_approve(data_dir, capsys)

    narrate_exit_code = main(
        ["--data-dir", str(data_dir), "script", "narrate", script_id, "--json"]
    )
    narrated: dict[str, Any] = json.loads(capsys.readouterr().out)
    audio_id = narrated["audio_id"]

    inspect_exit_code = main(["--data-dir", str(data_dir), "audio", "inspect", audio_id, "--json"])
    inspected: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert narrate_exit_code == 0
    assert narrated["source_type"] == "tts_generated"
    assert narrated["provider_name"] == "local_wav"
    assert narrated["provider_request"]["paid_call"] is False
    assert narrated["metadata"]["duration_seconds"] > 0
    assert Path(narrated["artifacts"]["audio"]).exists()
    assert inspect_exit_code == 0
    assert inspected["audio_id"] == audio_id


def test_script_narrate_generates_pyttsx3_audio_after_approval(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    script_id = import_transform_and_approve(data_dir, capsys)

    def fake_run(
        args: list[str],
        *,
        capture_output: bool,
        check: bool,
        text: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        output_path = Path(args[4])
        write_test_wav(output_path)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr("autotok.tts.subprocess.run", fake_run)

    exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "script",
            "narrate",
            script_id,
            "--provider",
            "pyttsx3",
            "--json",
        ]
    )

    narrated: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert narrated["source_type"] == "tts_generated"
    assert narrated["provider_name"] == "pyttsx3"
    assert narrated["provider_request"]["network"] is False
    assert narrated["provider_request"]["paid_call"] is False
    assert narrated["metadata"]["duration_seconds"] == 1.0


def test_script_narrate_rejects_pending_script(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    script_id = import_and_transform(data_dir, capsys)

    exit_code = main(["--data-dir", str(data_dir), "script", "narrate", script_id])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "approved script" in captured.err


def test_script_narrate_accepts_manual_wav(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    script_id = import_transform_and_approve(data_dir, capsys)
    audio_path = tmp_path / "manual.wav"
    write_test_wav(audio_path)

    exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "script",
            "narrate",
            script_id,
            "--audio-file",
            str(audio_path),
            "--json",
        ]
    )

    narrated: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert narrated["source_type"] == "manual_file"
    assert narrated["source_path"] == str(audio_path.resolve())
    assert narrated["metadata"]["duration_seconds"] == 1.0


def import_transform_and_approve(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> str:
    script_id = import_and_transform(data_dir, capsys)
    main(["--data-dir", str(data_dir), "script", "approve", script_id, "--json"])
    approved: dict[str, Any] = json.loads(capsys.readouterr().out)
    return str(approved["script_id"])


def import_and_transform(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> str:
    main(
        [
            "--data-dir",
            str(data_dir),
            "story",
            "import",
            "--text",
            "A narration story. It has a clear second sentence.",
            "--json",
        ]
    )
    imported: dict[str, Any] = json.loads(capsys.readouterr().out)
    main(
        [
            "--data-dir",
            str(data_dir),
            "story",
            "transform",
            str(imported["story_id"]),
            "--target-seconds",
            "30",
            "--json",
        ]
    )
    transformed: dict[str, Any] = json.loads(capsys.readouterr().out)
    return str(transformed["script_id"])


def write_test_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8_000)
        frame = struct.pack("<h", 0)
        for _ in range(8_000):
            wav_file.writeframesraw(frame)
        wav_file.writeframes(b"")
