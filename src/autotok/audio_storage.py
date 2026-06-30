"""Filesystem storage for Phase 3 narration audio artifacts."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autotok.audio_models import NarrationAudioRecord
from autotok.errors import PersistenceError, UserInputError

AUDIO_ID_PATTERN = re.compile(r"^audio_[a-f0-9]{16}$")


@dataclass(frozen=True, slots=True)
class StoredAudio:
    """A narration audio record and its artifact paths."""

    record: NarrationAudioRecord
    record_path: Path
    audio_path: Path
    created: bool = False


class AudioStore:
    """Store Phase 3 narration audio artifacts in the local workspace."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.audio_dir = data_dir / "audio"

    def save(self, record: NarrationAudioRecord, *, source_audio_path: Path) -> StoredAudio:
        """Persist audio metadata and copy the validated WAV artifact."""
        record_dir = self._record_dir(record.audio_id)
        record_path = record_dir / "record.json"
        audio_path = record_dir / "narration.wav"

        if record_path.exists():
            existing = self.load(record.audio_id)
            if existing.record.metadata.content_sha256 != record.metadata.content_sha256:
                raise PersistenceError(
                    "Audio ID collision for "
                    f"{record.audio_id}; existing artifact has a different hash."
                )
            return StoredAudio(
                record=existing.record,
                record_path=existing.record_path,
                audio_path=existing.audio_path,
                created=False,
            )

        try:
            record_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_audio_path, audio_path)
            _write_json(record_path, record.to_dict())
        except OSError as exc:
            raise PersistenceError(
                f"Could not write audio artifacts for {record.audio_id}."
            ) from exc

        return StoredAudio(
            record=record,
            record_path=record_path,
            audio_path=audio_path,
            created=True,
        )

    def load(self, audio_id: str) -> StoredAudio:
        """Load a stored audio record by ID."""
        _validate_audio_id(audio_id)
        record_dir = self._record_dir(audio_id)
        record_path = record_dir / "record.json"
        audio_path = record_dir / "narration.wav"
        if not record_path.exists():
            raise UserInputError(f"Audio record was not found: {audio_id}")

        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Audio record JSON must be an object.")
            record = NarrationAudioRecord.from_dict(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PersistenceError(f"Could not load audio record: {audio_id}") from exc

        return StoredAudio(record=record, record_path=record_path, audio_path=audio_path)

    def _record_dir(self, audio_id: str) -> Path:
        _validate_audio_id(audio_id)
        return self.audio_dir / audio_id


def _validate_audio_id(audio_id: str) -> None:
    if AUDIO_ID_PATTERN.fullmatch(audio_id) is None:
        raise UserInputError(
            "Audio ID must look like audio_ followed by 16 lowercase hexadecimal characters."
        )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)
