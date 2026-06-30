"""Filesystem storage for Phase 7 source discovery artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autotok.errors import PersistenceError, UserInputError
from autotok.source_adapters import CachedRetrievalProtocol
from autotok.source_models import SourceDiscoveryRun, SourceProvider

DISCOVERY_ID_PATTERN = re.compile(r"^discovery_[a-f0-9]{16}$")
CACHE_KEY_PATTERN = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True, slots=True)
class StoredSourceDiscovery:
    """A discovery run loaded from or saved to the artifact workspace."""

    record: SourceDiscoveryRun
    record_path: Path
    raw_pages_dir: Path
    raw_page_paths: tuple[Path, ...]
    created: bool = False


@dataclass(frozen=True, slots=True)
class CachedRetrieval:
    """A cached raw source retrieval response."""

    payload: dict[str, object]
    headers: dict[str, str]
    cache_path: Path


class SourceDiscoveryStore:
    """Store Phase 7 source discovery records in a local filesystem workspace."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.discovery_dir = data_dir / "source_discovery"

    def save(
        self,
        record: SourceDiscoveryRun,
        *,
        raw_pages: tuple[dict[str, object], ...] = (),
    ) -> StoredSourceDiscovery:
        """Persist a discovery run idempotently and return artifact paths."""
        run_dir = self._record_dir(record.discovery_id)
        record_path = run_dir / "record.json"
        raw_pages_dir = run_dir / "raw_pages"
        raw_page_paths = tuple(
            raw_pages_dir / f"page_{index:03d}.json" for index in range(1, len(raw_pages) + 1)
        )

        if record_path.exists():
            existing = self.load(record.discovery_id)
            return StoredSourceDiscovery(
                record=existing.record,
                record_path=existing.record_path,
                raw_pages_dir=existing.raw_pages_dir,
                raw_page_paths=existing.raw_page_paths,
                created=False,
            )

        try:
            raw_pages_dir.mkdir(parents=True, exist_ok=True)
            for path, payload in zip(raw_page_paths, raw_pages, strict=True):
                _write_json(path, payload)
            _write_json(record_path, record.to_dict())
        except OSError as exc:
            raise PersistenceError(
                f"Could not write source discovery artifacts for {record.discovery_id}."
            ) from exc

        return StoredSourceDiscovery(
            record=record,
            record_path=record_path,
            raw_pages_dir=raw_pages_dir,
            raw_page_paths=raw_page_paths,
            created=True,
        )

    def load(self, discovery_id: str) -> StoredSourceDiscovery:
        """Load a stored discovery run by ID."""
        _validate_discovery_id(discovery_id)
        run_dir = self._record_dir(discovery_id)
        record_path = run_dir / "record.json"
        raw_pages_dir = run_dir / "raw_pages"
        if not record_path.exists():
            raise UserInputError(f"Source discovery record was not found: {discovery_id}")

        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Discovery record JSON must be an object.")
            record = SourceDiscoveryRun.from_dict(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PersistenceError(
                f"Could not load source discovery record: {discovery_id}"
            ) from exc

        raw_page_paths = (
            tuple(sorted(raw_pages_dir.glob("page_*.json"))) if raw_pages_dir.exists() else ()
        )
        return StoredSourceDiscovery(
            record=record,
            record_path=record_path,
            raw_pages_dir=raw_pages_dir,
            raw_page_paths=raw_page_paths,
            created=False,
        )

    def _record_dir(self, discovery_id: str) -> Path:
        _validate_discovery_id(discovery_id)
        return self.discovery_dir / discovery_id


class SourceRetrievalCache:
    """Cache raw source retrieval responses without storing secrets."""

    def __init__(self, data_dir: Path, provider: SourceProvider) -> None:
        self.cache_dir = data_dir / "cache" / "source_retrieval" / provider.value

    def load(self, cache_key: str) -> CachedRetrievalProtocol | None:
        """Return a cached retrieval response when present."""
        _validate_cache_key(cache_key)
        cache_path = self.cache_dir / f"{cache_key}.json"
        if not cache_path.exists():
            return None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Cache payload must be an object.")
            response_payload = payload.get("payload")
            response_headers = payload.get("headers")
            if not isinstance(response_payload, dict):
                raise ValueError("Cached response payload must be an object.")
            if not isinstance(response_headers, dict):
                raise ValueError("Cached response headers must be an object.")
            headers = {
                str(key): str(value)
                for key, value in response_headers.items()
                if isinstance(key, str) and isinstance(value, (str, int, float))
            }
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise PersistenceError(f"Could not load source retrieval cache: {cache_key}") from exc
        return CachedRetrieval(payload=response_payload, headers=headers, cache_path=cache_path)

    def save(
        self,
        cache_key: str,
        *,
        payload: dict[str, object],
        headers: dict[str, str],
        url: str,
        cached_at: str,
    ) -> Path:
        """Persist a raw retrieval response and return the cache path."""
        _validate_cache_key(cache_key)
        cache_path = self.cache_dir / f"{cache_key}.json"
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            _write_json(
                cache_path,
                {
                    "cache_key": cache_key,
                    "cached_at": cached_at,
                    "url": url,
                    "headers": headers,
                    "payload": payload,
                },
            )
        except OSError as exc:
            raise PersistenceError(f"Could not write source retrieval cache: {cache_key}") from exc
        return cache_path


def _validate_discovery_id(discovery_id: str) -> None:
    if DISCOVERY_ID_PATTERN.fullmatch(discovery_id) is None:
        raise UserInputError(
            "Discovery ID must look like discovery_ followed by 16 lowercase "
            "hexadecimal characters."
        )


def _validate_cache_key(cache_key: str) -> None:
    if CACHE_KEY_PATTERN.fullmatch(cache_key) is None:
        raise UserInputError("Source retrieval cache key must be a SHA-256 hex digest.")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)
