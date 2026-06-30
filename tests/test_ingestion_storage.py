from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from autotok.errors import UserInputError
from autotok.ingestion import build_manual_file_record, build_manual_text_record
from autotok.models import SourceType
from autotok.storage import StoryStore

FIXED_TIME = datetime(2026, 6, 29, 12, 0, tzinfo=UTC)


def test_build_manual_text_record_has_stable_hash_and_metadata() -> None:
    record = build_manual_text_record(
        "  A small story.  ", title=" Local title ", imported_at=FIXED_TIME
    )

    assert record.story_id.startswith("story_")
    assert record.source.source_type is SourceType.MANUAL_TEXT
    assert record.source.title == "Local title"
    assert record.source.imported_at == "2026-06-29T12:00:00Z"
    assert record.original_text == "  A small story.  "
    assert record.normalized_text == "A small story."


def test_build_manual_file_record_reads_utf8_without_modifying_source(tmp_path: Path) -> None:
    story_file = tmp_path / "story.txt"
    original = "\ufeffLine one\r\nLine two with café"
    story_file.write_text(original, encoding="utf-8", newline="")

    record = build_manual_file_record(story_file, imported_at=FIXED_TIME)

    assert record.source.source_type is SourceType.MANUAL_FILE
    assert record.source.source_path == str(story_file.resolve())
    assert record.original_text == original
    assert record.normalized_text == "Line one\nLine two with café"
    with story_file.open("r", encoding="utf-8", newline="") as saved_story_file:
        assert saved_story_file.read() == original


def test_build_manual_file_record_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(UserInputError, match="does not exist"):
        build_manual_file_record(tmp_path / "missing.txt")


def test_story_store_saves_artifacts_and_reimports_idempotently(tmp_path: Path) -> None:
    store = StoryStore(tmp_path / "data")
    record = build_manual_text_record("Repeatable story", imported_at=FIXED_TIME)

    first = store.save(record)
    second = store.save(build_manual_text_record("Repeatable story", imported_at=FIXED_TIME))

    assert first.created is True
    assert second.created is False
    assert second.record.story_id == first.record.story_id
    assert first.original_text_path.read_text(encoding="utf-8") == "Repeatable story"
    assert first.normalized_text_path.read_text(encoding="utf-8") == "Repeatable story"
    payload: dict[str, Any] = json.loads(first.record_path.read_text(encoding="utf-8"))
    assert payload["story_id"] == record.story_id


def test_story_store_rejects_invalid_story_id(tmp_path: Path) -> None:
    store = StoryStore(tmp_path / "data")

    with pytest.raises(UserInputError, match="Story ID"):
        store.load("../record")
