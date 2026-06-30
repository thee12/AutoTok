"""Persistent job and orchestration models for Phase 9."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

JOB_SCHEMA_VERSION = 1


class JobStatus(StrEnum):
    """Persistent job lifecycle states."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class StageStatus(StrEnum):
    """Persistent pipeline stage lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class ArtifactType(StrEnum):
    """Known artifact categories tracked by Phase 9 jobs."""

    SOURCE = "source"
    CONTENT_GATE = "content_gate"
    SCRIPT = "script"
    AUDIO = "audio"
    SUBTITLE = "subtitle"
    MEDIA = "media"
    CLIP = "clip"
    RENDER = "render"
    MANIFEST = "manifest"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class JobRecord:
    """A persisted orchestration job."""

    job_id: str
    status: JobStatus
    created_at: str
    updated_at: str
    story_id: str | None = None
    batch_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Serialize a job record."""
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "story_id": self.story_id,
            "batch_id": self.batch_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class StageRecord:
    """A persisted stage within a job."""

    stage_id: str
    job_id: str
    name: str
    status: StageStatus
    created_at: str
    updated_at: str
    attempt_count: int = 0
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize a stage record."""
        return {
            "stage_id": self.stage_id,
            "job_id": self.job_id,
            "name": self.name,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "attempt_count": self.attempt_count,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error_message": self.error_message,
        }


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """A persisted execution attempt for a stage."""

    attempt_id: str
    stage_id: str
    attempt_number: int
    status: StageStatus
    started_at: str
    finished_at: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize an attempt record."""
        return {
            "attempt_id": self.attempt_id,
            "stage_id": self.stage_id,
            "attempt_number": self.attempt_number,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error_message": self.error_message,
        }


@dataclass(frozen=True, slots=True)
class JobArtifactRecord:
    """A persisted artifact associated with a job or stage."""

    job_artifact_id: str
    job_id: str
    artifact_type: ArtifactType
    artifact_ref: str
    created_at: str
    stage_id: str | None = None
    path: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Serialize an artifact record."""
        return {
            "job_artifact_id": self.job_artifact_id,
            "job_id": self.job_id,
            "stage_id": self.stage_id,
            "artifact_type": self.artifact_type.value,
            "artifact_ref": self.artifact_ref,
            "path": self.path,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
        }
