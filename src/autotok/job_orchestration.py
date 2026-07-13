"""Resumable local job orchestration for Phase 9."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from autotok.audio_storage import AudioStore
from autotok.config import AppConfig
from autotok.content_gate_models import ContentGateDecision
from autotok.content_gate_storage import ContentGateStore
from autotok.errors import AutoTokError, PersistenceError, UserInputError
from autotok.job_models import (
    ArtifactType,
    JobArtifactRecord,
    JobRecord,
    JobStatus,
    StageRecord,
    StageStatus,
)
from autotok.job_storage import JobStore
from autotok.media_models import MediaOrientation
from autotok.media_selection import (
    DEFAULT_RECENT_AVOIDANCE_LIMIT,
    DEFAULT_SELECTION_SEED,
    recent_media_ids_from_clips,
    select_background_clip,
)
from autotok.media_storage import MediaStore
from autotok.models import SourceType
from autotok.render import build_render_spec, render_video_package
from autotok.render_storage import RenderStore
from autotok.script_storage import ScriptStore
from autotok.storage import StoryStore
from autotok.subtitle_models import SubtitleExportFormat
from autotok.subtitle_storage import SubtitleStore
from autotok.subtitles import ApproximateAudioDurationStrategy, build_subtitle_document
from autotok.transform import DEFAULT_TARGET_SECONDS, DeterministicScriptTransformer
from autotok.tts import LocalWavTtsProvider, Pyttsx3TtsProvider, build_tts_audio_record

DEFAULT_MAX_JOB_ATTEMPTS = 2
DEFAULT_CLIP_PADDING_SECONDS = 1.0
JOB_MANIFEST_DIRNAME = "jobs"
JOB_MANIFEST_FILENAME = "manifest.json"
STORY_TO_RENDER_PIPELINE = "story_to_render"

StageExecutor = Callable[["JobRunContext"], "StageExecutionResult | None"]


@dataclass(frozen=True, slots=True)
class StageExecutionResult:
    """Artifact produced by one orchestration stage."""

    artifact_type: ArtifactType
    artifact_ref: str
    path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class JobStageDefinition:
    """Executable definition for one ordered pipeline stage."""

    name: str
    execute: StageExecutor


@dataclass(frozen=True, slots=True)
class JobRunContext:
    """Context passed to one stage execution."""

    config: AppConfig
    store: JobStore
    job: JobRecord
    stage: StageRecord


@dataclass(frozen=True, slots=True)
class JobRunOptions:
    """Runtime controls for a resumable job run."""

    max_attempts: int = DEFAULT_MAX_JOB_ATTEMPTS
    stop_after: str | None = None


@dataclass(frozen=True, slots=True)
class JobRunSummary:
    """Result of running or resuming a job."""

    job: JobRecord
    stages: tuple[StageRecord, ...]
    artifacts: tuple[JobArtifactRecord, ...]
    manifest_path: Path
    completed: bool
    stopped_after: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize a run summary for CLI output."""
        return {
            "job": self.job.to_dict(),
            "completed": self.completed,
            "stopped_after": self.stopped_after,
            "manifest_path": str(self.manifest_path),
            "stages": [stage.to_dict() for stage in self.stages],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }


@dataclass(frozen=True, slots=True)
class StoryPipelineOptions:
    """Options for the local story-to-render pipeline."""

    target_seconds: int = DEFAULT_TARGET_SECONDS
    media_tags: tuple[str, ...] = ()
    media_orientation: MediaOrientation | None = MediaOrientation.PORTRAIT
    seed: int = DEFAULT_SELECTION_SEED
    avoid_recent: int = DEFAULT_RECENT_AVOIDANCE_LIMIT
    subtitle_format: SubtitleExportFormat = SubtitleExportFormat.SRT
    ffmpeg_path: Path = Path("ffmpeg")
    ffprobe_path: Path = Path("ffprobe")
    clip_padding_seconds: float = DEFAULT_CLIP_PADDING_SECONDS
    tts_provider: str | None = None
    tts_voice_id: str | None = None
    tts_rate_wpm: int | None = None


@dataclass(frozen=True, slots=True)
class JobCleanupResult:
    """Summary of cleanup candidates or applied deletions."""

    matched_job_ids: tuple[str, ...]
    deleted_job_ids: tuple[str, ...]
    dry_run: bool

    def to_dict(self) -> dict[str, object]:
        """Serialize cleanup results for CLI output."""
        return {
            "matched_job_ids": list(self.matched_job_ids),
            "deleted_job_ids": list(self.deleted_job_ids),
            "dry_run": self.dry_run,
        }


def build_story_to_render_stage_definitions(
    config: AppConfig,
    options: StoryPipelineOptions,
) -> tuple[JobStageDefinition, ...]:
    """Build the concrete local pipeline stages available in Phase 9."""

    def transform(context: JobRunContext) -> StageExecutionResult:
        story = _load_job_story(config, context.job)
        _assert_story_transform_gate(config, story.source.source_type, story.story_id)
        script = DeterministicScriptTransformer().transform(
            story,
            target_seconds=options.target_seconds,
        )
        stored = ScriptStore(config.data_dir).save(script, before_text=story.normalized_text)
        return StageExecutionResult(
            artifact_type=ArtifactType.SCRIPT,
            artifact_ref=stored.record.script_id,
            path=str(stored.record_path),
            metadata={"created": stored.created},
        )

    def approve_script(context: JobRunContext) -> StageExecutionResult:
        script_id = _latest_artifact_ref(context.store, context.job.job_id, ArtifactType.SCRIPT)
        stored = ScriptStore(config.data_dir).approve(script_id)
        return StageExecutionResult(
            artifact_type=ArtifactType.SCRIPT,
            artifact_ref=stored.record.script_id,
            path=str(stored.record_path),
            metadata={"review_status": stored.record.review_status.value},
        )

    def narrate(context: JobRunContext) -> StageExecutionResult:
        script_id = _latest_artifact_ref(context.store, context.job.job_id, ArtifactType.SCRIPT)
        script = ScriptStore(config.data_dir).load(script_id).record
        provider = _build_job_tts_provider(config=config, options=options)
        record, source_audio_path = build_tts_audio_record(
            script,
            provider=provider,
            timeout_seconds=config.tts_timeout_seconds,
        )
        stored = AudioStore(config.data_dir).save(record, source_audio_path=source_audio_path)
        return StageExecutionResult(
            artifact_type=ArtifactType.AUDIO,
            artifact_ref=stored.record.audio_id,
            path=str(stored.record_path),
            metadata={"created": stored.created},
        )

    def subtitle(context: JobRunContext) -> StageExecutionResult:
        script_id = _latest_artifact_ref(context.store, context.job.job_id, ArtifactType.SCRIPT)
        audio_id = _latest_artifact_ref(context.store, context.job.job_id, ArtifactType.AUDIO)
        script = ScriptStore(config.data_dir).load(script_id).record
        audio = AudioStore(config.data_dir).load(audio_id).record
        document = build_subtitle_document(
            script=script,
            audio=audio,
            timing_strategy=ApproximateAudioDurationStrategy(),
            export_format=options.subtitle_format,
        )
        stored = SubtitleStore(config.data_dir).save(document)
        return StageExecutionResult(
            artifact_type=ArtifactType.SUBTITLE,
            artifact_ref=stored.document.subtitle_id,
            path=str(stored.record_path),
            metadata={"created": stored.created},
        )

    def select_clip(context: JobRunContext) -> StageExecutionResult:
        audio_id = _latest_artifact_ref(context.store, context.job.job_id, ArtifactType.AUDIO)
        audio = AudioStore(config.data_dir).load(audio_id).record
        media_store = MediaStore(config.data_dir)
        recent_media_ids = recent_media_ids_from_clips(
            media_store.list_clips(),
            limit=options.avoid_recent,
        )
        clip = select_background_clip(
            media_store.list_media(),
            target_duration_seconds=audio.metadata.duration_seconds + options.clip_padding_seconds,
            seed=options.seed,
            orientation=options.media_orientation,
            required_tags=options.media_tags,
            recent_media_ids=recent_media_ids,
        )
        stored = media_store.save_clip(clip)
        return StageExecutionResult(
            artifact_type=ArtifactType.CLIP,
            artifact_ref=stored.record.clip_id,
            path=str(stored.record_path),
            metadata={"created": stored.created, "media_id": stored.record.media_id},
        )

    def render(context: JobRunContext) -> StageExecutionResult:
        audio_id = _latest_artifact_ref(context.store, context.job.job_id, ArtifactType.AUDIO)
        subtitle_id = _latest_artifact_ref(context.store, context.job.job_id, ArtifactType.SUBTITLE)
        clip_id = _latest_artifact_ref(context.store, context.job.job_id, ArtifactType.CLIP)
        audio = AudioStore(config.data_dir).load(audio_id)
        subtitle_record = SubtitleStore(config.data_dir).load(subtitle_id)
        media_store = MediaStore(config.data_dir)
        clip = media_store.load_clip(clip_id)
        media = media_store.load_media(clip.record.media_id)
        spec = build_render_spec(audio=audio, subtitle=subtitle_record, media=media, clip=clip)
        stored = render_video_package(
            store=RenderStore(config.data_dir),
            spec=spec,
            subtitle=subtitle_record,
            ffmpeg_command=[str(options.ffmpeg_path)],
            ffprobe_command=[str(options.ffprobe_path)],
        )
        return StageExecutionResult(
            artifact_type=ArtifactType.RENDER,
            artifact_ref=stored.manifest.render_id,
            path=str(stored.paths.manifest_path),
            metadata={"created": stored.created, "output": str(stored.paths.output_path)},
        )

    return (
        JobStageDefinition("transform", transform),
        JobStageDefinition("approve_script", approve_script),
        JobStageDefinition("narrate", narrate),
        JobStageDefinition("subtitle", subtitle),
        JobStageDefinition("select_clip", select_clip),
        JobStageDefinition("render", render),
    )


def _build_job_tts_provider(
    *,
    config: AppConfig,
    options: StoryPipelineOptions,
) -> LocalWavTtsProvider | Pyttsx3TtsProvider:
    provider_name = options.tts_provider or config.tts_provider
    if provider_name == "local_wav":
        if options.tts_voice_id is not None or options.tts_rate_wpm is not None:
            raise UserInputError("pyttsx3 voice and rate options require --tts-provider pyttsx3.")
        return LocalWavTtsProvider()
    if provider_name == "pyttsx3":
        if options.tts_rate_wpm is None:
            return Pyttsx3TtsProvider(voice_id=options.tts_voice_id)
        return Pyttsx3TtsProvider(voice_id=options.tts_voice_id, rate_wpm=options.tts_rate_wpm)
    raise UserInputError(f"Unsupported TTS provider: {provider_name}")


def create_story_jobs(
    store: JobStore,
    story_ids: Sequence[str],
    *,
    batch_id: str | None = None,
    limit: int | None = None,
) -> tuple[JobRecord, ...]:
    """Create queued jobs for one local batch of story IDs."""
    cleaned_story_ids = tuple(story_id.strip() for story_id in story_ids if story_id.strip())
    if not cleaned_story_ids:
        raise UserInputError("At least one story ID is required to create a job.")
    if limit is not None and limit <= 0:
        raise UserInputError("Batch limit must be greater than zero.")
    selected_story_ids = cleaned_story_ids[:limit]
    effective_batch_id = batch_id or (_new_batch_id() if len(selected_story_ids) > 1 else None)
    return tuple(
        store.create_job(
            story_id=story_id,
            batch_id=effective_batch_id,
            metadata={"pipeline": STORY_TO_RENDER_PIPELINE},
        )
        for story_id in selected_story_ids
    )


def run_job(
    *,
    config: AppConfig,
    store: JobStore,
    job_id: str,
    stage_definitions: Sequence[JobStageDefinition],
    options: JobRunOptions | None = None,
) -> JobRunSummary:
    """Run or resume a job, skipping successful stages and retrying failed ones."""
    run_options = options or JobRunOptions()
    if run_options.max_attempts <= 0:
        raise UserInputError("Job max attempts must be greater than zero.")
    definition_names = tuple(definition.name for definition in stage_definitions)
    if len(set(definition_names)) != len(definition_names):
        raise UserInputError("Job stage names must be unique.")
    if run_options.stop_after is not None and run_options.stop_after not in definition_names:
        raise UserInputError(f"Unknown stop-after stage: {run_options.stop_after}")

    job = store.update_job_status(job_id, JobStatus.RUNNING)
    _recover_running_stages(store, job.job_id)
    stages_by_name = {
        definition.name: store.ensure_stage(job.job_id, definition.name)
        for definition in stage_definitions
    }

    stopped_after: str | None = None
    try:
        for definition in stage_definitions:
            stage = stages_by_name[definition.name]
            stage = store.load_stage(stage.stage_id)
            if stage.status is StageStatus.SUCCEEDED:
                if run_options.stop_after == definition.name:
                    stopped_after = definition.name
                    break
                continue
            _run_stage_until_terminal(
                config=config,
                store=store,
                job=job,
                stage=stage,
                definition=definition,
                max_attempts=run_options.max_attempts,
            )
            if run_options.stop_after == definition.name:
                stopped_after = definition.name
                break
    except AutoTokError:
        failed_job = store.update_job_status(job.job_id, JobStatus.FAILED)
        manifest_path = write_job_manifest(config.data_dir, store, failed_job.job_id)
        return JobRunSummary(
            job=failed_job,
            stages=store.list_stages(job.job_id),
            artifacts=store.list_artifacts(job.job_id),
            manifest_path=manifest_path,
            completed=False,
        )

    final_status = JobStatus.SUCCEEDED if stopped_after is None else JobStatus.QUEUED
    final_job = store.update_job_status(job.job_id, final_status)
    manifest_path = write_job_manifest(config.data_dir, store, final_job.job_id)
    store.add_artifact_once(
        final_job.job_id,
        artifact_type=ArtifactType.MANIFEST,
        artifact_ref=final_job.job_id,
        path=str(manifest_path),
        metadata={"kind": "job_manifest"},
    )
    return JobRunSummary(
        job=final_job,
        stages=store.list_stages(final_job.job_id),
        artifacts=store.list_artifacts(final_job.job_id),
        manifest_path=manifest_path,
        completed=final_status is JobStatus.SUCCEEDED,
        stopped_after=stopped_after,
    )


def write_job_manifest(data_dir: Path, store: JobStore, job_id: str) -> Path:
    """Write a current machine-readable job manifest."""
    job = store.load_job(job_id)
    stages = store.list_stages(job_id)
    attempts_by_stage = {
        stage.stage_id: [attempt.to_dict() for attempt in store.list_attempts(stage.stage_id)]
        for stage in stages
    }
    artifacts = store.list_artifacts(job_id)
    payload = {
        "schema_version": 1,
        "written_at": _utc_timestamp(),
        "job": job.to_dict(),
        "stages": [stage.to_dict() for stage in stages],
        "attempts_by_stage": attempts_by_stage,
        "artifacts": [artifact.to_dict() for artifact in artifacts],
    }
    manifest_path = _job_manifest_path(data_dir, job_id)
    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        raise PersistenceError(f"Could not write job manifest: {manifest_path}") from exc
    return manifest_path


def cleanup_jobs(
    *,
    store: JobStore,
    data_dir: Path,
    status: JobStatus,
    older_than_days: int,
    apply: bool,
) -> JobCleanupResult:
    """Find or delete job records matching a retention policy."""
    if older_than_days < 0:
        raise UserInputError("Retention age must not be negative.")
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    candidates = tuple(
        job
        for job in store.list_jobs(status=status)
        if _parse_utc_timestamp(job.updated_at) <= cutoff
    )
    matched = tuple(job.job_id for job in candidates)
    deleted: list[str] = []
    if apply:
        for job in candidates:
            store.delete_job(job.job_id)
            _delete_job_manifest_dir(data_dir, job.job_id)
            deleted.append(job.job_id)
    return JobCleanupResult(
        matched_job_ids=matched, deleted_job_ids=tuple(deleted), dry_run=not apply
    )


def _run_stage_until_terminal(
    *,
    config: AppConfig,
    store: JobStore,
    job: JobRecord,
    stage: StageRecord,
    definition: JobStageDefinition,
    max_attempts: int,
) -> None:
    current = stage
    while current.status is not StageStatus.SUCCEEDED and current.attempt_count < max_attempts:
        attempt = store.start_attempt(current.stage_id)
        current = store.load_stage(current.stage_id)
        context = JobRunContext(config=config, store=store, job=job, stage=current)
        try:
            result = definition.execute(context)
        except AutoTokError as exc:
            store.finish_attempt(
                attempt.attempt_id,
                StageStatus.FAILED,
                error_message=str(exc),
            )
            current = store.load_stage(current.stage_id)
            continue
        if result is not None:
            store.add_artifact_once(
                job.job_id,
                stage_id=current.stage_id,
                artifact_type=result.artifact_type,
                artifact_ref=result.artifact_ref,
                path=result.path,
                metadata=result.metadata,
            )
        store.finish_attempt(attempt.attempt_id, StageStatus.SUCCEEDED)
        return
    latest = store.load_stage(current.stage_id)
    if latest.status is not StageStatus.SUCCEEDED:
        raise UserInputError(
            f"Job stage failed after {latest.attempt_count} attempt(s): {definition.name}"
        )


def _recover_running_stages(store: JobStore, job_id: str) -> None:
    for stage in store.list_stages(job_id):
        if stage.status is not StageStatus.RUNNING:
            continue
        running_attempts = [
            attempt
            for attempt in store.list_attempts(stage.stage_id)
            if attempt.status is StageStatus.RUNNING
        ]
        if running_attempts:
            store.finish_attempt(
                running_attempts[-1].attempt_id,
                StageStatus.FAILED,
                error_message="Recovered incomplete running attempt before resume.",
            )
        else:
            store.update_stage_status(
                stage.stage_id,
                StageStatus.FAILED,
                error_message="Recovered incomplete running stage before resume.",
            )


def _latest_artifact_ref(store: JobStore, job_id: str, artifact_type: ArtifactType) -> str:
    for artifact in reversed(store.list_artifacts(job_id)):
        if artifact.artifact_type is artifact_type:
            return artifact.artifact_ref
    raise UserInputError(f"Job does not have a {artifact_type.value} artifact yet.")


def _load_job_story(config: AppConfig, job: JobRecord):  # type: ignore[no-untyped-def]
    if job.story_id is None:
        raise UserInputError("Job does not have a story ID.")
    return StoryStore(config.data_dir).load(job.story_id).record


def _assert_story_transform_gate(
    config: AppConfig,
    source_type: SourceType,
    story_id: str,
) -> None:
    try:
        stored = ContentGateStore(config.data_dir).load_for_story(story_id)
    except UserInputError as exc:
        if source_type is SourceType.REDDIT_POST:
            raise UserInputError(
                "Discovered stories must pass `autotok story assess` before transformation."
            ) from exc
        return
    if stored.record.effective_decision is not ContentGateDecision.APPROVED:
        raise UserInputError(
            "Story content gate must be approved before transformation; "
            f"current effective decision is {stored.record.effective_decision.value}."
        )


def _job_manifest_path(data_dir: Path, job_id: str) -> Path:
    return data_dir / JOB_MANIFEST_DIRNAME / job_id / JOB_MANIFEST_FILENAME


def _delete_job_manifest_dir(data_dir: Path, job_id: str) -> None:
    jobs_dir = (data_dir / JOB_MANIFEST_DIRNAME).resolve()
    target = (jobs_dir / job_id).resolve()
    if target == jobs_dir or jobs_dir not in target.parents:
        raise PersistenceError(f"Refusing to delete unexpected job manifest path: {target}")
    if target.exists():
        shutil.rmtree(target)


def _parse_utc_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_batch_id() -> str:
    return f"batch_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
