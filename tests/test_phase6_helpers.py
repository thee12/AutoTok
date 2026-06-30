from __future__ import annotations

import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from autotok.audio_storage import AudioStore, StoredAudio
from autotok.cli import main
from autotok.ingestion import build_manual_text_record
from autotok.media_selection import build_background_media_record, select_background_clip
from autotok.media_storage import MediaStore, StoredClip, StoredMedia
from autotok.script_models import NarrationScriptRecord
from autotok.subtitle_storage import StoredSubtitle, SubtitleStore
from autotok.subtitles import ApproximateAudioDurationStrategy, build_subtitle_document
from autotok.transform import DeterministicScriptTransformer
from autotok.tts import LocalWavTtsProvider, build_tts_audio_record


@dataclass(frozen=True, slots=True)
class PipelineArtifacts:
    data_dir: Path
    script: NarrationScriptRecord
    audio: StoredAudio
    subtitle: StoredSubtitle
    media: StoredMedia
    clip: StoredClip


def build_pipeline_artifacts(
    tmp_path: Path,
    *,
    story_text: str = "A render test story with enough words for subtitles and narration.",
) -> PipelineArtifacts:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    story = build_manual_text_record(story_text)
    script = DeterministicScriptTransformer().transform(story).approve("2026-06-30T12:00:00Z")
    audio_record, audio_path = build_tts_audio_record(script, provider=LocalWavTtsProvider())
    audio = AudioStore(data_dir).save(audio_record, source_audio_path=audio_path)
    subtitle_document = build_subtitle_document(
        script=script,
        audio=audio.record,
        timing_strategy=ApproximateAudioDurationStrategy(),
    )
    subtitle = SubtitleStore(data_dir).save(subtitle_document)
    media_file = tmp_path / "background.mp4"
    media_file.write_bytes(b"authorized synthetic background media")
    media_record = build_background_media_record(
        media_path=media_file,
        license_note="Synthetic authorized test media.",
        tags=("gameplay",),
        ffprobe_command=[
            str(
                create_fake_ffprobe(
                    tmp_path,
                    width=1080,
                    height=1920,
                    duration=audio.record.metadata.duration_seconds + 5,
                )
            )
        ],
    )
    media_store = MediaStore(data_dir)
    media = media_store.save_media(media_record, source_media_path=media_file)
    clip_record = select_background_clip(
        [media.record],
        target_duration_seconds=audio.record.metadata.duration_seconds + 1,
        seed=3,
        required_tags=("gameplay",),
    )
    clip = media_store.save_clip(clip_record)
    return PipelineArtifacts(
        data_dir=data_dir,
        script=script,
        audio=audio,
        subtitle=subtitle,
        media=media,
        clip=clip,
    )


def run_cli_pipeline_to_clip(
    data_dir: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    ffprobe_path: Path,
    story_text: str = "Render CLI story. It has enough material for a local MVP smoke test.",
) -> dict[str, str]:
    main(["--data-dir", str(data_dir), "story", "import", "--text", story_text, "--json"])
    imported = json.loads(capsys.readouterr().out)
    main(
        [
            "--data-dir",
            str(data_dir),
            "story",
            "transform",
            imported["story_id"],
            "--target-seconds",
            "20",
            "--json",
        ]
    )
    transformed = json.loads(capsys.readouterr().out)
    script_id = transformed["script_id"]
    main(["--data-dir", str(data_dir), "script", "approve", script_id, "--json"])
    capsys.readouterr()
    main(["--data-dir", str(data_dir), "script", "narrate", script_id, "--json"])
    audio = json.loads(capsys.readouterr().out)
    audio_id = audio["audio_id"]
    main(
        [
            "--data-dir",
            str(data_dir),
            "subtitle",
            "generate",
            script_id,
            audio_id,
            "--json",
        ]
    )
    subtitle = json.loads(capsys.readouterr().out)
    media_file = tmp_path / f"background-{script_id}.mp4"
    media_file.write_bytes(f"authorized media {script_id}".encode())
    main(
        [
            "--data-dir",
            str(data_dir),
            "media",
            "import",
            "--file",
            str(media_file),
            "--license-note",
            "Synthetic authorized CLI media.",
            "--tag",
            "gameplay",
            "--ffprobe-path",
            str(ffprobe_path),
            "--json",
        ]
    )
    capsys.readouterr()
    target_seconds = str(float(audio["metadata"]["duration_seconds"]) + 1.0)
    main(
        [
            "--data-dir",
            str(data_dir),
            "media",
            "select",
            "--target-seconds",
            target_seconds,
            "--orientation",
            "portrait",
            "--tag",
            "gameplay",
            "--seed",
            "9",
            "--json",
        ]
    )
    clip = json.loads(capsys.readouterr().out)
    return {
        "script_id": str(script_id),
        "audio_id": str(audio_id),
        "subtitle_id": str(subtitle["subtitle_id"]),
        "clip_id": str(clip["clip_id"]),
    }


def create_fake_ffmpeg(tmp_path: Path) -> Path:
    script = tmp_path / "fake_ffmpeg.py"
    script.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path(sys.argv[-1]).write_bytes(b'rendered mp4 bytes')\n",
        encoding="utf-8",
    )
    return _command_wrapper(tmp_path, "fake_ffmpeg", script)


def create_fake_ffprobe(
    tmp_path: Path,
    *,
    width: int,
    height: int,
    duration: float,
    include_audio: bool = True,
) -> Path:
    streams: list[dict[str, object]] = [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": width,
            "height": height,
            "avg_frame_rate": "30/1",
        }
    ]
    if include_audio:
        streams.append({"codec_type": "audio", "codec_name": "aac"})
    payload: dict[str, Any] = {
        "format": {"duration": str(duration), "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
        "streams": streams,
    }
    script = tmp_path / f"fake_ffprobe_{width}_{height}_{duration}_{include_audio}.py"
    script.write_text(
        f"import json\nprint(json.dumps({json.dumps(payload)}))\n",
        encoding="utf-8",
    )
    return _command_wrapper(tmp_path, script.stem, script)


def _command_wrapper(tmp_path: Path, name: str, script: Path) -> Path:
    if os.name == "nt":
        command = tmp_path / f"{name}.cmd"
        command.write_text(f'@echo off\n"{sys.executable}" "{script}" %*\n', encoding="utf-8")
        return command
    command = tmp_path / name
    command.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
    command.chmod(command.stat().st_mode | stat.S_IXUSR)
    return command
