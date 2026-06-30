from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from autotok.errors import UserInputError
from autotok.job_models import ArtifactType, JobStatus, StageStatus
from autotok.job_storage import DEFAULT_JOB_DB_FILENAME, JobStore

FIXED_TIME = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
LATER_TIME = datetime(2026, 6, 30, 12, 1, tzinfo=UTC)


def test_job_store_initializes_sqlite_database(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "data")

    store.initialize()

    assert (tmp_path / "data" / DEFAULT_JOB_DB_FILENAME).exists()
    assert store.list_jobs() == ()


def test_job_store_creates_jobs_stages_attempts_and_artifacts(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "data")

    job = store.create_job(
        story_id="story_0123456789abcdef",
        batch_id="batch_local",
        metadata={"seed": 7},
        created_at=FIXED_TIME,
    )
    stage = store.add_stage(job.job_id, "transform", created_at=FIXED_TIME)
    attempt = store.start_attempt(stage.stage_id, started_at=FIXED_TIME)
    finished = store.finish_attempt(
        attempt.attempt_id,
        StageStatus.SUCCEEDED,
        finished_at=LATER_TIME,
    )
    artifact = store.add_artifact(
        job.job_id,
        stage_id=stage.stage_id,
        artifact_type=ArtifactType.SCRIPT,
        artifact_ref="script_0123456789abcdef",
        path="data/scripts/script_0123456789abcdef/record.json",
        metadata={"created": True},
        created_at=LATER_TIME,
    )

    loaded_job = store.load_job(job.job_id)
    stages = store.list_stages(job.job_id)
    attempts = store.list_attempts(stage.stage_id)
    artifacts = store.list_artifacts(job.job_id)

    assert loaded_job.story_id == "story_0123456789abcdef"
    assert loaded_job.status is JobStatus.QUEUED
    assert loaded_job.metadata == {"seed": 7}
    assert stages[0].status is StageStatus.SUCCEEDED
    assert stages[0].attempt_count == 1
    assert attempts == (finished,)
    assert artifact.artifact_type is ArtifactType.SCRIPT
    assert artifacts[0].artifact_ref == "script_0123456789abcdef"
    assert artifacts[0].metadata == {"created": True}


def test_job_store_updates_job_and_stage_failures(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "data")
    job = store.create_job(created_at=FIXED_TIME)
    stage = store.add_stage(job.job_id, "render", created_at=FIXED_TIME)

    running_job = store.update_job_status(job.job_id, JobStatus.RUNNING, updated_at=FIXED_TIME)
    failed_stage = store.update_stage_status(
        stage.stage_id,
        StageStatus.FAILED,
        error_message="render failed",
        updated_at=LATER_TIME,
    )
    failed_job = store.update_job_status(job.job_id, JobStatus.FAILED, updated_at=LATER_TIME)

    assert running_job.status is JobStatus.RUNNING
    assert failed_stage.status is StageStatus.FAILED
    assert failed_stage.error_message == "render failed"
    assert failed_stage.finished_at == "2026-06-30T12:01:00Z"
    assert failed_job.status is JobStatus.FAILED


def test_job_store_lists_jobs_by_status(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "data")
    queued = store.create_job(created_at=FIXED_TIME)
    running = store.create_job(created_at=LATER_TIME)
    store.update_job_status(running.job_id, JobStatus.RUNNING, updated_at=LATER_TIME)

    assert [job.job_id for job in store.list_jobs()] == [queued.job_id, running.job_id]
    assert [job.job_id for job in store.list_jobs(status=JobStatus.RUNNING)] == [running.job_id]


def test_job_store_rejects_missing_records(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "data")

    with pytest.raises(UserInputError, match="Job record"):
        store.load_job("job_missing")

    job = store.create_job(created_at=FIXED_TIME)
    with pytest.raises(UserInputError, match="Stage name"):
        store.add_stage(job.job_id, "   ")
