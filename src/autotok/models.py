"""Canonical source and story models for AutoTok."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

SCHEMA_VERSION = 1


class SourceType(StrEnum):
    """Supported Phase 1 source types."""

    MANUAL_TEXT = "manual_text"
    MANUAL_FILE = "manual_file"


@dataclass(frozen=True, slots=True)
class StorySource:
    """Metadata describing where a manually imported story came from."""

    source_type: SourceType
    imported_at: str
    content_sha256: str
    original_character_count: int
    normalized_character_count: int
    title: str | None = None
    source_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize source metadata to JSON-compatible values."""
        return {
            "source_type": self.source_type.value,
            "imported_at": self.imported_at,
            "content_sha256": self.content_sha256,
            "original_character_count": self.original_character_count,
            "normalized_character_count": self.normalized_character_count,
            "title": self.title,
            "source_path": self.source_path,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> StorySource:
        """Deserialize and validate source metadata."""
        source_type_value = _required_str(data, "source_type")
        try:
            source_type = SourceType(source_type_value)
        except ValueError as exc:
            raise ValueError(f"Unsupported source_type: {source_type_value}") from exc

        return cls(
            source_type=source_type,
            imported_at=_required_str(data, "imported_at"),
            content_sha256=_required_str(data, "content_sha256"),
            original_character_count=_required_int(data, "original_character_count"),
            normalized_character_count=_required_int(data, "normalized_character_count"),
            title=_optional_str(data, "title"),
            source_path=_optional_str(data, "source_path"),
        )


@dataclass(frozen=True, slots=True)
class StoryRecord:
    """Canonical Phase 1 record for a manually imported story."""

    story_id: str
    source: StorySource
    original_text: str
    normalized_text: str
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        """Serialize the story record to JSON-compatible values."""
        return {
            "schema_version": self.schema_version,
            "story_id": self.story_id,
            "source": self.source.to_dict(),
            "original_text": self.original_text,
            "normalized_text": self.normalized_text,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> StoryRecord:
        """Deserialize and validate a story record."""
        schema_version = _required_int(data, "schema_version")
        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported story record schema_version: {schema_version}")

        source_data = data.get("source")
        if not isinstance(source_data, Mapping):
            raise ValueError("Story record source must be an object.")

        return cls(
            schema_version=schema_version,
            story_id=_required_str(data, "story_id"),
            source=StorySource.from_dict(source_data),
            original_text=_required_str(data, "original_text"),
            normalized_text=_required_str(data, "normalized_text"),
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
