"""Local review dashboard models for Phase 10."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

REVIEW_SCHEMA_VERSION = 1


class ReviewPackageStatus(StrEnum):
    """Human review state for a rendered export package."""

    PENDING = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class ReviewEventType(StrEnum):
    """Audit event categories recorded by the local review dashboard."""

    CREATED = "created"
    SCRIPT_EDITED = "script_edited"
    METADATA_EDITED = "metadata_edited"
    APPROVED = "approved"
    REJECTED = "rejected"
    REGENERATION_REQUESTED = "regeneration_requested"


@dataclass(frozen=True, slots=True)
class ReviewScriptSnapshot:
    """Editable script text displayed in the local review UI."""

    hook: str
    body: str
    outro: str

    @property
    def full_text(self) -> str:
        """Return the joined script text."""
        return "\n\n".join(part for part in (self.hook, self.body, self.outro) if part)

    def to_dict(self) -> dict[str, object]:
        """Serialize the editable script snapshot."""
        return {"hook": self.hook, "body": self.body, "outro": self.outro}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReviewScriptSnapshot:
        """Deserialize an editable script snapshot."""
        return cls(
            hook=_required_str(data, "hook"),
            body=_required_str(data, "body"),
            outro=_required_str(data, "outro"),
        )


@dataclass(frozen=True, slots=True)
class ReviewMetadata:
    """Editable metadata for the export package."""

    title: str = ""
    caption: str = ""
    hashtags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Serialize editable metadata."""
        return {"title": self.title, "caption": self.caption, "hashtags": list(self.hashtags)}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReviewMetadata:
        """Deserialize editable metadata."""
        hashtags = data.get("hashtags", [])
        if not isinstance(hashtags, Sequence) or isinstance(hashtags, str):
            raise ValueError("hashtags must be a list of strings.")
        return cls(
            title=_optional_str(data, "title") or "",
            caption=_optional_str(data, "caption") or "",
            hashtags=tuple(_clean_hashtag(str(item)) for item in hashtags if str(item).strip()),
        )


@dataclass(frozen=True, slots=True)
class ReviewAuditEvent:
    """One append-only local review audit event."""

    event_id: str
    event_type: ReviewEventType
    created_at: str
    reviewer: str
    message: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Serialize an audit event."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "created_at": self.created_at,
            "reviewer": self.reviewer,
            "message": self.message,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReviewAuditEvent:
        """Deserialize an audit event."""
        metadata = data.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ValueError("audit metadata must be an object.")
        try:
            event_type = ReviewEventType(_required_str(data, "event_type"))
        except ValueError as exc:
            raise ValueError("review audit event_type is unsupported.") from exc
        return cls(
            event_id=_required_str(data, "event_id"),
            event_type=event_type,
            created_at=_required_str(data, "created_at"),
            reviewer=_required_str(data, "reviewer"),
            message=_required_str(data, "message"),
            metadata=dict(metadata),
        )


@dataclass(frozen=True, slots=True)
class RegenerationRequest:
    """A human request to regenerate a pipeline stage."""

    request_id: str
    stage_name: str
    reason: str
    requested_by: str
    requested_at: str

    def to_dict(self) -> dict[str, object]:
        """Serialize a regeneration request."""
        return {
            "request_id": self.request_id,
            "stage_name": self.stage_name,
            "reason": self.reason,
            "requested_by": self.requested_by,
            "requested_at": self.requested_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> RegenerationRequest:
        """Deserialize a regeneration request."""
        return cls(
            request_id=_required_str(data, "request_id"),
            stage_name=_required_str(data, "stage_name"),
            reason=_required_str(data, "reason"),
            requested_by=_required_str(data, "requested_by"),
            requested_at=_required_str(data, "requested_at"),
        )


@dataclass(frozen=True, slots=True)
class ReviewPackage:
    """Persistent review state for one rendered export package."""

    render_id: str
    story_id: str
    script_id: str
    audio_id: str
    subtitle_id: str
    clip_id: str
    output_path: str
    created_at: str
    updated_at: str
    script: ReviewScriptSnapshot
    metadata: ReviewMetadata = field(default_factory=ReviewMetadata)
    status: ReviewPackageStatus = ReviewPackageStatus.PENDING
    approved_at: str | None = None
    rejected_at: str | None = None
    audit_events: tuple[ReviewAuditEvent, ...] = ()
    regeneration_requests: tuple[RegenerationRequest, ...] = ()
    schema_version: int = REVIEW_SCHEMA_VERSION

    def with_event(self, event: ReviewAuditEvent) -> ReviewPackage:
        """Return a copy with one appended audit event and refreshed timestamp."""
        return replace(
            self,
            updated_at=event.created_at,
            audit_events=(*self.audit_events, event),
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize the review package."""
        return {
            "schema_version": self.schema_version,
            "render_id": self.render_id,
            "story_id": self.story_id,
            "script_id": self.script_id,
            "audio_id": self.audio_id,
            "subtitle_id": self.subtitle_id,
            "clip_id": self.clip_id,
            "output_path": self.output_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status.value,
            "approved_at": self.approved_at,
            "rejected_at": self.rejected_at,
            "script": self.script.to_dict(),
            "metadata": self.metadata.to_dict(),
            "audit_events": [event.to_dict() for event in self.audit_events],
            "regeneration_requests": [request.to_dict() for request in self.regeneration_requests],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ReviewPackage:
        """Deserialize and validate a review package."""
        schema_version = _required_int(data, "schema_version")
        if schema_version != REVIEW_SCHEMA_VERSION:
            raise ValueError(f"Unsupported review schema_version: {schema_version}")
        try:
            status = ReviewPackageStatus(_required_str(data, "status"))
        except ValueError as exc:
            raise ValueError("review status is unsupported.") from exc
        script = data.get("script")
        metadata = data.get("metadata")
        audit_events = data.get("audit_events", [])
        regeneration_requests = data.get("regeneration_requests", [])
        if not isinstance(script, Mapping):
            raise ValueError("script must be an object.")
        if not isinstance(metadata, Mapping):
            raise ValueError("metadata must be an object.")
        if not isinstance(audit_events, Sequence) or isinstance(audit_events, str):
            raise ValueError("audit_events must be a list.")
        if not isinstance(regeneration_requests, Sequence) or isinstance(
            regeneration_requests, str
        ):
            raise ValueError("regeneration_requests must be a list.")
        return cls(
            schema_version=schema_version,
            render_id=_required_str(data, "render_id"),
            story_id=_required_str(data, "story_id"),
            script_id=_required_str(data, "script_id"),
            audio_id=_required_str(data, "audio_id"),
            subtitle_id=_required_str(data, "subtitle_id"),
            clip_id=_required_str(data, "clip_id"),
            output_path=_required_str(data, "output_path"),
            created_at=_required_str(data, "created_at"),
            updated_at=_required_str(data, "updated_at"),
            status=status,
            approved_at=_optional_str(data, "approved_at"),
            rejected_at=_optional_str(data, "rejected_at"),
            script=ReviewScriptSnapshot.from_dict(script),
            metadata=ReviewMetadata.from_dict(metadata),
            audit_events=tuple(_events_from_sequence(audit_events)),
            regeneration_requests=tuple(_requests_from_sequence(regeneration_requests)),
        )


def _events_from_sequence(values: Sequence[object]) -> list[ReviewAuditEvent]:
    events: list[ReviewAuditEvent] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError("Each audit event must be an object.")
        events.append(ReviewAuditEvent.from_dict(value))
    return events


def _requests_from_sequence(values: Sequence[object]) -> list[RegenerationRequest]:
    requests: list[RegenerationRequest] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError("Each regeneration request must be an object.")
        requests.append(RegenerationRequest.from_dict(value))
    return requests


def _clean_hashtag(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    return cleaned if cleaned.startswith("#") else f"#{cleaned}"


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
