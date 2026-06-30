from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import pytest

from autotok.errors import RenderError, UserInputError
from autotok.render import (
    build_ffmpeg_command,
    build_render_spec,
    rendered_metadata_from_ffprobe,
    validate_render_output,
)
from autotok.render_models import RenderedVideoMetadata, RenderProfile
from autotok.subtitle_storage import SubtitleStore
from tests.test_phase6_helpers import (
    build_pipeline_artifacts,
    create_fake_ffmpeg,
    create_fake_ffprobe,
)


def test_build_render_spec_and_ffmpeg_command(tmp_path: Path) -> None:
    artifacts = build_pipeline_artifacts(tmp_path)

    spec = build_render_spec(
        audio=artifacts.audio,
        subtitle=artifacts.subtitle,
        media=artifacts.media,
        clip=artifacts.clip,
    )
    command = build_ffmpeg_command(
        spec=spec,
        subtitle_path=tmp_path / "subtitles.ass",
        output_path=tmp_path / "output.mp4",
        ffmpeg_command=["ffmpeg-test"],
    )

    assert spec.render_id.startswith("render_")
    assert spec.clip_duration_seconds == artifacts.audio.record.metadata.duration_seconds
    assert command[0] == "ffmpeg-test"
    assert "-map" in command
    assert "1:a:0" in command
    joined_command = " ".join(command)
    assert "scale=1080:1920" in joined_command
    assert "crop=1080:1920" in joined_command
    assert "subtitles=" in joined_command


def test_build_render_spec_rejects_mismatched_subtitle(tmp_path: Path) -> None:
    artifacts = build_pipeline_artifacts(tmp_path)
    other = build_pipeline_artifacts(
        tmp_path / "other", story_text="A different story for subtitles."
    )

    with pytest.raises(UserInputError, match="Subtitle document"):
        build_render_spec(
            audio=artifacts.audio,
            subtitle=other.subtitle,
            media=artifacts.media,
            clip=artifacts.clip,
        )


def test_render_validation_rejects_non_portrait_output(tmp_path: Path) -> None:
    artifacts = build_pipeline_artifacts(tmp_path)
    spec = build_render_spec(
        audio=artifacts.audio,
        subtitle=artifacts.subtitle,
        media=artifacts.media,
        clip=artifacts.clip,
    )
    metadata = RenderedVideoMetadata(
        duration_seconds=spec.clip_duration_seconds,
        width=1920,
        height=1080,
        frame_rate_fps=30.0,
        video_codec="h264",
        audio_codec="aac",
        content_sha256="abc",
        file_size_bytes=10,
    )

    with pytest.raises(RenderError, match="dimensions"):
        validate_render_output(metadata, spec=spec)


def test_rendered_metadata_requires_audio_stream(tmp_path: Path) -> None:
    output_path = tmp_path / "output.mp4"
    output_path.write_bytes(b"rendered bytes")
    payload: dict[str, Any] = {
        "format": {"duration": "4.0"},
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

    with pytest.raises(Exception, match="audio"):
        rendered_metadata_from_ffprobe(payload, output_path)


def test_render_package_writes_manifest(tmp_path: Path) -> None:
    artifacts = build_pipeline_artifacts(tmp_path)
    spec = build_render_spec(
        audio=artifacts.audio,
        subtitle=artifacts.subtitle,
        media=artifacts.media,
        clip=artifacts.clip,
        profile=RenderProfile(),
    )
    ffmpeg = create_fake_ffmpeg(tmp_path)
    ffprobe = create_fake_ffprobe(
        tmp_path,
        width=1080,
        height=1920,
        duration=spec.clip_duration_seconds,
        include_audio=True,
    )

    from autotok.render import render_video_package
    from autotok.render_storage import RenderStore

    stored = render_video_package(
        store=RenderStore(artifacts.data_dir),
        spec=spec,
        subtitle=artifacts.subtitle,
        ffmpeg_command=[str(ffmpeg)],
        ffprobe_command=[str(ffprobe)],
    )

    assert stored.created is True
    assert stored.paths.output_path.exists()
    assert stored.paths.manifest_path.exists()
    assert stored.manifest.status == "complete"
    assert stored.manifest.output_metadata.audio_codec == "aac"
    assert SubtitleStore(artifacts.data_dir).load(artifacts.subtitle.document.subtitle_id)


def test_fake_helpers_are_executable_on_this_platform(tmp_path: Path) -> None:
    ffmpeg = create_fake_ffmpeg(tmp_path)
    ffprobe = create_fake_ffprobe(tmp_path, width=1080, height=1920, duration=1.0)

    assert ffmpeg.exists()
    assert ffprobe.exists()
    if os.name != "nt":
        assert ffmpeg.stat().st_mode & stat.S_IXUSR
        assert ffprobe.stat().st_mode & stat.S_IXUSR
