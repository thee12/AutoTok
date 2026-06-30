"""Source discovery models for Phase 7."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from autotok.normalization import content_sha256, normalize_story_text

DISCOVERY_SCHEMA_VERSION = 1
DISCOVERY_ID_PREFIX = "discovery"
DISCOVERY_ID_HASH_LENGTH = 16


class SourceProvider(StrEnum):
    """Supported automated source providers."""

    REDDIT = "reddit"


@dataclass(frozen=True, slots=True)
class DiscoveredSourcePost:
    """A public source post discovered before canonical story import."""

    provider: SourceProvider
    source_id: str
    source_url: str
    title: str
    body: str
    retrieved_at: str
    content_sha256: str
    source_label: str
    permalink: str | None = None

    @property
    def story_text(self) -> str:
        """Return the text that will be imported as a canonical story."""
        if self.title and self.body:
            return f"{self.title}\n\n{self.body}"
        return self.title or self.body

    def to_dict(self) -> dict[str, object]:
        """Serialize the discovered post to JSON-compatible values."""
        return {
            "provider": self.provider.value,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "title": self.title,
            "body": self.body,
            "retrieved_at": self.retrieved_at,
            "content_sha256": self.content_sha256,
            "source_label": self.source_label,
            "permalink": self.permalink,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> DiscoveredSourcePost:
        """Deserialize and validate a discovered source post."""
        provider_value = _required_str(data, "provider")
        try:
            provider = SourceProvider(provider_value)
        except ValueError as exc:
            raise ValueError(f"Unsupported source provider: {provider_value}") from exc
        return cls(
            provider=provider,
            source_id=_required_str(data, "source_id"),
            source_url=_required_str(data, "source_url"),
            title=_optional_str(data, "title") or "",
            body=_optional_str(data, "body") or "",
            retrieved_at=_required_str(data, "retrieved_at"),
            content_sha256=_required_str(data, "content_sha256"),
            source_label=_required_str(data, "source_label"),
            permalink=_optional_str(data, "permalink"),
        )


@dataclass(frozen=True, slots=True)
class SourceDiscoveryRun:
    """A cached discovery run containing filtered source posts."""

    discovery_id: str
    provider: SourceProvider
    created_at: str
    query: Mapping[str, object]
    posts: tuple[DiscoveredSourcePost, ...]
    request: Mapping[str, object]
    pagination: Mapping[str, object]
    rate_limits: tuple[Mapping[str, object], ...] = ()
    cache_hits: int = 0
    schema_version: int = DISCOVERY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        """Serialize the discovery run to JSON-compatible values."""
        return {
            "schema_version": self.schema_version,
            "discovery_id": self.discovery_id,
            "provider": self.provider.value,
            "created_at": self.created_at,
            "query": dict(self.query),
            "posts": [post.to_dict() for post in self.posts],
            "request": dict(self.request),
            "pagination": dict(self.pagination),
            "rate_limits": [dict(snapshot) for snapshot in self.rate_limits],
            "cache_hits": self.cache_hits,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> SourceDiscoveryRun:
        """Deserialize and validate a discovery run."""
        schema_version = _required_int(data, "schema_version")
        if schema_version != DISCOVERY_SCHEMA_VERSION:
            raise ValueError(f"Unsupported discovery schema_version: {schema_version}")

        provider_value = _required_str(data, "provider")
        try:
            provider = SourceProvider(provider_value)
        except ValueError as exc:
            raise ValueError(f"Unsupported source provider: {provider_value}") from exc

        posts_value = data.get("posts")
        if not isinstance(posts_value, Sequence) or isinstance(posts_value, (str, bytes)):
            raise ValueError("Discovery posts must be a list.")
        posts = tuple(
            DiscoveredSourcePost.from_dict(_required_mapping(item, "post")) for item in posts_value
        )

        return cls(
            schema_version=schema_version,
            discovery_id=_required_str(data, "discovery_id"),
            provider=provider,
            created_at=_required_str(data, "created_at"),
            query=_required_mapping(data.get("query"), "query"),
            posts=posts,
            request=_required_mapping(data.get("request"), "request"),
            pagination=_required_mapping(data.get("pagination"), "pagination"),
            rate_limits=_mapping_tuple(data.get("rate_limits"), "rate_limits"),
            cache_hits=_required_int(data, "cache_hits"),
        )


def build_discovery_id(
    provider: SourceProvider,
    query: Mapping[str, object],
    posts: Sequence[DiscoveredSourcePost],
) -> str:
    """Build a stable discovery ID from query parameters and filtered posts."""
    payload = {
        "provider": provider.value,
        "query": dict(sorted(query.items())),
        "posts": [
            {"source_id": post.source_id, "content_sha256": post.content_sha256} for post in posts
        ],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"{DISCOVERY_ID_PREFIX}_{digest[:DISCOVERY_ID_HASH_LENGTH]}"


def build_discovered_post(
    *,
    provider: SourceProvider,
    source_id: str,
    source_url: str,
    title: str,
    body: str,
    retrieved_at: str,
    source_label: str,
    permalink: str | None = None,
) -> DiscoveredSourcePost | None:
    """Create a discovered post, returning None when it has no usable story text."""
    cleaned_title = title.strip()
    cleaned_body = body.strip()
    story_text = (
        f"{cleaned_title}\n\n{cleaned_body}"
        if cleaned_title and cleaned_body
        else cleaned_title or cleaned_body
    )
    normalized_text = normalize_story_text(story_text)
    if not normalized_text:
        return None
    return DiscoveredSourcePost(
        provider=provider,
        source_id=source_id,
        source_url=source_url,
        title=cleaned_title,
        body=cleaned_body,
        retrieved_at=retrieved_at,
        content_sha256=content_sha256(normalized_text),
        source_label=source_label,
        permalink=permalink,
    )


def _required_str(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string.")
    return value


def _optional_str(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null.")
    return value


def _required_int(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer.")
    return value


def _required_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object.")
    return value


def _mapping_tuple(value: object, name: str) -> tuple[Mapping[str, object], ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be a list.")
    return tuple(_required_mapping(item, name) for item in value)
