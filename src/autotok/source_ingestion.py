"""Source-post ingestion into canonical story records for Phase 7."""

from __future__ import annotations

from datetime import UTC, datetime

from autotok.errors import UserInputError
from autotok.models import SourceType, StoryRecord, StorySource
from autotok.normalization import (
    content_sha256,
    normalize_story_text,
    stable_story_id,
    validate_story_text,
)
from autotok.source_models import DiscoveredSourcePost, SourceProvider


def build_source_post_record(
    post: DiscoveredSourcePost,
    *,
    imported_at: datetime | None = None,
) -> StoryRecord:
    """Create a canonical story record from an approved discovered source post."""
    if post.provider is not SourceProvider.REDDIT:
        raise UserInputError(f"Unsupported source post provider: {post.provider.value}")

    original_text = post.story_text
    normalized_text = normalize_story_text(original_text)
    validate_story_text(normalized_text)
    digest = content_sha256(normalized_text)
    source = StorySource(
        source_type=SourceType.REDDIT_POST,
        imported_at=_utc_timestamp(imported_at),
        content_sha256=digest,
        original_character_count=len(original_text),
        normalized_character_count=len(normalized_text),
        title=post.title or None,
        source_identifier=post.source_id,
        source_url=post.source_url,
        retrieved_at=post.retrieved_at,
        source_label=post.source_label,
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
