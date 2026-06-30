"""Filesystem storage for Phase 1 story artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autotok.errors import PersistenceError, UserInputError
from autotok.models import StoryRecord

STORY_ID_PATTERN = re.compile(r"^story_[a-f0-9]{16}$")


@dataclass(frozen=True, slots=True)
class StoredStory:
    """A story record loaded from or saved to the artifact workspace."""

    record: StoryRecord
    record_path: Path
    original_text_path: Path
    normalized_text_path: Path
    created: bool = False


class StoryStore:
    """Store Phase 1 story records in a local filesystem workspace."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.sources_dir = data_dir / "sources"

    def save(self, record: StoryRecord) -> StoredStory:
        """Persist a story record idempotently and return its artifact paths."""
        record_dir = self._record_dir(record.story_id)
        record_path = record_dir / "record.json"
        original_text_path = record_dir / "original.txt"
        normalized_text_path = record_dir / "normalized.txt"

        if record_path.exists():
            existing = self.load(record.story_id)
            if existing.record.source.content_sha256 != record.source.content_sha256:
                raise PersistenceError(
                    "Story ID collision for "
                    f"{record.story_id}; existing artifact has a different hash."
                )
            return StoredStory(
                record=existing.record,
                record_path=existing.record_path,
                original_text_path=existing.original_text_path,
                normalized_text_path=existing.normalized_text_path,
                created=False,
            )

        try:
            record_dir.mkdir(parents=True, exist_ok=True)
            _write_text(original_text_path, record.original_text)
            _write_text(normalized_text_path, record.normalized_text)
            _write_json(record_path, record.to_dict())
        except OSError as exc:
            raise PersistenceError(
                f"Could not write story artifacts for {record.story_id}."
            ) from exc

        return StoredStory(
            record=record,
            record_path=record_path,
            original_text_path=original_text_path,
            normalized_text_path=normalized_text_path,
            created=True,
        )

    def load(self, story_id: str) -> StoredStory:
        """Load a stored story by ID."""
        _validate_story_id(story_id)
        record_dir = self._record_dir(story_id)
        record_path = record_dir / "record.json"
        original_text_path = record_dir / "original.txt"
        normalized_text_path = record_dir / "normalized.txt"
        if not record_path.exists():
            raise UserInputError(f"Story record was not found: {story_id}")

        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Story record JSON must be an object.")
            record = StoryRecord.from_dict(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PersistenceError(f"Could not load story record: {story_id}") from exc

        return StoredStory(
            record=record,
            record_path=record_path,
            original_text_path=original_text_path,
            normalized_text_path=normalized_text_path,
            created=False,
        )

    def _record_dir(self, story_id: str) -> Path:
        _validate_story_id(story_id)
        return self.sources_dir / story_id


def _validate_story_id(story_id: str) -> None:
    if STORY_ID_PATTERN.fullmatch(story_id) is None:
        raise UserInputError(
            "Story ID must look like story_ followed by 16 lowercase hexadecimal characters."
        )


def _write_text(path: Path, text: str) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(text, encoding="utf-8", newline="\n")
    temp_path.replace(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)
