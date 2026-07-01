"""Publishing domain models for Phase 11 official integrations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

PUBLISHING_SCHEMA_VERSION = 1


class PublishingProvider(StrEnum):
    """Official publishing providers supported by AutoTok."""

    TIKTOK = "tiktok"


class PublishSourceType(StrEnum):
    """TikTok Direct Post source modes."""

    FILE_UPLOAD = "FILE_UPLOAD"
    PULL_FROM_URL = "PULL_FROM_URL"


class PublicationStatus(StrEnum):
    """Local publication lifecycle status."""

    DRY_RUN_READY = "dry_run_ready"
    BLOCKED = "blocked"
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"


class PublicationEventType(StrEnum):
    """Audit event categories for publication records."""

    DRY_RUN = "dry_run"
    SUBMITTED = "submitted"
    STATUS_FETCHED = "status_fetched"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TikTokCapability:
    """Verified official TikTok Content Posting API capability snapshot."""

    provider: PublishingProvider = PublishingProvider.TIKTOK
    direct_post_endpoint: str = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    status_endpoint: str = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
    oauth_token_endpoint: str = "https://open.tiktokapis.com/v2/oauth/token/"
    oauth_revoke_endpoint: str = "https://open.tiktokapis.com/v2/oauth/revoke/"
    required_scope: str = "video.publish"
    supports_direct_post: bool = True
    supports_scheduling: bool = False
    verified_at: str = "2026-07-01"
    documentation_urls: tuple[str, ...] = (
        "https://developers.tiktok.com/doc/content-posting-api-get-started/",
        "https://developers.tiktok.com/doc/content-posting-api-reference-direct-post/",
        "https://developers.tiktok.com/doc/content-posting-api-reference-get-video-status/",
        "https://developers.tiktok.com/doc/oauth-user-access-token-management/",
    )

    def to_dict(self) -> dict[str, object]:
        """Serialize capability verification."""
        return {
            "provider": self.provider.value,
            "direct_post_endpoint": self.direct_post_endpoint,
            "status_endpoint": self.status_endpoint,
            "oauth_token_endpoint": self.oauth_token_endpoint,
            "oauth_revoke_endpoint": self.oauth_revoke_endpoint,
            "required_scope": self.required_scope,
            "supports_direct_post": self.supports_direct_post,
            "supports_scheduling": self.supports_scheduling,
            "verified_at": self.verified_at,
            "documentation_urls": list(self.documentation_urls),
        }


@dataclass(frozen=True, slots=True)
class TikTokDirectPostOptions:
    """Official TikTok Direct Post request options."""

    privacy_level: str = "SELF_ONLY"
    disable_duet: bool = False
    disable_comment: bool = False
    disable_stitch: bool = False
    cover_timestamp_ms: int = 0
    source_type: PublishSourceType = PublishSourceType.FILE_UPLOAD
    video_url: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize request options."""
        return {
            "privacy_level": self.privacy_level,
            "disable_duet": self.disable_duet,
            "disable_comment": self.disable_comment,
            "disable_stitch": self.disable_stitch,
            "cover_timestamp_ms": self.cover_timestamp_ms,
            "source_type": self.source_type.value,
            "video_url": self.video_url,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> TikTokDirectPostOptions:
        """Deserialize request options."""
        try:
            source_type = PublishSourceType(_required_str(data, "source_type"))
        except ValueError as exc:
            raise ValueError("source_type is unsupported.") from exc
        video_url = data.get("video_url")
        if video_url is not None and not isinstance(video_url, str):
            raise ValueError("video_url must be a string or null.")
        return cls(
            privacy_level=_required_str(data, "privacy_level"),
            disable_duet=_required_bool(data, "disable_duet"),
            disable_comment=_required_bool(data, "disable_comment"),
            disable_stitch=_required_bool(data, "disable_stitch"),
            cover_timestamp_ms=_required_int(data, "cover_timestamp_ms"),
            source_type=source_type,
            video_url=video_url or None,
        )


@dataclass(frozen=True, slots=True)
class PublicationAuditEvent:
    """One append-only publication audit event."""

    event_id: str
    event_type: PublicationEventType
    created_at: str
    message: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Serialize an audit event."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "created_at": self.created_at,
            "message": self.message,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> PublicationAuditEvent:
        """Deserialize an audit event."""
        metadata = data.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ValueError("metadata must be an object.")
        try:
            event_type = PublicationEventType(_required_str(data, "event_type"))
        except ValueError as exc:
            raise ValueError("publication audit event_type is unsupported.") from exc
        return cls(
            event_id=_required_str(data, "event_id"),
            event_type=event_type,
            created_at=_required_str(data, "created_at"),
            message=_required_str(data, "message"),
            metadata=dict(metadata),
        )


@dataclass(frozen=True, slots=True)
class PublicationRecord:
    """Persistent local publication state for one render/provider pair."""

    publication_id: str
    render_id: str
    provider: PublishingProvider
    status: PublicationStatus
    created_at: str
    updated_at: str
    approved_review_at: str
    render_output_path: str
    request_options: TikTokDirectPostOptions
    capability: TikTokCapability = field(default_factory=TikTokCapability)
    publish_id: str | None = None
    last_status_payload: Mapping[str, Any] | None = None
    audit_events: tuple[PublicationAuditEvent, ...] = ()
    schema_version: int = PUBLISHING_SCHEMA_VERSION

    def with_event(
        self,
        event: PublicationAuditEvent,
        *,
        status: PublicationStatus | None = None,
        publish_id: str | None = None,
        last_status_payload: Mapping[str, Any] | None = None,
    ) -> PublicationRecord:
        """Return a copy with an appended event and refreshed status fields."""
        return replace(
            self,
            updated_at=event.created_at,
            status=self.status if status is None else status,
            publish_id=self.publish_id if publish_id is None else publish_id,
            last_status_payload=(
                self.last_status_payload if last_status_payload is None else last_status_payload
            ),
            audit_events=(*self.audit_events, event),
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize the publication record."""
        return {
            "schema_version": self.schema_version,
            "publication_id": self.publication_id,
            "render_id": self.render_id,
            "provider": self.provider.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "approved_review_at": self.approved_review_at,
            "render_output_path": self.render_output_path,
            "request_options": self.request_options.to_dict(),
            "capability": self.capability.to_dict(),
            "publish_id": self.publish_id,
            "last_status_payload": (
                None if self.last_status_payload is None else dict(self.last_status_payload)
            ),
            "audit_events": [event.to_dict() for event in self.audit_events],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> PublicationRecord:
        """Deserialize and validate a publication record."""
        schema_version = _required_int(data, "schema_version")
        if schema_version != PUBLISHING_SCHEMA_VERSION:
            raise ValueError(f"Unsupported publishing schema_version: {schema_version}")
        request_options = data.get("request_options")
        events = data.get("audit_events", [])
        last_status_payload = data.get("last_status_payload")
        if not isinstance(request_options, Mapping):
            raise ValueError("request_options must be an object.")
        if not isinstance(events, Sequence) or isinstance(events, str):
            raise ValueError("audit_events must be a list.")
        if last_status_payload is not None and not isinstance(last_status_payload, Mapping):
            raise ValueError("last_status_payload must be an object or null.")
        try:
            provider = PublishingProvider(_required_str(data, "provider"))
            status = PublicationStatus(_required_str(data, "status"))
        except ValueError as exc:
            raise ValueError("publication provider or status is unsupported.") from exc
        return cls(
            schema_version=schema_version,
            publication_id=_required_str(data, "publication_id"),
            render_id=_required_str(data, "render_id"),
            provider=provider,
            status=status,
            created_at=_required_str(data, "created_at"),
            updated_at=_required_str(data, "updated_at"),
            approved_review_at=_required_str(data, "approved_review_at"),
            render_output_path=_required_str(data, "render_output_path"),
            request_options=TikTokDirectPostOptions.from_dict(request_options),
            publish_id=_optional_str(data, "publish_id"),
            last_status_payload=(
                None if last_status_payload is None else dict(last_status_payload)
            ),
            audit_events=tuple(_events_from_sequence(events)),
        )


@dataclass(frozen=True, slots=True)
class PublicationResult:
    """Result returned by publication workflows."""

    record: PublicationRecord
    dry_run: bool
    duplicate_prevented: bool = False
    provider_response: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize a publication result."""
        return {
            "dry_run": self.dry_run,
            "duplicate_prevented": self.duplicate_prevented,
            "publication": self.record.to_dict(),
            "provider_response": (
                None if self.provider_response is None else dict(self.provider_response)
            ),
        }


def _events_from_sequence(values: Sequence[object]) -> list[PublicationAuditEvent]:
    events: list[PublicationAuditEvent] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError("Each audit event must be an object.")
        events.append(PublicationAuditEvent.from_dict(value))
    return events


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
    return value or None


def _required_int(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer.")
    return value


def _required_bool(data: Mapping[str, object], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean.")
    return value
