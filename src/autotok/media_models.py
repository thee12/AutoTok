"""Background media models for Phase 5 artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

MEDIA_SCHEMA_VERSION = 1
CLIP_SCHEMA_VERSION = 1


class MediaOrientation(StrEnum):
    """Supported background-media orientation classes."""

    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"
    SQUARE = "square"


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    """Validated video metadata extracted by ffprobe."""

    format_name: str
    duration_seconds: float
    width: int
    height: int
    frame_rate_fps: float
    video_codec: str
    content_sha256: str
    file_size_bytes: int

    @property
    def orientation(self) -> MediaOrientation:
        """Return the coarse visual orientation."""
        if self.height > self.width:
            return MediaOrientation.PORTRAIT
        if self.width > self.height:
            return MediaOrientation.LANDSCAPE
        return MediaOrientation.SQUARE

    def to_dict(self) -> dict[str, object]:
        """Serialize metadata to JSON-compatible values."""
        return {
            "format_name": self.format_name,
            "duration_seconds": self.duration_seconds,
            "width": self.width,
            "height": self.height,
            "frame_rate_fps": self.frame_rate_fps,
            "video_codec": self.video_codec,
            "orientation": self.orientation.value,
            "content_sha256": self.content_sha256,
            "file_size_bytes": self.file_size_bytes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> VideoMetadata:
        """Deserialize video metadata."""
        return cls(
            format_name=_required_str(data, "format_name"),
            duration_seconds=_required_float(data, "duration_seconds"),
            width=_required_int(data, "width"),
            height=_required_int(data, "height"),
            frame_rate_fps=_required_float(data, "frame_rate_fps"),
            video_codec=_required_str(data, "video_codec"),
            content_sha256=_required_str(data, "content_sha256"),
            file_size_bytes=_required_int(data, "file_size_bytes"),
        )


@dataclass(frozen=True, slots=True)
class BackgroundMediaRecord:
    """Authorized background media catalog record."""

    media_id: str
    created_at: str
    original_filename: str
    source_path: str
    license_note: str
    usage_note: str | None
    tags: tuple[str, ...]
    metadata: VideoMetadata
    schema_version: int = MEDIA_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        """Serialize the media record to JSON-compatible values."""
        return {
            "schema_version": self.schema_version,
            "media_id": self.media_id,
            "created_at": self.created_at,
            "original_filename": self.original_filename,
            "source_path": self.source_path,
            "license_note": self.license_note,
            "usage_note": self.usage_note,
            "tags": list(self.tags),
            "metadata": self.metadata.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> BackgroundMediaRecord:
        """Deserialize and validate a background media record."""
        schema_version = _required_int(data, "schema_version")
        if schema_version != MEDIA_SCHEMA_VERSION:
            raise ValueError(f"Unsupported media schema_version: {schema_version}")
        metadata_data = data.get("metadata")
        if not isinstance(metadata_data, Mapping):
            raise ValueError("metadata must be an object.")
        tags_data = data.get("tags")
        if not isinstance(tags_data, Sequence) or isinstance(tags_data, str):
            raise ValueError("tags must be a list of strings.")
        return cls(
            schema_version=schema_version,
            media_id=_required_str(data, "media_id"),
            created_at=_required_str(data, "created_at"),
            original_filename=_required_str(data, "original_filename"),
            source_path=_required_str(data, "source_path"),
            license_note=_required_str(data, "license_note"),
            usage_note=_optional_str(data, "usage_note"),
            tags=tuple(_required_sequence_str(tags_data, "tags")),
            metadata=VideoMetadata.from_dict(metadata_data),
        )


@dataclass(frozen=True, slots=True)
class ClipPreparationRecord:
    """Prepared background-media segment for a later render phase."""

    clip_id: str
    media_id: str
    created_at: str
    target_duration_seconds: float
    start_seconds: float
    end_seconds: float
    seed: int
    requested_orientation: str
    required_tags: tuple[str, ...]
    avoided_recent_media_ids: tuple[str, ...]
    schema_version: int = CLIP_SCHEMA_VERSION

    @property
    def duration_seconds(self) -> float:
        """Return selected segment duration."""
        return round(self.end_seconds - self.start_seconds, 3)

    def to_dict(self) -> dict[str, object]:
        """Serialize the clip record to JSON-compatible values."""
        return {
            "schema_version": self.schema_version,
            "clip_id": self.clip_id,
            "media_id": self.media_id,
            "created_at": self.created_at,
            "target_duration_seconds": self.target_duration_seconds,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "duration_seconds": self.duration_seconds,
            "seed": self.seed,
            "requested_orientation": self.requested_orientation,
            "required_tags": list(self.required_tags),
            "avoided_recent_media_ids": list(self.avoided_recent_media_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ClipPreparationRecord:
        """Deserialize and validate a clip-preparation record."""
        schema_version = _required_int(data, "schema_version")
        if schema_version != CLIP_SCHEMA_VERSION:
            raise ValueError(f"Unsupported clip schema_version: {schema_version}")
        required_tags = data.get("required_tags")
        if not isinstance(required_tags, Sequence) or isinstance(required_tags, str):
            raise ValueError("required_tags must be a list of strings.")
        avoided = data.get("avoided_recent_media_ids")
        if not isinstance(avoided, Sequence) or isinstance(avoided, str):
            raise ValueError("avoided_recent_media_ids must be a list of strings.")
        return cls(
            schema_version=schema_version,
            clip_id=_required_str(data, "clip_id"),
            media_id=_required_str(data, "media_id"),
            created_at=_required_str(data, "created_at"),
            target_duration_seconds=_required_float(data, "target_duration_seconds"),
            start_seconds=_required_float(data, "start_seconds"),
            end_seconds=_required_float(data, "end_seconds"),
            seed=_required_int(data, "seed"),
            requested_orientation=_required_str(data, "requested_orientation"),
            required_tags=tuple(_required_sequence_str(required_tags, "required_tags")),
            avoided_recent_media_ids=tuple(
                _required_sequence_str(avoided, "avoided_recent_media_ids")
            ),
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


def _optional_str(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null.")
    return value or None


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
