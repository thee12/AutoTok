"""Text normalization for manually imported stories."""

from __future__ import annotations

import hashlib
import unicodedata

from autotok.errors import UserInputError

MAX_STORY_CHARACTERS = 200_000
STORY_ID_PREFIX = "story"
STORY_ID_HASH_LENGTH = 16


def normalize_story_text(text: str) -> str:
    """Normalize story text while preserving readable Unicode content."""
    normalized = unicodedata.normalize("NFC", text).replace("\ufeff", "")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    sanitized = "".join(
        character
        for character in normalized
        if character in {"\n", "\t"} or unicodedata.category(character) != "Cc"
    )
    return sanitized.strip()


def validate_story_text(normalized_text: str) -> None:
    """Validate normalized story text for Phase 1 ingestion."""
    if not normalized_text:
        raise UserInputError(
            "Story text is empty after normalization; provide non-empty UTF-8 text."
        )
    if len(normalized_text) > MAX_STORY_CHARACTERS:
        raise UserInputError(
            "Story text is too large for Phase 1 ingestion; "
            f"limit is {MAX_STORY_CHARACTERS} characters."
        )


def content_sha256(normalized_text: str) -> str:
    """Return the SHA-256 digest for normalized story text."""
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def stable_story_id(content_hash: str) -> str:
    """Build a filesystem-safe stable story ID from a content hash."""
    return f"{STORY_ID_PREFIX}_{content_hash[:STORY_ID_HASH_LENGTH]}"
