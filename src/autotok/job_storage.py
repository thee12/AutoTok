"""SQLite persistence foundation for Phase 9 jobs."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from autotok.errors import PersistenceError, UserInputError
from autotok.job_models import (
    JOB_SCHEMA_VERSION,
    ArtifactType,
    AttemptRecord,
    JobArtifactRecord,
    JobRecord,
    JobStatus,
    StageRecord,
    StageStatus,
)

DEFAULT_JOB_DB_FILENAME = "jobs.sqlite3"


class JobStore:
    """SQLite-backed persistent job store for local orchestration."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.db_path = data_dir / DEFAULT_JOB_DB_FILENAME

    def initialize(self) -> None:
        """Create or validate the Phase 9 job database schema."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                _initialize_schema(connection)
        except sqlite3.Error as exc:
            raise PersistenceError("Could not initialize job database.") from exc

    def create_job(
        self,
        *,
        story_id: str | None = None,
        batch_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> JobRecord:
        """Create a queued job record."""
        self.initialize()
        timestamp = _utc_timestamp(created_at)
        record = JobRecord(
            job_id=_new_id("job"),
            status=JobStatus.QUEUED,
            created_at=timestamp,
            updated_at=timestamp,
            story_id=story_id,
            batch_id=batch_id,
            metadata={} if metadata is None else dict(metadata),
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO jobs (
                        job_id, status, story_id, batch_id, metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.job_id,
                        record.status.value,
                        record.story_id,
                        record.batch_id,
                        _json(record.metadata),
                        record.created_at,
                        record.updated_at,
                    ),
                )
        except sqlite3.Error as exc:
            raise PersistenceError("Could not create job record.") from exc
        return record

    def load_job(self, job_id: str) -> JobRecord:
        """Load a job by ID."""
        self.initialize()
        row = self._fetch_one("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        if row is None:
            raise UserInputError(f"Job record was not found: {job_id}")
        return _job_from_row(row)

    def list_jobs(self, *, status: JobStatus | None = None) -> tuple[JobRecord, ...]:
        """List jobs in deterministic creation order."""
        self.initialize()
        if status is None:
            rows = self._fetch_all("SELECT * FROM jobs ORDER BY rowid", ())
        else:
            rows = self._fetch_all(
                "SELECT * FROM jobs WHERE status = ? ORDER BY rowid",
                (status.value,),
            )
        return tuple(_job_from_row(row) for row in rows)

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        updated_at: datetime | None = None,
    ) -> JobRecord:
        """Update and return a job status."""
        self.load_job(job_id)
        timestamp = _utc_timestamp(updated_at)
        try:
            with self._connect() as connection:
                connection.execute(
                    "UPDATE jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                    (status.value, timestamp, job_id),
                )
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not update job status: {job_id}") from exc
        return self.load_job(job_id)

    def add_stage(
        self,
        job_id: str,
        name: str,
        *,
        created_at: datetime | None = None,
    ) -> StageRecord:
        """Add a pending stage to a job."""
        self.load_job(job_id)
        cleaned_name = name.strip()
        if not cleaned_name:
            raise UserInputError("Stage name must not be empty.")
        timestamp = _utc_timestamp(created_at)
        record = StageRecord(
            stage_id=_new_id("stage"),
            job_id=job_id,
            name=cleaned_name,
            status=StageStatus.PENDING,
            created_at=timestamp,
            updated_at=timestamp,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO stages (
                        stage_id, job_id, name, status, attempt_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.stage_id,
                        record.job_id,
                        record.name,
                        record.status.value,
                        record.attempt_count,
                        record.created_at,
                        record.updated_at,
                    ),
                )
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not add stage to job: {job_id}") from exc
        return record

    def get_stage_by_name(self, job_id: str, name: str) -> StageRecord | None:
        """Return a job stage by name, if it exists."""
        self.load_job(job_id)
        cleaned_name = name.strip()
        if not cleaned_name:
            raise UserInputError("Stage name must not be empty.")
        row = self._fetch_one(
            "SELECT * FROM stages WHERE job_id = ? AND name = ? ORDER BY created_at LIMIT 1",
            (job_id, cleaned_name),
        )
        if row is None:
            return None
        return _stage_from_row(row)

    def ensure_stage(self, job_id: str, name: str) -> StageRecord:
        """Load a stage by name or create it when missing."""
        stage = self.get_stage_by_name(job_id, name)
        if stage is not None:
            return stage
        return self.add_stage(job_id, name)

    def list_stages(self, job_id: str) -> tuple[StageRecord, ...]:
        """List stages for a job in creation order."""
        self.load_job(job_id)
        rows = self._fetch_all(
            "SELECT * FROM stages WHERE job_id = ? ORDER BY rowid",
            (job_id,),
        )
        return tuple(_stage_from_row(row) for row in rows)

    def update_stage_status(
        self,
        stage_id: str,
        status: StageStatus,
        *,
        error_message: str | None = None,
        updated_at: datetime | None = None,
    ) -> StageRecord:
        """Update and return a stage status."""
        stage = self.load_stage(stage_id)
        timestamp = _utc_timestamp(updated_at)
        started_at = stage.started_at or (timestamp if status is StageStatus.RUNNING else None)
        finished_at = timestamp if status in _TERMINAL_STAGE_STATUSES else stage.finished_at
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    UPDATE stages
                    SET status = ?, updated_at = ?, started_at = ?,
                        finished_at = ?, error_message = ?
                    WHERE stage_id = ?
                    """,
                    (status.value, timestamp, started_at, finished_at, error_message, stage_id),
                )
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not update stage status: {stage_id}") from exc
        return self.load_stage(stage_id)

    def load_stage(self, stage_id: str) -> StageRecord:
        """Load a stage by ID."""
        self.initialize()
        row = self._fetch_one("SELECT * FROM stages WHERE stage_id = ?", (stage_id,))
        if row is None:
            raise UserInputError(f"Stage record was not found: {stage_id}")
        return _stage_from_row(row)

    def start_attempt(
        self,
        stage_id: str,
        *,
        started_at: datetime | None = None,
    ) -> AttemptRecord:
        """Start a stage attempt and mark the stage running."""
        stage = self.load_stage(stage_id)
        timestamp = _utc_timestamp(started_at)
        attempt_number = stage.attempt_count + 1
        record = AttemptRecord(
            attempt_id=_new_id("attempt"),
            stage_id=stage_id,
            attempt_number=attempt_number,
            status=StageStatus.RUNNING,
            started_at=timestamp,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO attempts (
                        attempt_id, stage_id, attempt_number, status, started_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        record.attempt_id,
                        record.stage_id,
                        record.attempt_number,
                        record.status.value,
                        record.started_at,
                    ),
                )
                connection.execute(
                    """
                    UPDATE stages
                    SET status = ?, attempt_count = ?, started_at = COALESCE(started_at, ?),
                        updated_at = ?
                    WHERE stage_id = ?
                    """,
                    (StageStatus.RUNNING.value, attempt_number, timestamp, timestamp, stage_id),
                )
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not start attempt for stage: {stage_id}") from exc
        return record

    def finish_attempt(
        self,
        attempt_id: str,
        status: StageStatus,
        *,
        error_message: str | None = None,
        finished_at: datetime | None = None,
    ) -> AttemptRecord:
        """Finish an attempt and mirror its terminal status onto the stage."""
        if status not in _TERMINAL_STAGE_STATUSES:
            raise UserInputError("Attempt finish status must be terminal.")
        attempt = self.load_attempt(attempt_id)
        timestamp = _utc_timestamp(finished_at)
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    UPDATE attempts
                    SET status = ?, finished_at = ?, error_message = ?
                    WHERE attempt_id = ?
                    """,
                    (status.value, timestamp, error_message, attempt_id),
                )
                connection.execute(
                    """
                    UPDATE stages
                    SET status = ?, updated_at = ?, finished_at = ?, error_message = ?
                    WHERE stage_id = ?
                    """,
                    (status.value, timestamp, timestamp, error_message, attempt.stage_id),
                )
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not finish attempt: {attempt_id}") from exc
        return self.load_attempt(attempt_id)

    def load_attempt(self, attempt_id: str) -> AttemptRecord:
        """Load an attempt by ID."""
        self.initialize()
        row = self._fetch_one("SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,))
        if row is None:
            raise UserInputError(f"Attempt record was not found: {attempt_id}")
        return _attempt_from_row(row)

    def list_attempts(self, stage_id: str) -> tuple[AttemptRecord, ...]:
        """List attempts for a stage by attempt number."""
        self.load_stage(stage_id)
        rows = self._fetch_all(
            "SELECT * FROM attempts WHERE stage_id = ? ORDER BY attempt_number",
            (stage_id,),
        )
        return tuple(_attempt_from_row(row) for row in rows)

    def add_artifact(
        self,
        job_id: str,
        *,
        artifact_type: ArtifactType,
        artifact_ref: str,
        stage_id: str | None = None,
        path: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> JobArtifactRecord:
        """Attach an artifact reference to a job or stage."""
        self.load_job(job_id)
        if stage_id is not None:
            self.load_stage(stage_id)
        cleaned_ref = artifact_ref.strip()
        if not cleaned_ref:
            raise UserInputError("Artifact reference must not be empty.")
        timestamp = _utc_timestamp(created_at)
        record = JobArtifactRecord(
            job_artifact_id=_new_id("jobartifact"),
            job_id=job_id,
            stage_id=stage_id,
            artifact_type=artifact_type,
            artifact_ref=cleaned_ref,
            path=path,
            metadata={} if metadata is None else dict(metadata),
            created_at=timestamp,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO artifacts (
                        job_artifact_id, job_id, stage_id, artifact_type, artifact_ref,
                        path, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.job_artifact_id,
                        record.job_id,
                        record.stage_id,
                        record.artifact_type.value,
                        record.artifact_ref,
                        record.path,
                        _json(record.metadata),
                        record.created_at,
                    ),
                )
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not add artifact to job: {job_id}") from exc
        return record

    def add_artifact_once(
        self,
        job_id: str,
        *,
        artifact_type: ArtifactType,
        artifact_ref: str,
        stage_id: str | None = None,
        path: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> JobArtifactRecord:
        """Attach an artifact unless the same reference is already tracked."""
        cleaned_ref = artifact_ref.strip()
        if not cleaned_ref:
            raise UserInputError("Artifact reference must not be empty.")
        for artifact in self.list_artifacts(job_id):
            if (
                artifact.stage_id == stage_id
                and artifact.artifact_type is artifact_type
                and artifact.artifact_ref == cleaned_ref
                and artifact.path == path
            ):
                return artifact
        return self.add_artifact(
            job_id,
            artifact_type=artifact_type,
            artifact_ref=cleaned_ref,
            stage_id=stage_id,
            path=path,
            metadata=metadata,
            created_at=created_at,
        )

    def list_artifacts(self, job_id: str) -> tuple[JobArtifactRecord, ...]:
        """List artifacts for a job in creation order."""
        self.load_job(job_id)
        rows = self._fetch_all(
            "SELECT * FROM artifacts WHERE job_id = ? ORDER BY rowid",
            (job_id,),
        )
        return tuple(_artifact_from_row(row) for row in rows)

    def delete_job(self, job_id: str) -> None:
        """Delete one job record and cascading stage, attempt, and artifact records."""
        self.load_job(job_id)
        try:
            with self._connect() as connection:
                connection.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        except sqlite3.Error as exc:
            raise PersistenceError(f"Could not delete job record: {job_id}") from exc

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _fetch_one(self, query: str, params: tuple[object, ...]) -> sqlite3.Row | None:
        try:
            with closing(self._connect()) as connection:
                return cast(sqlite3.Row | None, connection.execute(query, params).fetchone())
        except sqlite3.Error as exc:
            raise PersistenceError("Could not read job database.") from exc

    def _fetch_all(self, query: str, params: tuple[object, ...]) -> tuple[sqlite3.Row, ...]:
        try:
            with closing(self._connect()) as connection:
                return tuple(connection.execute(query, params).fetchall())
        except sqlite3.Error as exc:
            raise PersistenceError("Could not read job database.") from exc


_TERMINAL_STAGE_STATUSES = {
    StageStatus.SUCCEEDED,
    StageStatus.FAILED,
    StageStatus.SKIPPED,
}


def _initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_info (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            story_id TEXT,
            batch_id TEXT,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stages (
            stage_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            attempt_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            error_message TEXT
        );
        CREATE TABLE IF NOT EXISTS attempts (
            attempt_id TEXT PRIMARY KEY,
            stage_id TEXT NOT NULL REFERENCES stages(stage_id) ON DELETE CASCADE,
            attempt_number INTEGER NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            error_message TEXT,
            UNIQUE(stage_id, attempt_number)
        );
        CREATE TABLE IF NOT EXISTS artifacts (
            job_artifact_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
            stage_id TEXT REFERENCES stages(stage_id) ON DELETE SET NULL,
            artifact_type TEXT NOT NULL,
            artifact_ref TEXT NOT NULL,
            path TEXT,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    existing = connection.execute(
        "SELECT value FROM schema_info WHERE key = 'job_schema_version'"
    ).fetchone()
    if existing is None:
        connection.execute(
            "INSERT INTO schema_info (key, value) VALUES ('job_schema_version', ?)",
            (str(JOB_SCHEMA_VERSION),),
        )
    elif existing[0] != str(JOB_SCHEMA_VERSION):
        raise PersistenceError(
            f"Unsupported job database schema version: {existing[0]} expected {JOB_SCHEMA_VERSION}."
        )


def _job_from_row(row: sqlite3.Row) -> JobRecord:
    return JobRecord(
        job_id=str(row["job_id"]),
        status=JobStatus(str(row["status"])),
        story_id=_optional_str(row["story_id"]),
        batch_id=_optional_str(row["batch_id"]),
        metadata=_loads_object(str(row["metadata_json"])),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _stage_from_row(row: sqlite3.Row) -> StageRecord:
    return StageRecord(
        stage_id=str(row["stage_id"]),
        job_id=str(row["job_id"]),
        name=str(row["name"]),
        status=StageStatus(str(row["status"])),
        attempt_count=int(row["attempt_count"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        started_at=_optional_str(row["started_at"]),
        finished_at=_optional_str(row["finished_at"]),
        error_message=_optional_str(row["error_message"]),
    )


def _attempt_from_row(row: sqlite3.Row) -> AttemptRecord:
    return AttemptRecord(
        attempt_id=str(row["attempt_id"]),
        stage_id=str(row["stage_id"]),
        attempt_number=int(row["attempt_number"]),
        status=StageStatus(str(row["status"])),
        started_at=str(row["started_at"]),
        finished_at=_optional_str(row["finished_at"]),
        error_message=_optional_str(row["error_message"]),
    )


def _artifact_from_row(row: sqlite3.Row) -> JobArtifactRecord:
    return JobArtifactRecord(
        job_artifact_id=str(row["job_artifact_id"]),
        job_id=str(row["job_id"]),
        stage_id=_optional_str(row["stage_id"]),
        artifact_type=ArtifactType(str(row["artifact_type"])),
        artifact_ref=str(row["artifact_ref"]),
        path=_optional_str(row["path"]),
        metadata=_loads_object(str(row["metadata_json"])),
        created_at=str(row["created_at"]),
    )


def _json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), sort_keys=True)


def _loads_object(payload: str) -> dict[str, Any]:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise PersistenceError("Stored metadata JSON must be an object.")
    return data


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _utc_timestamp(value: datetime | None) -> str:
    timestamp = datetime.now(UTC) if value is None else value.astimezone(UTC)
    return timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")
