from __future__ import annotations

import json
from pathlib import Path

from autotok.config import AppConfig
from autotok.errors import UserInputError
from autotok.job_models import ArtifactType, JobStatus, StageStatus
from autotok.job_orchestration import (
    JobRunContext,
    JobRunOptions,
    JobStageDefinition,
    StageExecutionResult,
    cleanup_jobs,
    run_job,
)
from autotok.job_storage import JobStore


def test_run_job_resumes_without_rerunning_successful_stage(tmp_path: Path) -> None:
    config = AppConfig(data_dir=tmp_path / "data")
    store = JobStore(config.data_dir)
    job = store.create_job(story_id="story_demo")
    calls: list[str] = []

    def first_stage(context: JobRunContext) -> StageExecutionResult:
        calls.append(context.stage.name)
        return StageExecutionResult(ArtifactType.OTHER, "first_artifact", path="first.json")

    def second_stage(context: JobRunContext) -> StageExecutionResult:
        calls.append(context.stage.name)
        return StageExecutionResult(ArtifactType.OTHER, "second_artifact", path="second.json")

    definitions = (
        JobStageDefinition("first", first_stage),
        JobStageDefinition("second", second_stage),
    )

    partial = run_job(
        config=config,
        store=store,
        job_id=job.job_id,
        stage_definitions=definitions,
        options=JobRunOptions(stop_after="first"),
    )
    resumed = run_job(
        config=config,
        store=store,
        job_id=job.job_id,
        stage_definitions=definitions,
    )

    assert partial.job.status is JobStatus.QUEUED
    assert partial.completed is False
    assert partial.stopped_after == "first"
    assert resumed.job.status is JobStatus.SUCCEEDED
    assert resumed.completed is True
    assert calls == ["first", "second"]
    assert [stage.status for stage in resumed.stages] == [
        StageStatus.SUCCEEDED,
        StageStatus.SUCCEEDED,
    ]
    assert [stage.attempt_count for stage in resumed.stages] == [1, 1]
    artifact_refs = [artifact.artifact_ref for artifact in resumed.artifacts]
    assert artifact_refs.count("first_artifact") == 1
    assert artifact_refs.count("second_artifact") == 1
    manifest_payload = json.loads(resumed.manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["job"]["status"] == JobStatus.SUCCEEDED.value


def test_run_job_recovers_running_attempt_before_resume(tmp_path: Path) -> None:
    config = AppConfig(data_dir=tmp_path / "data")
    store = JobStore(config.data_dir)
    job = store.create_job(story_id="story_demo")
    stage = store.add_stage(job.job_id, "recoverable")
    store.start_attempt(stage.stage_id)

    def recoverable(context: JobRunContext) -> StageExecutionResult:
        return StageExecutionResult(ArtifactType.OTHER, "recovered", path="recovered.json")

    summary = run_job(
        config=config,
        store=store,
        job_id=job.job_id,
        stage_definitions=(JobStageDefinition("recoverable", recoverable),),
    )

    attempts = store.list_attempts(stage.stage_id)
    assert summary.job.status is JobStatus.SUCCEEDED
    assert [attempt.status for attempt in attempts] == [StageStatus.FAILED, StageStatus.SUCCEEDED]
    assert attempts[0].error_message == "Recovered incomplete running attempt before resume."


def test_run_job_marks_job_failed_after_max_attempts(tmp_path: Path) -> None:
    config = AppConfig(data_dir=tmp_path / "data")
    store = JobStore(config.data_dir)
    job = store.create_job(story_id="story_demo")

    def failing_stage(context: JobRunContext) -> StageExecutionResult:
        raise UserInputError("temporary local failure")

    summary = run_job(
        config=config,
        store=store,
        job_id=job.job_id,
        stage_definitions=(JobStageDefinition("failing", failing_stage),),
        options=JobRunOptions(max_attempts=2),
    )

    stage = summary.stages[0]
    attempts = store.list_attempts(stage.stage_id)
    assert summary.job.status is JobStatus.FAILED
    assert summary.completed is False
    assert stage.status is StageStatus.FAILED
    assert stage.attempt_count == 2
    assert [attempt.error_message for attempt in attempts] == [
        "temporary local failure",
        "temporary local failure",
    ]


def test_cleanup_jobs_dry_run_and_apply(tmp_path: Path) -> None:
    config = AppConfig(data_dir=tmp_path / "data")
    store = JobStore(config.data_dir)
    job = store.create_job(story_id="story_demo")
    store.update_job_status(job.job_id, JobStatus.SUCCEEDED)

    dry_run = cleanup_jobs(
        store=store,
        data_dir=config.data_dir,
        status=JobStatus.SUCCEEDED,
        older_than_days=0,
        apply=False,
    )
    applied = cleanup_jobs(
        store=store,
        data_dir=config.data_dir,
        status=JobStatus.SUCCEEDED,
        older_than_days=0,
        apply=True,
    )

    assert dry_run.matched_job_ids == (job.job_id,)
    assert dry_run.deleted_job_ids == ()
    assert applied.deleted_job_ids == (job.job_id,)
    assert store.list_jobs() == ()
