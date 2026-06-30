"""Render models for Phase 6 video packages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

RENDER_SPEC_SCHEMA_VERSION = 1
RENDER_MANIFEST_SCHEMA_VERSION = 1
DEFAULT_RENDER_WIDTH = 1080
DEFAULT_RENDER_HEIGHT = 1920
DEFAULT_RENDER_FPS = 30
DEFAULT_VIDEO_CODEC = "libx264"
DEFAULT_AUDIO_CODEC = "aac"
DEFAULT_AUDIO_BITRATE = "192k"
DEFAULT_PIXEL_FORMAT = "yuv420p"


@dataclass(frozen=True, slots=True)
class RenderProfile:
    """Output profile for a local rendered short-form video."""

    width: int = DEFAULT_RENDER_WIDTH
    height: int = DEFAULT_RENDER_HEIGHT
    fps: int = DEFAULT_RENDER_FPS
    video_codec: str = DEFAULT_VIDEO_CODEC
    audio_codec: str = DEFAULT_AUDIO_CODEC
    audio_bitrate: str = DEFAULT_AUDIO_BITRATE
    pixel_format: str = DEFAULT_PIXEL_FORMAT

    def to_dict(self) -> dict[str, object]:
        """Serialize the render profile."""
        return {
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "audio_bitrate": self.audio_bitrate,
            "pixel_format": self.pixel_format,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RenderProfile:
        """Deserialize the render profile."""
        return cls(
            width=_required_int(data, "width"),
            height=_required_int(data, "height"),
            fps=_required_int(data, "fps"),
            video_codec=_required_str(data, "video_codec"),
            audio_codec=_required_str(data, "audio_codec"),
            audio_bitrate=_required_str(data, "audio_bitrate"),
            pixel_format=_required_str(data, "pixel_format"),
        )


@dataclass(frozen=True, slots=True)
class RenderSpec:
    """Concrete render specification assembled from existing artifacts."""

    render_id: str
    created_at: str
    story_id: str
    script_id: str
    audio_id: str
    subtitle_id: str
    media_id: str
    clip_id: str
    media_path: str
    audio_path: str
    subtitle_path: str
    clip_start_seconds: float
    clip_duration_seconds: float
    output_filename: str
    profile: RenderProfile
    schema_version: int = RENDER_SPEC_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        """Serialize the render specification."""
        return {
            "schema_version": self.schema_version,
            "render_id": self.render_id,
            "created_at": self.created_at,
            "story_id": self.story_id,
            "script_id": self.script_id,
            "audio_id": self.audio_id,
            "subtitle_id": self.subtitle_id,
            "media_id": self.media_id,
            "clip_id": self.clip_id,
            "media_path": self.media_path,
            "audio_path": self.audio_path,
            "subtitle_path": self.subtitle_path,
            "clip_start_seconds": self.clip_start_seconds,
            "clip_duration_seconds": self.clip_duration_seconds,
            "output_filename": self.output_filename,
            "profile": self.profile.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RenderSpec:
        """Deserialize the render specification."""
        schema_version = _required_int(data, "schema_version")
        if schema_version != RENDER_SPEC_SCHEMA_VERSION:
            raise ValueError(f"Unsupported render spec schema_version: {schema_version}")
        profile_data = data.get("profile")
        if not isinstance(profile_data, Mapping):
            raise ValueError("profile must be an object.")
        return cls(
            schema_version=schema_version,
            render_id=_required_str(data, "render_id"),
            created_at=_required_str(data, "created_at"),
            story_id=_required_str(data, "story_id"),
            script_id=_required_str(data, "script_id"),
            audio_id=_required_str(data, "audio_id"),
            subtitle_id=_required_str(data, "subtitle_id"),
            media_id=_required_str(data, "media_id"),
            clip_id=_required_str(data, "clip_id"),
            media_path=_required_str(data, "media_path"),
            audio_path=_required_str(data, "audio_path"),
            subtitle_path=_required_str(data, "subtitle_path"),
            clip_start_seconds=_required_float(data, "clip_start_seconds"),
            clip_duration_seconds=_required_float(data, "clip_duration_seconds"),
            output_filename=_required_str(data, "output_filename"),
            profile=RenderProfile.from_dict(profile_data),
        )


@dataclass(frozen=True, slots=True)
class RenderedVideoMetadata:
    """Validated metadata for a rendered output video."""

    duration_seconds: float
    width: int
    height: int
    frame_rate_fps: float
    video_codec: str
    audio_codec: str
    content_sha256: str
    file_size_bytes: int

    def to_dict(self) -> dict[str, object]:
        """Serialize rendered video metadata."""
        return {
            "duration_seconds": self.duration_seconds,
            "width": self.width,
            "height": self.height,
            "frame_rate_fps": self.frame_rate_fps,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "content_sha256": self.content_sha256,
            "file_size_bytes": self.file_size_bytes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RenderedVideoMetadata:
        """Deserialize rendered video metadata."""
        return cls(
            duration_seconds=_required_float(data, "duration_seconds"),
            width=_required_int(data, "width"),
            height=_required_int(data, "height"),
            frame_rate_fps=_required_float(data, "frame_rate_fps"),
            video_codec=_required_str(data, "video_codec"),
            audio_codec=_required_str(data, "audio_codec"),
            content_sha256=_required_str(data, "content_sha256"),
            file_size_bytes=_required_int(data, "file_size_bytes"),
        )


@dataclass(frozen=True, slots=True)
class RenderManifest:
    """Manifest for a completed local video render package."""

    render_id: str
    created_at: str
    status: str
    spec: RenderSpec
    output_metadata: RenderedVideoMetadata
    ffmpeg_command: tuple[str, ...]
    artifacts: dict[str, str]
    schema_version: int = RENDER_MANIFEST_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        """Serialize render manifest."""
        return {
            "schema_version": self.schema_version,
            "render_id": self.render_id,
            "created_at": self.created_at,
            "status": self.status,
            "spec": self.spec.to_dict(),
            "output_metadata": self.output_metadata.to_dict(),
            "ffmpeg_command": list(self.ffmpeg_command),
            "artifacts": self.artifacts,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RenderManifest:
        """Deserialize render manifest."""
        schema_version = _required_int(data, "schema_version")
        if schema_version != RENDER_MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"Unsupported render manifest schema_version: {schema_version}")
        spec_data = data.get("spec")
        if not isinstance(spec_data, Mapping):
            raise ValueError("spec must be an object.")
        metadata_data = data.get("output_metadata")
        if not isinstance(metadata_data, Mapping):
            raise ValueError("output_metadata must be an object.")
        command_data = data.get("ffmpeg_command")
        if not isinstance(command_data, Sequence) or isinstance(command_data, str):
            raise ValueError("ffmpeg_command must be a list of strings.")
        artifacts = data.get("artifacts")
        if not isinstance(artifacts, dict):
            raise ValueError("artifacts must be an object.")
        return cls(
            schema_version=schema_version,
            render_id=_required_str(data, "render_id"),
            created_at=_required_str(data, "created_at"),
            status=_required_str(data, "status"),
            spec=RenderSpec.from_dict(spec_data),
            output_metadata=RenderedVideoMetadata.from_dict(metadata_data),
            ffmpeg_command=tuple(_required_sequence_str(command_data, "ffmpeg_command")),
            artifacts={str(key): str(value) for key, value in artifacts.items()},
        )


def _required_sequence_str(values: Sequence[object], key: str) -> list[str]:
    strings: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{key} must contain non-empty strings.")
        strings.append(value)
    return strings


def _required_str(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string.")
    return value


def _required_int(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer.")
    return value


def _required_float(data: Mapping[str, object], key: str) -> float:
    value = data.get(key)
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"{key} must be a number.")
