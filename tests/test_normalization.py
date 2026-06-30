from __future__ import annotations

import pytest

from autotok.errors import UserInputError
from autotok.normalization import (
    content_sha256,
    normalize_story_text,
    stable_story_id,
    validate_story_text,
)


def test_normalize_story_text_preserves_unicode_and_line_endings() -> None:
    text = "\ufeffCafe\u0301\r\nsecond line\x00\x08"

    normalized = normalize_story_text(text)

    assert normalized == "Café\nsecond line"


def test_validate_story_text_rejects_empty_content() -> None:
    with pytest.raises(UserInputError, match="empty"):
        validate_story_text(normalize_story_text("\x00\r\n  "))


def test_stable_story_id_uses_content_hash_prefix() -> None:
    digest = content_sha256("same story")

    assert stable_story_id(digest) == f"story_{digest[:16]}"
