"""Narration audio models for Phase 3 artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

AUDIO_SCHEMA_VERSION = 1


class AudioSourceType(StrEnum):
    """Supported Phase 3 narration audio source types."""

    TTS_GENERATED = "tts_generated"
    MANUAL_FILE = "manual_file"


@dataclass(frozen=True, slots=True)
class AudioMetadata:
    """Validated WAV narration audio metadata."""

    format_name: str
    duration_seconds: float
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int
    frame_count: int
    content_sha256: str
    file_size_bytes: int

    def to_dict(self) -> dict[str, object]:
        """Serialize metadata to JSON-compatible values."""
        return {
            "format_name": self.format_name,
            "duration_seconds": self.duration_seconds,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "sample_width_bytes": self.sample_width_bytes,
            "frame_count": self.frame_count,
            "content_sha256": self.content_sha256,
            "file_size_bytes": self.file_size_bytes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> AudioMetadata:
        """Deserialize audio metadata."""
        return cls(
            format_name=_required_str(data, "format_name"),
            duration_seconds=_required_float(data, "duration_seconds"),
            sample_rate_hz=_required_int(data, "sample_rate_hz"),
            channels=_required_int(data, "channels"),
            sample_width_bytes=_required_int(data, "sample_width_bytes"),
            frame_count=_required_int(data, "frame_count"),
            content_sha256=_required_str(data, "content_sha256"),
            file_size_bytes=_required_int(data, "file_size_bytes"),
        )


@dataclass(frozen=True, slots=True)
class NarrationAudioRecord:
    """Validated narration audio artifact for an approved script."""

    audio_id: str
    script_id: str
    story_id: str
    source_type: AudioSourceType
    provider_name: str
    provider_version: str
    created_at: str
    metadata: AudioMetadata
    provider_request: dict[str, object]
    source_path: str | None = None
    normalized: bool = False
    schema_version: int = AUDIO_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        """Serialize the audio record to JSON-compatible values."""
        return {
            "schema_version": self.schema_version,
            "audio_id": self.audio_id,
            "script_id": self.script_id,
            "story_id": self.story_id,
            "source_type": self.source_type.value,
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "created_at": self.created_at,
            "metadata": self.metadata.to_dict(),
            "provider_request": self.provider_request,
            "source_path": self.source_path,
            "normalized": self.normalized,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> NarrationAudioRecord:
        """Deserialize and validate a narration audio record."""
        schema_version = _required_int(data, "schema_version")
        if schema_version != AUDIO_SCHEMA_VERSION:
            raise ValueError(f"Unsupported audio schema_version: {schema_version}")

        try:
            source_type = AudioSourceType(_required_str(data, "source_type"))
        except ValueError as exc:
            raise ValueError("source_type is unsupported.") from exc

        metadata_data = data.get("metadata")
        if not isinstance(metadata_data, Mapping):
            raise ValueError("metadata must be an object.")
        provider_request = data.get("provider_request")
        if not isinstance(provider_request, dict):
            raise ValueError("provider_request must be an object.")

        return cls(
            schema_version=schema_version,
            audio_id=_required_str(data, "audio_id"),
            script_id=_required_str(data, "script_id"),
            story_id=_required_str(data, "story_id"),
            source_type=source_type,
            provider_name=_required_str(data, "provider_name"),
            provider_version=_required_str(data, "provider_version"),
            created_at=_required_str(data, "created_at"),
            metadata=AudioMetadata.from_dict(metadata_data),
            provider_request=provider_request,
            source_path=_optional_str(data, "source_path"),
            normalized=_required_bool(data, "normalized"),
        )


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


def _required_bool(data: Mapping[str, object], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean.")
    return value
