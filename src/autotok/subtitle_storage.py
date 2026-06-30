"""Filesystem storage for Phase 4 subtitle artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autotok.errors import PersistenceError, UserInputError
from autotok.subtitle_models import SubtitleDocument, SubtitleExportFormat
from autotok.subtitles import export_subtitles

SUBTITLE_ID_PATTERN = re.compile(r"^subtitle_[a-f0-9]{16}$")


@dataclass(frozen=True, slots=True)
class StoredSubtitle:
    """A subtitle document and its artifact paths."""

    document: SubtitleDocument
    record_path: Path
    export_path: Path
    created: bool = False


class SubtitleStore:
    """Store Phase 4 subtitle artifacts in the local workspace."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.subtitles_dir = data_dir / "subtitles"

    def save(self, document: SubtitleDocument) -> StoredSubtitle:
        """Persist a subtitle document idempotently."""
        record_dir = self._record_dir(document.subtitle_id)
        record_path = record_dir / "record.json"
        export_path = record_dir / f"subtitles.{document.metadata.export_format.value}"

        if record_path.exists():
            existing = self.load(document.subtitle_id)
            if existing.document.script_id != document.script_id:
                raise PersistenceError(
                    "Subtitle ID collision for "
                    f"{document.subtitle_id}; existing artifact has a different script."
                )
            return StoredSubtitle(
                document=existing.document,
                record_path=existing.record_path,
                export_path=existing.export_path,
                created=False,
            )

        try:
            record_dir.mkdir(parents=True, exist_ok=True)
            _write_json(record_path, document.to_dict())
            _write_text(export_path, export_subtitles(document, document.metadata.export_format))
        except OSError as exc:
            raise PersistenceError(
                f"Could not write subtitle artifacts for {document.subtitle_id}."
            ) from exc

        return StoredSubtitle(
            document=document,
            record_path=record_path,
            export_path=export_path,
            created=True,
        )

    def load(self, subtitle_id: str) -> StoredSubtitle:
        """Load a stored subtitle document by ID."""
        _validate_subtitle_id(subtitle_id)
        record_dir = self._record_dir(subtitle_id)
        record_path = record_dir / "record.json"
        if not record_path.exists():
            raise UserInputError(f"Subtitle record was not found: {subtitle_id}")

        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Subtitle record JSON must be an object.")
            document = SubtitleDocument.from_dict(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PersistenceError(f"Could not load subtitle record: {subtitle_id}") from exc

        export_path = record_dir / f"subtitles.{document.metadata.export_format.value}"
        return StoredSubtitle(document=document, record_path=record_path, export_path=export_path)

    def export(self, subtitle_id: str, export_format: SubtitleExportFormat) -> Path:
        """Write an additional export format for a stored subtitle document."""
        stored = self.load(subtitle_id)
        export_path = self._record_dir(subtitle_id) / f"subtitles.{export_format.value}"
        try:
            _write_text(export_path, export_subtitles(stored.document, export_format))
        except OSError as exc:
            raise PersistenceError(f"Could not export subtitle record: {subtitle_id}") from exc
        return export_path

    def _record_dir(self, subtitle_id: str) -> Path:
        _validate_subtitle_id(subtitle_id)
        return self.subtitles_dir / subtitle_id


def _validate_subtitle_id(subtitle_id: str) -> None:
    if SUBTITLE_ID_PATTERN.fullmatch(subtitle_id) is None:
        raise UserInputError(
            "Subtitle ID must look like subtitle_ followed by 16 lowercase hexadecimal characters."
        )


def _write_text(path: Path, text: str) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(text, encoding="utf-8", newline="\n")
    temp_path.replace(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)
