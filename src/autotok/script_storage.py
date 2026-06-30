"""Filesystem storage for Phase 2 narration script artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autotok.errors import PersistenceError, UserInputError
from autotok.script_models import NarrationScriptRecord

SCRIPT_ID_PATTERN = re.compile(r"^script_[a-f0-9]{16}$")


@dataclass(frozen=True, slots=True)
class StoredScript:
    """A narration script record and its artifact paths."""

    record: NarrationScriptRecord
    record_path: Path
    before_text_path: Path
    script_text_path: Path
    created: bool = False


class ScriptStore:
    """Store Phase 2 narration script artifacts in the local workspace."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.scripts_dir = data_dir / "scripts"

    def save(self, record: NarrationScriptRecord, *, before_text: str) -> StoredScript:
        """Persist a script idempotently and return artifact paths."""
        record_dir = self._record_dir(record.script_id)
        record_path = record_dir / "record.json"
        before_text_path = record_dir / "before.txt"
        script_text_path = record_dir / "script.txt"

        if record_path.exists():
            existing = self.load(record.script_id)
            if existing.record.story_id != record.story_id:
                raise PersistenceError(
                    "Script ID collision for "
                    f"{record.script_id}; existing artifact has a different story."
                )
            return StoredScript(
                record=existing.record,
                record_path=existing.record_path,
                before_text_path=existing.before_text_path,
                script_text_path=existing.script_text_path,
                created=False,
            )

        try:
            record_dir.mkdir(parents=True, exist_ok=True)
            _write_text(before_text_path, before_text)
            _write_text(script_text_path, record.full_text)
            _write_json(record_path, record.to_dict())
        except OSError as exc:
            raise PersistenceError(
                f"Could not write script artifacts for {record.script_id}."
            ) from exc

        return StoredScript(
            record=record,
            record_path=record_path,
            before_text_path=before_text_path,
            script_text_path=script_text_path,
            created=True,
        )

    def load(self, script_id: str) -> StoredScript:
        """Load a stored script by ID."""
        _validate_script_id(script_id)
        record_dir = self._record_dir(script_id)
        record_path = record_dir / "record.json"
        before_text_path = record_dir / "before.txt"
        script_text_path = record_dir / "script.txt"
        if not record_path.exists():
            raise UserInputError(f"Script record was not found: {script_id}")

        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Script record JSON must be an object.")
            record = NarrationScriptRecord.from_dict(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PersistenceError(f"Could not load script record: {script_id}") from exc

        return StoredScript(
            record=record,
            record_path=record_path,
            before_text_path=before_text_path,
            script_text_path=script_text_path,
            created=False,
        )

    def approve(self, script_id: str, *, approved_at: datetime | None = None) -> StoredScript:
        """Mark a script approved and update its record artifact."""
        stored = self.load(script_id)
        timestamp = datetime.now(UTC) if approved_at is None else approved_at.astimezone(UTC)
        approved_record = stored.record.approve(
            timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        try:
            _write_json(stored.record_path, approved_record.to_dict())
        except OSError as exc:
            raise PersistenceError(f"Could not approve script record: {script_id}") from exc
        return StoredScript(
            record=approved_record,
            record_path=stored.record_path,
            before_text_path=stored.before_text_path,
            script_text_path=stored.script_text_path,
            created=False,
        )

    def _record_dir(self, script_id: str) -> Path:
        _validate_script_id(script_id)
        return self.scripts_dir / script_id


def _validate_script_id(script_id: str) -> None:
    if SCRIPT_ID_PATTERN.fullmatch(script_id) is None:
        raise UserInputError(
            "Script ID must look like script_ followed by 16 lowercase hexadecimal characters."
        )


def _write_text(path: Path, text: str) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(text, encoding="utf-8", newline="\n")
    temp_path.replace(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)
