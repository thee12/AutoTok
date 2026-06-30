from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autotok.cli import main
from autotok.subtitles import script_words_from_text


def test_subtitle_generate_inspect_and_export_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    script_id, audio_id = build_script_and_audio(data_dir, capsys)

    generate_exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "subtitle",
            "generate",
            script_id,
            audio_id,
            "--format",
            "srt",
            "--json",
        ]
    )
    generated: dict[str, Any] = json.loads(capsys.readouterr().out)
    subtitle_id = generated["subtitle_id"]

    inspect_exit_code = main(
        ["--data-dir", str(data_dir), "subtitle", "inspect", subtitle_id, "--json"]
    )
    inspected: dict[str, Any] = json.loads(capsys.readouterr().out)

    export_exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "subtitle",
            "export",
            subtitle_id,
            "--format",
            "vtt",
            "--json",
        ]
    )
    exported: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert generate_exit_code == 0
    assert generated["metadata"]["timing_strategy"] == "approximate_audio_duration"
    assert generated["metadata"]["approximate"] is True
    assert Path(generated["artifacts"]["export"]).exists()
    assert inspect_exit_code == 0
    assert inspected["subtitle_id"] == subtitle_id
    assert export_exit_code == 0
    assert Path(exported["export"]).suffix == ".vtt"
    assert Path(exported["export"]).exists()


def test_subtitle_generate_accepts_provider_word_timings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    script_id, audio_id = build_script_and_audio(data_dir, capsys)
    script = json.loads(
        main_capture(
            capsys,
            ["--data-dir", str(data_dir), "script", "inspect", script_id, "--json"],
        )
    )
    timings_path = tmp_path / "word-timings.json"
    words = script_words_from_text(script["full_text"])
    timings_path.write_text(
        json.dumps(
            [
                {"word": word, "start_seconds": index * 0.3, "end_seconds": (index + 1) * 0.3}
                for index, word in enumerate(words)
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--data-dir",
            str(data_dir),
            "subtitle",
            "generate",
            script_id,
            audio_id,
            "--word-timings",
            str(timings_path),
            "--format",
            "ass",
            "--json",
        ]
    )

    generated: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert generated["metadata"]["timing_strategy"] == "provider_word_timings"
    assert generated["metadata"]["approximate"] is False
    assert Path(generated["artifacts"]["export"]).suffix == ".ass"


def test_subtitle_generate_rejects_mismatched_audio(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    script_id, _audio_id = build_script_and_audio(data_dir, capsys)
    _other_script_id, other_audio_id = build_script_and_audio(
        data_dir, capsys, story_text="Other story."
    )

    exit_code = main(
        ["--data-dir", str(data_dir), "subtitle", "generate", script_id, other_audio_id]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "does not belong" in captured.err


def build_script_and_audio(
    data_dir: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    story_text: str = "Subtitle CLI story. It has another sentence for timing.",
) -> tuple[str, str]:
    main(
        [
            "--data-dir",
            str(data_dir),
            "story",
            "import",
            "--text",
            story_text,
            "--json",
        ]
    )
    imported = json.loads(capsys.readouterr().out)
    main(
        [
            "--data-dir",
            str(data_dir),
            "story",
            "transform",
            imported["story_id"],
            "--target-seconds",
            "30",
            "--json",
        ]
    )
    transformed = json.loads(capsys.readouterr().out)
    script_id = transformed["script_id"]
    main(["--data-dir", str(data_dir), "script", "approve", script_id, "--json"])
    capsys.readouterr()
    main(["--data-dir", str(data_dir), "script", "narrate", script_id, "--json"])
    audio = json.loads(capsys.readouterr().out)
    return str(script_id), str(audio["audio_id"])


def main_capture(capsys: pytest.CaptureFixture[str], argv: list[str]) -> str:
    exit_code = main(argv)
    captured = capsys.readouterr()
    assert exit_code == 0
    return captured.out
