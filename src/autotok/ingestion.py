"""Manual story ingestion for Phase 1."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from autotok.errors import UserInputError
from autotok.models import SourceType, StoryRecord, StorySource
from autotok.normalization import (
    content_sha256,
    normalize_story_text,
    stable_story_id,
    validate_story_text,
)


def build_manual_text_record(
    text: str,
    *,
    title: str | None = None,
    imported_at: datetime | None = None,
) -> StoryRecord:
    """Create a canonical story record from manually supplied text."""
    return _build_record(
        original_text=text,
        source_type=SourceType.MANUAL_TEXT,
        title=title,
        source_path=None,
        imported_at=imported_at,
    )


def build_manual_file_record(
    path: Path,
    *,
    title: str | None = None,
    imported_at: datetime | None = None,
) -> StoryRecord:
    """Create a canonical story record from a local UTF-8 text file."""
    source_path = path.expanduser()
    if not source_path.exists():
        raise UserInputError(f"Story file does not exist: {source_path}")
    if not source_path.is_file():
        raise UserInputError(f"Story path is not a file: {source_path}")

    try:
        with source_path.open("r", encoding="utf-8", newline="") as story_file:
            original_text = story_file.read()
    except UnicodeDecodeError as exc:
        raise UserInputError(
            f"Story file must be valid UTF-8 text: {source_path}. Save it as UTF-8 and try again."
        ) from exc
    except OSError as exc:
        raise UserInputError(f"Could not read story file: {source_path}") from exc

    return _build_record(
        original_text=original_text,
        source_type=SourceType.MANUAL_FILE,
        title=title,
        source_path=str(source_path.resolve()),
        imported_at=imported_at,
    )


def _build_record(
    *,
    original_text: str,
    source_type: SourceType,
    title: str | None,
    source_path: str | None,
    imported_at: datetime | None,
) -> StoryRecord:
    normalized_text = normalize_story_text(original_text)
    validate_story_text(normalized_text)
    digest = content_sha256(normalized_text)
    timestamp = _utc_timestamp(imported_at)
    source = StorySource(
        source_type=source_type,
        imported_at=timestamp,
        content_sha256=digest,
        original_character_count=len(original_text),
        normalized_character_count=len(normalized_text),
        title=_clean_optional_title(title),
        source_path=source_path,
    )
    return StoryRecord(
        story_id=stable_story_id(digest),
        source=source,
        original_text=original_text,
        normalized_text=normalized_text,
    )


def _utc_timestamp(value: datetime | None) -> str:
    timestamp = datetime.now(UTC) if value is None else value.astimezone(UTC)
    return timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_optional_title(title: str | None) -> str | None:
    if title is None:
        return None
    cleaned = title.strip()
    if not cleaned:
        raise UserInputError("Story title must not be empty when provided.")
    return cleaned
