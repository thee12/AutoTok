"""FFprobe-backed background media probing for Phase 5."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

from autotok.audio_probe import file_sha256
from autotok.errors import DependencyError, UnsupportedMediaError, UserInputError
from autotok.media_models import VideoMetadata

FFPROBE_TIMEOUT_SECONDS = 15


def probe_video_media(
    path: Path,
    *,
    ffprobe_command: Sequence[str] | None = None,
) -> VideoMetadata:
    """Probe and validate a local video file using ffprobe JSON output."""
    media_path = path.expanduser()
    if not media_path.exists():
        raise UserInputError(f"Media file does not exist: {media_path}")
    if not media_path.is_file():
        raise UserInputError(f"Media path is not a file: {media_path}")

    command = list(ffprobe_command or ["ffprobe"])
    command.extend(
        [
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(media_path),
        ]
    )
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=FFPROBE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise DependencyError(
            "ffprobe was not found. Install FFmpeg or pass --ffprobe-path."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise UnsupportedMediaError(f"ffprobe timed out while reading media: {media_path}") from exc

    if result.returncode != 0:
        detail = result.stderr.strip() or "ffprobe returned a nonzero exit code."
        raise UnsupportedMediaError(f"Could not probe media file: {detail}")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise UnsupportedMediaError("ffprobe returned invalid JSON.") from exc

    return metadata_from_ffprobe(payload, media_path)


def metadata_from_ffprobe(payload: object, media_path: Path) -> VideoMetadata:
    """Build validated video metadata from ffprobe JSON payload."""
    if not isinstance(payload, dict):
        raise UnsupportedMediaError("ffprobe output must be a JSON object.")
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise UnsupportedMediaError("ffprobe output did not include streams.")
    video_stream = _first_video_stream(streams)
    format_data = payload.get("format")
    if not isinstance(format_data, dict):
        format_data = {}

    width = _positive_int(video_stream.get("width"), "Video width must be positive.")
    height = _positive_int(video_stream.get("height"), "Video height must be positive.")
    duration = _duration_seconds(video_stream, format_data)
    frame_rate = _frame_rate(video_stream)
    codec = _non_empty_str(video_stream.get("codec_name"), "Video codec is missing.")
    format_name = _non_empty_str(format_data.get("format_name"), "unknown")

    return VideoMetadata(
        format_name=format_name,
        duration_seconds=duration,
        width=width,
        height=height,
        frame_rate_fps=frame_rate,
        video_codec=codec,
        content_sha256=file_sha256(media_path),
        file_size_bytes=media_path.stat().st_size,
    )


def _first_video_stream(streams: list[object]) -> dict[str, object]:
    for stream in streams:
        if isinstance(stream, dict) and stream.get("codec_type") == "video":
            return stream
    raise UnsupportedMediaError("Media file must contain a video stream.")


def _duration_seconds(video_stream: dict[str, object], format_data: dict[str, object]) -> float:
    raw_duration = video_stream.get("duration") or format_data.get("duration")
    if not isinstance(raw_duration, str | int | float):
        raise UnsupportedMediaError("Video duration is missing or invalid.")
    try:
        duration = round(float(raw_duration), 3)
    except ValueError as exc:
        raise UnsupportedMediaError("Video duration is missing or invalid.") from exc
    if duration <= 0:
        raise UnsupportedMediaError("Video duration must be greater than zero.")
    return duration


def _frame_rate(video_stream: dict[str, object]) -> float:
    value = video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")
    if isinstance(value, str) and "/" in value:
        numerator_text, denominator_text = value.split("/", 1)
        try:
            numerator = float(numerator_text)
            denominator = float(denominator_text)
        except ValueError as exc:
            raise UnsupportedMediaError("Video frame rate is invalid.") from exc
        if denominator <= 0 or numerator <= 0:
            raise UnsupportedMediaError("Video frame rate must be greater than zero.")
        return round(numerator / denominator, 3)
    if not isinstance(value, str | int | float):
        raise UnsupportedMediaError("Video frame rate is missing or invalid.")
    try:
        frame_rate = float(value)
    except ValueError as exc:
        raise UnsupportedMediaError("Video frame rate is missing or invalid.") from exc
    if frame_rate <= 0:
        raise UnsupportedMediaError("Video frame rate must be greater than zero.")
    return round(frame_rate, 3)


def _positive_int(value: object, message: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise UnsupportedMediaError(message)
    return value


def _non_empty_str(value: object, fallback: str) -> str:
    if isinstance(value, str) and value:
        return value
    return fallback
