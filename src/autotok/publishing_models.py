"""Publishing domain models for local manual-upload handoff packages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

PUBLISHING_SCHEMA_VERSION = 2


class PublishingProvider(StrEnum):
    """Manual publishing targets supported by AutoTok."""

    TIKTOK = "tiktok"


class PublicationStatus(StrEnum):
    """Local manual-upload lifecycle status."""

    EXPORT_READY = "export_ready"
    BLOCKED = "blocked"
    MANUALLY_PUBLISHED = "manually_published"
    FAILED = "failed"


class PublicationEventType(StrEnum):
    """Audit event categories for manual publication records."""

    EXPORT_PREPARED = "export_prepared"
    BLOCKED = "blocked"
    MANUAL_STATUS_RECORDED = "manual_status_recorded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TikTokManualUploadOptions:
    """Operator-facing TikTok upload settings to include in the handoff package."""

    privacy_level: str = "private_or_unlisted_until_reviewed"
    disable_duet: bool = False
    disable_comment: bool = False
    disable_stitch: bool = False
    cover_timestamp_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        """Serialize manual upload options."""
        return {
            "privacy_level": self.privacy_level,
            "disable_duet": self.disable_duet,
            "disable_comment": self.disable_comment,
            "disable_stitch": self.disable_stitch,
            "cover_timestamp_ms": self.cover_timestamp_ms,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> TikTokManualUploadOptions:
        """Deserialize manual upload options."""
        return cls(
            privacy_level=_required_str(data, "privacy_level"),
            disable_duet=_required_bool(data, "disable_duet"),
            disable_comment=_required_bool(data, "disable_comment"),
            disable_stitch=_required_bool(data, "disable_stitch"),
            cover_timestamp_ms=_required_int(data, "cover_timestamp_ms"),
        )


@dataclass(frozen=True, slots=True)
class ManualUploadPackage:
    """Files prepared for the operator to upload manually."""

    package_dir: str
    video_path: str
    caption_path: str
    metadata_path: str
    instructions_path: str
    title: str
    caption: str
    hashtags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Serialize a manual upload package."""
        return {
            "package_dir": self.package_dir,
            "video_path": self.video_path,
            "caption_path": self.caption_path,
            "metadata_path": self.metadata_path,
            "instructions_path": self.instructions_path,
            "title": self.title,
            "caption": self.caption,
            "hashtags": list(self.hashtags),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ManualUploadPackage:
        """Deserialize a manual upload package."""
        hashtags = data.get("hashtags", [])
        if not isinstance(hashtags, Sequence) or isinstance(hashtags, str):
            raise ValueError("hashtags must be a list of strings.")
        return cls(
            package_dir=_required_str(data, "package_dir"),
            video_path=_required_str(data, "video_path"),
            caption_path=_required_str(data, "caption_path"),
            metadata_path=_required_str(data, "metadata_path"),
            instructions_path=_required_str(data, "instructions_path"),
            title=_required_str(data, "title"),
            caption=_required_str(data, "caption"),
            hashtags=tuple(str(item) for item in hashtags if str(item).strip()),
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
    """Persistent local manual-upload state for one render/provider pair."""

    publication_id: str
    render_id: str
    provider: PublishingProvider
    status: PublicationStatus
    created_at: str
    updated_at: str
    approved_review_at: str
    render_output_path: str
    manual_options: TikTokManualUploadOptions
    upload_package: ManualUploadPackage | None = None
    manual_publish_url: str | None = None
    audit_events: tuple[PublicationAuditEvent, ...] = ()
    schema_version: int = PUBLISHING_SCHEMA_VERSION

    def with_event(
        self,
        event: PublicationAuditEvent,
        *,
        status: PublicationStatus | None = None,
        upload_package: ManualUploadPackage | None = None,
        manual_publish_url: str | None = None,
    ) -> PublicationRecord:
        """Return a copy with an appended event and refreshed status fields."""
        return replace(
            self,
            updated_at=event.created_at,
            status=self.status if status is None else status,
            upload_package=self.upload_package if upload_package is None else upload_package,
            manual_publish_url=(
                self.manual_publish_url if manual_publish_url is None else manual_publish_url
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
            "manual_options": self.manual_options.to_dict(),
            "upload_package": None
            if self.upload_package is None
            else self.upload_package.to_dict(),
            "manual_publish_url": self.manual_publish_url,
            "audit_events": [event.to_dict() for event in self.audit_events],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> PublicationRecord:
        """Deserialize and validate a publication record."""
        schema_version = _required_int(data, "schema_version")
        if schema_version != PUBLISHING_SCHEMA_VERSION:
            raise ValueError(f"Unsupported publishing schema_version: {schema_version}")
        manual_options = data.get("manual_options")
        upload_package = data.get("upload_package")
        events = data.get("audit_events", [])
        if not isinstance(manual_options, Mapping):
            raise ValueError("manual_options must be an object.")
        if upload_package is not None and not isinstance(upload_package, Mapping):
            raise ValueError("upload_package must be an object or null.")
        if not isinstance(events, Sequence) or isinstance(events, str):
            raise ValueError("audit_events must be a list.")
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
            manual_options=TikTokManualUploadOptions.from_dict(manual_options),
            upload_package=(
                None if upload_package is None else ManualUploadPackage.from_dict(upload_package)
            ),
            manual_publish_url=_optional_str(data, "manual_publish_url"),
            audit_events=tuple(_events_from_sequence(events)),
        )


@dataclass(frozen=True, slots=True)
class PublicationResult:
    """Result returned by manual publication workflows."""

    record: PublicationRecord
    package: ManualUploadPackage
    duplicate_prevented: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize a publication result."""
        return {
            "manual_upload": True,
            "duplicate_prevented": self.duplicate_prevented,
            "publication": self.record.to_dict(),
            "package": self.package.to_dict(),
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
