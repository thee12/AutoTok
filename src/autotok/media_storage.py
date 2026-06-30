"""Filesystem storage for Phase 5 background media artifacts."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autotok.errors import PersistenceError, UserInputError
from autotok.media_models import BackgroundMediaRecord, ClipPreparationRecord

MEDIA_ID_PATTERN = re.compile(r"^media_[a-f0-9]{16}$")
CLIP_ID_PATTERN = re.compile(r"^clip_[a-f0-9]{16}$")


@dataclass(frozen=True, slots=True)
class StoredMedia:
    """A cataloged background media record and artifact paths."""

    record: BackgroundMediaRecord
    record_path: Path
    media_path: Path
    created: bool = False


@dataclass(frozen=True, slots=True)
class StoredClip:
    """A prepared background clip record and artifact path."""

    record: ClipPreparationRecord
    record_path: Path
    created: bool = False


class MediaStore:
    """Store Phase 5 background media and clip-preparation artifacts."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.media_dir = data_dir / "media"
        self.clips_dir = data_dir / "clips"

    def save_media(self, record: BackgroundMediaRecord, *, source_media_path: Path) -> StoredMedia:
        """Persist a media catalog record idempotently and copy the source file."""
        record_dir = self._media_record_dir(record.media_id)
        record_path = record_dir / "record.json"
        media_path = record_dir / f"source{source_media_path.suffix.lower()}"

        if record_path.exists():
            existing = self.load_media(record.media_id)
            if existing.record.metadata.content_sha256 != record.metadata.content_sha256:
                raise PersistenceError(
                    "Media ID collision for "
                    f"{record.media_id}; existing artifact has a different hash."
                )
            return StoredMedia(
                record=existing.record,
                record_path=existing.record_path,
                media_path=existing.media_path,
                created=False,
            )

        try:
            record_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_media_path, media_path)
            _write_json(record_path, record.to_dict())
        except OSError as exc:
            raise PersistenceError(
                f"Could not write media artifacts for {record.media_id}."
            ) from exc

        return StoredMedia(
            record=record,
            record_path=record_path,
            media_path=media_path,
            created=True,
        )

    def load_media(self, media_id: str) -> StoredMedia:
        """Load a stored background media record by ID."""
        _validate_media_id(media_id)
        record_dir = self._media_record_dir(media_id)
        record_path = record_dir / "record.json"
        if not record_path.exists():
            raise UserInputError(f"Media record was not found: {media_id}")
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Media record JSON must be an object.")
            record = BackgroundMediaRecord.from_dict(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PersistenceError(f"Could not load media record: {media_id}") from exc
        media_path = _stored_source_path(record_dir)
        return StoredMedia(record=record, record_path=record_path, media_path=media_path)

    def list_media(self) -> tuple[BackgroundMediaRecord, ...]:
        """Return all cataloged media records sorted by ID."""
        if not self.media_dir.exists():
            return ()
        records: list[BackgroundMediaRecord] = []
        for record_path in sorted(self.media_dir.glob("media_*/record.json")):
            records.append(self.load_media(record_path.parent.name).record)
        return tuple(records)

    def save_clip(self, record: ClipPreparationRecord) -> StoredClip:
        """Persist a clip-preparation record idempotently."""
        record_dir = self._clip_record_dir(record.clip_id)
        record_path = record_dir / "record.json"
        if record_path.exists():
            existing = self.load_clip(record.clip_id)
            return StoredClip(
                record=existing.record,
                record_path=existing.record_path,
                created=False,
            )
        try:
            record_dir.mkdir(parents=True, exist_ok=True)
            _write_json(record_path, record.to_dict())
        except OSError as exc:
            raise PersistenceError(f"Could not write clip artifact for {record.clip_id}.") from exc
        return StoredClip(record=record, record_path=record_path, created=True)

    def load_clip(self, clip_id: str) -> StoredClip:
        """Load a prepared clip record by ID."""
        _validate_clip_id(clip_id)
        record_path = self._clip_record_dir(clip_id) / "record.json"
        if not record_path.exists():
            raise UserInputError(f"Clip record was not found: {clip_id}")
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Clip record JSON must be an object.")
            record = ClipPreparationRecord.from_dict(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PersistenceError(f"Could not load clip record: {clip_id}") from exc
        return StoredClip(record=record, record_path=record_path)

    def list_clips(self) -> tuple[ClipPreparationRecord, ...]:
        """Return all prepared clip records sorted by ID."""
        if not self.clips_dir.exists():
            return ()
        records: list[ClipPreparationRecord] = []
        for record_path in sorted(self.clips_dir.glob("clip_*/record.json")):
            records.append(self.load_clip(record_path.parent.name).record)
        return tuple(records)

    def _media_record_dir(self, media_id: str) -> Path:
        _validate_media_id(media_id)
        return self.media_dir / media_id

    def _clip_record_dir(self, clip_id: str) -> Path:
        _validate_clip_id(clip_id)
        return self.clips_dir / clip_id


def _stored_source_path(record_dir: Path) -> Path:
    matches = sorted(path for path in record_dir.glob("source*") if path.is_file())
    if not matches:
        raise PersistenceError(f"Stored media source is missing: {record_dir}")
    return matches[0]


def _validate_media_id(media_id: str) -> None:
    if MEDIA_ID_PATTERN.fullmatch(media_id) is None:
        raise UserInputError(
            "Media ID must look like media_ followed by 16 lowercase hexadecimal characters."
        )


def _validate_clip_id(clip_id: str) -> None:
    if CLIP_ID_PATTERN.fullmatch(clip_id) is None:
        raise UserInputError(
            "Clip ID must look like clip_ followed by 16 lowercase hexadecimal characters."
        )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)
