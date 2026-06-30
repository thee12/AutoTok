"""Phase 6 FFmpeg rendering and output validation."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from autotok.audio_probe import file_sha256
from autotok.audio_storage import StoredAudio
from autotok.errors import DependencyError, RenderError, UnsupportedMediaError, UserInputError
from autotok.media_storage import StoredClip, StoredMedia
from autotok.render_models import RenderedVideoMetadata, RenderManifest, RenderProfile, RenderSpec
from autotok.render_storage import RenderStore, StoredRender
from autotok.subtitle_models import SubtitleExportFormat
from autotok.subtitle_storage import StoredSubtitle
from autotok.subtitles import export_subtitles

FFMPEG_TIMEOUT_SECONDS = 120
FFPROBE_TIMEOUT_SECONDS = 15
OUTPUT_DURATION_TOLERANCE_SECONDS = 0.35


def build_render_spec(
    *,
    audio: StoredAudio,
    subtitle: StoredSubtitle,
    media: StoredMedia,
    clip: StoredClip,
    profile: RenderProfile | None = None,
    created_at: datetime | None = None,
) -> RenderSpec:
    """Build and validate a render specification from completed pipeline artifacts."""
    render_profile = profile or RenderProfile()
    validate_render_inputs(
        audio=audio, subtitle=subtitle, media=media, clip=clip, profile=render_profile
    )
    render_duration = round(audio.record.metadata.duration_seconds, 3)
    render_id = stable_render_id(
        audio_id=audio.record.audio_id,
        subtitle_id=subtitle.document.subtitle_id,
        clip_id=clip.record.clip_id,
        profile=render_profile,
    )
    return RenderSpec(
        render_id=render_id,
        created_at=_utc_timestamp(created_at),
        story_id=audio.record.story_id,
        script_id=audio.record.script_id,
        audio_id=audio.record.audio_id,
        subtitle_id=subtitle.document.subtitle_id,
        media_id=media.record.media_id,
        clip_id=clip.record.clip_id,
        media_path=str(media.media_path),
        audio_path=str(audio.audio_path),
        subtitle_path="subtitles.ass",
        clip_start_seconds=clip.record.start_seconds,
        clip_duration_seconds=render_duration,
        output_filename="output.mp4",
        profile=render_profile,
    )


def validate_render_inputs(
    *,
    audio: StoredAudio,
    subtitle: StoredSubtitle,
    media: StoredMedia,
    clip: StoredClip,
    profile: RenderProfile,
) -> None:
    """Validate artifact relationships and render profile constraints."""
    if subtitle.document.audio_id != audio.record.audio_id:
        raise UserInputError("Subtitle document does not belong to the requested audio artifact.")
    if subtitle.document.script_id != audio.record.script_id:
        raise UserInputError(
            "Subtitle document script does not match the requested audio artifact."
        )
    if subtitle.document.story_id != audio.record.story_id:
        raise UserInputError("Subtitle document story does not match the requested audio artifact.")
    if clip.record.media_id != media.record.media_id:
        raise UserInputError("Clip preparation record does not belong to the requested media.")
    if audio.record.metadata.duration_seconds <= 0:
        raise UserInputError("Narration audio duration must be greater than zero.")
    if (
        clip.record.duration_seconds + OUTPUT_DURATION_TOLERANCE_SECONDS
        < audio.record.metadata.duration_seconds
    ):
        raise UserInputError("Prepared clip duration must cover the narration audio duration.")
    if (
        clip.record.end_seconds
        > media.record.metadata.duration_seconds + OUTPUT_DURATION_TOLERANCE_SECONDS
    ):
        raise UserInputError("Prepared clip extends beyond cataloged media duration.")
    if profile.width <= 0 or profile.height <= 0 or profile.fps <= 0:
        raise UserInputError("Render profile width, height, and fps must be positive.")
    if profile.height <= profile.width:
        raise UserInputError("Phase 6 render profile must be portrait-oriented.")


def render_video_package(
    *,
    store: RenderStore,
    spec: RenderSpec,
    subtitle: StoredSubtitle,
    ffmpeg_command: Sequence[str] | None = None,
    ffprobe_command: Sequence[str] | None = None,
    created_at: datetime | None = None,
) -> StoredRender:
    """Render a local video package, validate it, and write a manifest."""
    paths = store.save_spec(spec)
    if paths.manifest_path.exists() and paths.output_path.exists():
        return store.load(spec.render_id)

    try:
        paths.subtitle_ass_path.write_text(
            export_subtitles(subtitle.document, SubtitleExportFormat.ASS),
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        raise RenderError(
            f"Could not write render subtitle file: {paths.subtitle_ass_path}"
        ) from exc

    command = build_ffmpeg_command(
        spec=spec,
        subtitle_path=paths.subtitle_ass_path,
        output_path=paths.output_path,
        ffmpeg_command=ffmpeg_command,
    )
    run_ffmpeg(command)
    metadata = probe_rendered_video(paths.output_path, ffprobe_command=ffprobe_command)
    validate_render_output(metadata, spec=spec)
    manifest = RenderManifest(
        render_id=spec.render_id,
        created_at=_utc_timestamp(created_at),
        status="complete",
        spec=spec,
        output_metadata=metadata,
        ffmpeg_command=tuple(command),
        artifacts={
            "manifest": str(paths.manifest_path),
            "render_spec": str(paths.spec_path),
            "output": str(paths.output_path),
            "subtitle_ass": str(paths.subtitle_ass_path),
        },
    )
    return store.save_manifest(manifest, paths, created=True)


def build_ffmpeg_command(
    *,
    spec: RenderSpec,
    subtitle_path: Path,
    output_path: Path,
    ffmpeg_command: Sequence[str] | None = None,
) -> list[str]:
    """Build the FFmpeg command for portrait video composition."""
    profile = spec.profile
    video_filter = (
        f"scale={profile.width}:{profile.height}:force_original_aspect_ratio=increase,"
        f"crop={profile.width}:{profile.height},"
        f"subtitles='{escape_filter_path(subtitle_path)}'"
    )
    command = list(ffmpeg_command or ["ffmpeg"])
    command.extend(
        [
            "-hide_banner",
            "-y",
            "-ss",
            _format_seconds(spec.clip_start_seconds),
            "-t",
            _format_seconds(spec.clip_duration_seconds),
            "-i",
            spec.media_path,
            "-i",
            spec.audio_path,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            video_filter,
            "-shortest",
            "-r",
            str(profile.fps),
            "-c:v",
            profile.video_codec,
            "-pix_fmt",
            profile.pixel_format,
            "-c:a",
            profile.audio_codec,
            "-b:a",
            profile.audio_bitrate,
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return command


def run_ffmpeg(command: Sequence[str]) -> None:
    """Run FFmpeg and map failures to a render error."""
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            check=False,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise DependencyError(
            "ffmpeg was not found. Install FFmpeg or pass --ffmpeg-path."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError("ffmpeg timed out while rendering the video package.") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or "ffmpeg returned a nonzero exit code."
        raise RenderError(f"ffmpeg render failed: {detail}")


def probe_rendered_video(
    path: Path,
    *,
    ffprobe_command: Sequence[str] | None = None,
) -> RenderedVideoMetadata:
    """Probe a rendered video and require both video and audio streams."""
    output_path = path.expanduser()
    if not output_path.exists():
        raise RenderError(f"Rendered output was not created: {output_path}")
    command = list(ffprobe_command or ["ffprobe"])
    command.extend(
        [
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(output_path),
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
        raise UnsupportedMediaError(
            f"ffprobe timed out while reading output: {output_path}"
        ) from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or "ffprobe returned a nonzero exit code."
        raise UnsupportedMediaError(f"Could not probe rendered output: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise UnsupportedMediaError("ffprobe returned invalid JSON for rendered output.") from exc
    return rendered_metadata_from_ffprobe(payload, output_path)


def rendered_metadata_from_ffprobe(payload: object, output_path: Path) -> RenderedVideoMetadata:
    """Build rendered output metadata from ffprobe JSON."""
    if not isinstance(payload, dict):
        raise UnsupportedMediaError("ffprobe output must be a JSON object.")
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise UnsupportedMediaError("ffprobe output did not include streams.")
    video_stream = _first_stream(streams, "video")
    audio_stream = _first_stream(streams, "audio")
    format_data = payload.get("format")
    if not isinstance(format_data, dict):
        format_data = {}
    return RenderedVideoMetadata(
        duration_seconds=_duration_seconds(video_stream, format_data),
        width=_positive_int(video_stream.get("width"), "Rendered video width must be positive."),
        height=_positive_int(video_stream.get("height"), "Rendered video height must be positive."),
        frame_rate_fps=_frame_rate(video_stream),
        video_codec=_non_empty_str(video_stream.get("codec_name"), "unknown"),
        audio_codec=_non_empty_str(audio_stream.get("codec_name"), "unknown"),
        content_sha256=file_sha256(output_path),
        file_size_bytes=output_path.stat().st_size,
    )


def validate_render_output(metadata: RenderedVideoMetadata, *, spec: RenderSpec) -> None:
    """Validate rendered output against the profile and expected duration."""
    if metadata.width != spec.profile.width or metadata.height != spec.profile.height:
        raise RenderError("Rendered output dimensions do not match the portrait profile.")
    if metadata.height <= metadata.width:
        raise RenderError("Rendered output is not portrait-oriented.")
    if metadata.duration_seconds + OUTPUT_DURATION_TOLERANCE_SECONDS < spec.clip_duration_seconds:
        raise RenderError("Rendered output is shorter than the narration duration.")
    if metadata.file_size_bytes <= 0:
        raise RenderError("Rendered output file is empty.")


def escape_filter_path(path: Path) -> str:
    """Escape a filesystem path for FFmpeg filter arguments."""
    value = path.resolve().as_posix()
    return value.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def stable_render_id(
    *,
    audio_id: str,
    subtitle_id: str,
    clip_id: str,
    profile: RenderProfile,
) -> str:
    """Build a stable render ID from the rendered artifact inputs."""
    payload = "\n".join(
        [audio_id, subtitle_id, clip_id, json.dumps(profile.to_dict(), sort_keys=True)]
    ).encode("utf-8")
    return f"render_{hashlib.sha256(payload).hexdigest()[:16]}"


def _first_stream(streams: list[object], codec_type: str) -> dict[str, object]:
    for stream in streams:
        if isinstance(stream, dict) and stream.get("codec_type") == codec_type:
            return stream
    raise UnsupportedMediaError(f"Rendered output must contain a {codec_type} stream.")


def _duration_seconds(video_stream: dict[str, object], format_data: dict[str, object]) -> float:
    raw_duration = video_stream.get("duration") or format_data.get("duration")
    if not isinstance(raw_duration, str | int | float):
        raise UnsupportedMediaError("Rendered video duration is missing or invalid.")
    try:
        duration = round(float(raw_duration), 3)
    except ValueError as exc:
        raise UnsupportedMediaError("Rendered video duration is missing or invalid.") from exc
    if duration <= 0:
        raise UnsupportedMediaError("Rendered video duration must be greater than zero.")
    return duration


def _frame_rate(video_stream: dict[str, object]) -> float:
    value = video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")
    if isinstance(value, str) and "/" in value:
        numerator_text, denominator_text = value.split("/", 1)
        try:
            numerator = float(numerator_text)
            denominator = float(denominator_text)
        except ValueError as exc:
            raise UnsupportedMediaError("Rendered video frame rate is invalid.") from exc
        if denominator <= 0 or numerator <= 0:
            raise UnsupportedMediaError("Rendered video frame rate must be greater than zero.")
        return round(numerator / denominator, 3)
    if not isinstance(value, str | int | float):
        raise UnsupportedMediaError("Rendered video frame rate is missing or invalid.")
    try:
        frame_rate = float(value)
    except ValueError as exc:
        raise UnsupportedMediaError("Rendered video frame rate is missing or invalid.") from exc
    if frame_rate <= 0:
        raise UnsupportedMediaError("Rendered video frame rate must be greater than zero.")
    return round(frame_rate, 3)


def _positive_int(value: object, message: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise UnsupportedMediaError(message)
    return value


def _non_empty_str(value: object, fallback: str) -> str:
    if isinstance(value, str) and value:
        return value
    return fallback


def _format_seconds(value: float) -> str:
    return f"{value:.3f}"


def _utc_timestamp(value: datetime | None) -> str:
    timestamp = datetime.now(UTC) if value is None else value.astimezone(UTC)
    return timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
