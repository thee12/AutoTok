"""Filesystem storage for Phase 8 content gate artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autotok.content_gate_models import ContentGateRecord, OverrideEvent
from autotok.errors import PersistenceError, UserInputError

GATE_ID_PATTERN = re.compile(r"^gate_[a-f0-9]{16}$")
STORY_ID_PATTERN = re.compile(r"^story_[a-f0-9]{16}$")


@dataclass(frozen=True, slots=True)
class StoredContentGate:
    """A content gate record loaded from or saved to the artifact workspace."""

    record: ContentGateRecord
    record_path: Path
    created: bool = False


class ContentGateStore:
    """Store Phase 8 content gate records in a local filesystem workspace."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.gates_dir = data_dir / "content_gates"

    def save(self, record: ContentGateRecord) -> StoredContentGate:
        """Persist a content gate record idempotently."""
        record_dir = self._record_dir(record.story_id)
        record_path = record_dir / "record.json"
        if record_path.exists():
            existing = self.load_for_story(record.story_id)
            if existing.record.gate_id == record.gate_id:
                return StoredContentGate(
                    record=existing.record,
                    record_path=existing.record_path,
                    created=False,
                )
        try:
            record_dir.mkdir(parents=True, exist_ok=True)
            _write_json(record_path, record.to_dict())
        except OSError as exc:
            raise PersistenceError(
                f"Could not write content gate artifacts for {record.story_id}."
            ) from exc
        return StoredContentGate(record=record, record_path=record_path, created=True)

    def load_for_story(self, story_id: str) -> StoredContentGate:
        """Load the stored content gate for a story ID."""
        _validate_story_id(story_id)
        record_path = self._record_dir(story_id) / "record.json"
        if not record_path.exists():
            raise UserInputError(f"Content gate record was not found for story: {story_id}")
        return self._load_path(record_path, created=False)

    def load(self, gate_id: str) -> StoredContentGate:
        """Load a stored content gate by gate ID."""
        _validate_gate_id(gate_id)
        for record_path in self.gates_dir.glob("story_*/record.json"):
            stored = self._load_path(record_path, created=False)
            if stored.record.gate_id == gate_id:
                return stored
        raise UserInputError(f"Content gate record was not found: {gate_id}")

    def append_override(self, story_id: str, event: OverrideEvent) -> StoredContentGate:
        """Append a manual override event to an existing gate record."""
        stored = self.load_for_story(story_id)
        updated = stored.record.with_override(event)
        try:
            _write_json(stored.record_path, updated.to_dict())
        except OSError as exc:
            raise PersistenceError(
                f"Could not write content gate override for {story_id}."
            ) from exc
        return StoredContentGate(record=updated, record_path=stored.record_path, created=False)

    def _load_path(self, record_path: Path, *, created: bool) -> StoredContentGate:
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Content gate JSON must be an object.")
            record = ContentGateRecord.from_dict(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PersistenceError(f"Could not load content gate record: {record_path}") from exc
        return StoredContentGate(record=record, record_path=record_path, created=created)

    def _record_dir(self, story_id: str) -> Path:
        _validate_story_id(story_id)
        return self.gates_dir / story_id


def _validate_story_id(story_id: str) -> None:
    if STORY_ID_PATTERN.fullmatch(story_id) is None:
        raise UserInputError(
            "Story ID must look like story_ followed by 16 lowercase hexadecimal characters."
        )


def _validate_gate_id(gate_id: str) -> None:
    if GATE_ID_PATTERN.fullmatch(gate_id) is None:
        raise UserInputError(
            "Gate ID must look like gate_ followed by 16 lowercase hexadecimal characters."
        )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)
