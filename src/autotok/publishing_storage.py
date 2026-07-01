"""Filesystem-backed publication storage for Phase 11."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autotok.errors import PersistenceError, UserInputError
from autotok.publishing_models import PublicationRecord, PublishingProvider

PUBLICATIONS_DIRNAME = "publications"
PUBLICATION_RECORD_FILENAME = "publication.json"


@dataclass(frozen=True, slots=True)
class StoredPublication:
    """A publication record and its filesystem location."""

    record: PublicationRecord
    record_path: Path
    created: bool = False


class PublicationStore:
    """Store local publication attempts and audit history."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.publications_dir = data_dir / PUBLICATIONS_DIRNAME

    def load(self, render_id: str, provider: PublishingProvider) -> StoredPublication:
        """Load a publication record for one render/provider pair."""
        record_path = self._record_path(render_id, provider)
        if not record_path.exists():
            raise UserInputError(
                f"Publication record was not found for {render_id} on {provider.value}."
            )
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Publication record JSON must be an object.")
            record = PublicationRecord.from_dict(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PersistenceError(
                f"Could not load publication record for {render_id} on {provider.value}."
            ) from exc
        return StoredPublication(record=record, record_path=record_path)

    def save(self, record: PublicationRecord, *, created: bool = False) -> StoredPublication:
        """Persist one publication record."""
        record_path = self._record_path(record.render_id, record.provider)
        try:
            record_path.parent.mkdir(parents=True, exist_ok=True)
            _write_json(record_path, record.to_dict())
        except OSError as exc:
            raise PersistenceError(
                f"Could not write publication record for {record.render_id}."
            ) from exc
        return StoredPublication(record=record, record_path=record_path, created=created)

    def exists(self, render_id: str, provider: PublishingProvider) -> bool:
        """Return whether a publication record exists."""
        return self._record_path(render_id, provider).exists()

    def list(self, *, provider: PublishingProvider | None = None) -> tuple[StoredPublication, ...]:
        """List publication records in deterministic order."""
        if not self.publications_dir.exists():
            return ()
        records: list[StoredPublication] = []
        for record_path in sorted(self.publications_dir.glob("render_*/*/publication.json")):
            provider_name = record_path.parent.name
            try:
                item_provider = PublishingProvider(provider_name)
            except ValueError:
                continue
            if provider is not None and item_provider is not provider:
                continue
            records.append(self.load(record_path.parent.parent.name, item_provider))
        return tuple(records)

    def _record_path(self, render_id: str, provider: PublishingProvider) -> Path:
        return self.publications_dir / render_id / provider.value / PUBLICATION_RECORD_FILENAME


def utc_timestamp() -> str:
    """Return a compact UTC timestamp for persisted records."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    """Create a compact local identifier."""
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)
