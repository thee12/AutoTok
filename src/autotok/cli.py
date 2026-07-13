"""Command-line interface for AutoTok."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from autotok import __version__
from autotok.analytics import (
    assign_experiment_variant,
    build_analytics_report,
    create_experiment,
    create_template_variant,
    import_performance_record,
    parse_metric_pairs,
)
from autotok.analytics_models import AnalyticsSource
from autotok.analytics_storage import AnalyticsStore
from autotok.audio_storage import AudioStore, StoredAudio
from autotok.config import AppConfig, ConfigError
from autotok.content_gate_models import ContentGateConfig, ContentGateDecision
from autotok.content_gate_storage import ContentGateStore, StoredContentGate
from autotok.content_gates import assess_story, build_override_event
from autotok.errors import AutoTokError, UserInputError
from autotok.ingestion import build_manual_file_record, build_manual_text_record
from autotok.job_models import JobStatus
from autotok.job_orchestration import (
    JOB_MANIFEST_DIRNAME,
    JOB_MANIFEST_FILENAME,
    JobRunOptions,
    StoryPipelineOptions,
    build_story_to_render_stage_definitions,
    cleanup_jobs,
    create_story_jobs,
    run_job,
)
from autotok.job_storage import JobStore
from autotok.logging import configure_logging
from autotok.media_models import MediaOrientation
from autotok.media_selection import (
    DEFAULT_RECENT_AVOIDANCE_LIMIT,
    DEFAULT_SELECTION_SEED,
    build_background_media_record,
    recent_media_ids_from_clips,
    select_background_clip,
)
from autotok.media_storage import MediaStore, StoredClip, StoredMedia
from autotok.models import SourceType, StoryRecord
from autotok.operations import (
    audit_repository,
    build_health_report,
    build_metrics_report,
    create_backup,
    inspect_restore,
    plan_retention,
    profile_operations,
)
from autotok.publishing import prepare_tiktok_publication, record_manual_tiktok_publish
from autotok.publishing_models import PublishingProvider, TikTokManualUploadOptions
from autotok.publishing_storage import PublicationStore, StoredPublication
from autotok.render import build_render_spec, render_video_package
from autotok.render_storage import RenderStore, StoredRender
from autotok.review_server import DEFAULT_REVIEW_HOST, DEFAULT_REVIEW_PORT, serve_review_dashboard
from autotok.review_storage import ReviewStore
from autotok.script_models import NarrationScriptRecord
from autotok.script_storage import ScriptStore, StoredScript
from autotok.source_adapters import (
    REDDIT_ALLOWED_SORTS,
    RedditDataApiAdapter,
    RedditDiscoveryConfig,
    discover_reddit_from_fixture,
)
from autotok.source_ingestion import build_source_post_record
from autotok.source_models import DiscoveredSourcePost, SourceProvider
from autotok.source_storage import SourceDiscoveryStore, SourceRetrievalCache, StoredSourceDiscovery
from autotok.storage import StoredStory, StoryStore
from autotok.subtitle_models import SubtitleExportFormat
from autotok.subtitle_storage import StoredSubtitle, SubtitleStore
from autotok.subtitles import (
    DEFAULT_MAX_CHARS_PER_LINE,
    DEFAULT_MAX_LINES_PER_CUE,
    DEFAULT_MAX_WORDS_PER_CUE,
    ApproximateAudioDurationStrategy,
    ProviderWordTimingStrategy,
    SubtitleTimingStrategy,
    build_subtitle_document,
    load_word_timings,
)
from autotok.transform import DEFAULT_TARGET_SECONDS, DeterministicScriptTransformer
from autotok.tts import (
    LocalWavTtsProvider,
    Pyttsx3TtsProvider,
    build_manual_audio_record,
    build_tts_audio_record,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""
    parser = argparse.ArgumentParser(
        prog="autotok",
        description="AutoTok local-first video pipeline tooling.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Override the local AutoTok data directory.",
    )

    subcommands = parser.add_subparsers(dest="command", required=True)
    _add_doctor_parser(subcommands)
    _add_story_parser(subcommands)
    _add_source_parser(subcommands)
    _add_script_parser(subcommands)
    _add_audio_parser(subcommands)
    _add_subtitle_parser(subcommands)
    _add_media_parser(subcommands)
    _add_render_parser(subcommands)
    _add_job_parser(subcommands)
    _add_review_parser(subcommands)
    _add_publish_parser(subcommands)
    _add_ops_parser(subcommands)
    _add_analytics_parser(subcommands)
    return parser


def _add_doctor_parser(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    doctor = subcommands.add_parser(
        "doctor",
        help="Run a harmless local diagnostic.",
        description="Validate local configuration and print a diagnostic summary.",
    )
    doctor.add_argument(
        "--json",
        action="store_true",
        help="Print the diagnostic summary as JSON.",
    )
    doctor.set_defaults(handler=run_doctor)


def _add_story_parser(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    story = subcommands.add_parser(
        "story",
        help="Import, inspect, and transform local manual stories.",
    )
    story_subcommands = story.add_subparsers(dest="story_command", required=True)

    story_import = story_subcommands.add_parser(
        "import",
        help="Import a manually supplied story.",
        description="Import UTF-8 story text from an argument or local file.",
    )
    input_group = story_import.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--text", help="Story text to import.")
    input_group.add_argument("--file", type=Path, help="UTF-8 text file to import.")
    story_import.add_argument("--title", help="Optional local title for the story.")
    story_import.add_argument("--json", action="store_true", help="Print import result as JSON.")
    story_import.set_defaults(handler=run_story_import)

    story_inspect = story_subcommands.add_parser(
        "inspect",
        help="Inspect an imported story record.",
    )
    story_inspect.add_argument("story_id", help="Imported story ID to inspect.")
    story_inspect.add_argument("--json", action="store_true", help="Print story record as JSON.")
    story_inspect.set_defaults(handler=run_story_inspect)

    story_transform = story_subcommands.add_parser(
        "transform",
        help="Transform an imported story into a reviewable narration script.",
    )
    story_transform.add_argument("story_id", help="Imported story ID to transform.")
    story_transform.add_argument(
        "--target-seconds",
        type=int,
        default=DEFAULT_TARGET_SECONDS,
        help="Target narration duration in seconds.",
    )
    story_transform.add_argument(
        "--provider",
        choices=["deterministic"],
        default="deterministic",
        help="Transformation provider to use.",
    )
    story_transform.add_argument("--json", action="store_true", help="Print script result as JSON.")
    story_transform.set_defaults(handler=run_story_transform)

    story_assess = story_subcommands.add_parser(
        "assess",
        help="Score a story and write its content gate decision.",
    )
    story_assess.add_argument("story_id", help="Story ID to assess before transformation.")
    story_assess.add_argument("--min-words", type=int, default=ContentGateConfig().min_words)
    story_assess.add_argument("--max-words", type=int, default=ContentGateConfig().max_words)
    story_assess.add_argument(
        "--min-duration-seconds",
        type=int,
        default=ContentGateConfig().min_duration_seconds,
    )
    story_assess.add_argument(
        "--max-duration-seconds",
        type=int,
        default=ContentGateConfig().max_duration_seconds,
    )
    story_assess.add_argument(
        "--auto-approve-min-score",
        type=int,
        default=ContentGateConfig().auto_approve_min_score,
    )
    story_assess.add_argument(
        "--reject-below-score",
        type=int,
        default=ContentGateConfig().reject_below_score,
    )
    story_assess.add_argument(
        "--near-duplicate-threshold",
        type=float,
        default=ContentGateConfig().near_duplicate_threshold,
    )
    story_assess.add_argument("--json", action="store_true", help="Print gate result as JSON.")
    story_assess.set_defaults(handler=run_story_assess)

    story_gate = story_subcommands.add_parser(
        "gate",
        help="Inspect a stored content gate decision for a story.",
    )
    story_gate.add_argument("story_id", help="Story ID with a stored gate decision.")
    story_gate.add_argument("--json", action="store_true", help="Print gate record as JSON.")
    story_gate.set_defaults(handler=run_story_gate)

    story_override = story_subcommands.add_parser(
        "override",
        help="Append a manual override to a story content gate.",
    )
    story_override.add_argument("story_id", help="Story ID with a stored gate decision.")
    story_override.add_argument(
        "--decision",
        choices=[item.value for item in ContentGateDecision],
        required=True,
        help="Manual effective decision to apply.",
    )
    story_override.add_argument("--reason", required=True, help="Reason for the manual override.")
    story_override.add_argument(
        "--reviewer",
        default="local_reviewer",
        help="Local reviewer identifier for the override trail.",
    )
    story_override.add_argument("--json", action="store_true", help="Print gate record as JSON.")
    story_override.set_defaults(handler=run_story_override)


def _add_source_parser(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    source = subcommands.add_parser(
        "source",
        help="Discover, inspect, and import approved public source posts.",
    )
    source_subcommands = source.add_subparsers(dest="source_command", required=True)

    source_discover = source_subcommands.add_parser(
        "discover",
        help="Discover approved source posts without importing them as stories.",
    )
    provider_subcommands = source_discover.add_subparsers(dest="source_provider", required=True)
    reddit = provider_subcommands.add_parser(
        "reddit",
        help="Discover public Reddit posts through the authenticated Data API or a fixture.",
    )
    reddit.add_argument("--subreddit", required=True, help="Subreddit name without the r/ prefix.")
    reddit.add_argument(
        "--sort",
        choices=sorted(REDDIT_ALLOWED_SORTS),
        default="hot",
        help="Reddit listing sort to retrieve.",
    )
    reddit.add_argument("--limit", type=int, default=25, help="Posts requested per page.")
    reddit.add_argument("--max-pages", type=int, default=1, help="Maximum listing pages to fetch.")
    reddit.add_argument(
        "--fixture-json",
        type=Path,
        help="Local Reddit listing JSON fixture to use instead of live network access.",
    )
    reddit.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass the local raw retrieval cache for live Reddit requests.",
    )
    reddit.add_argument("--json", action="store_true", help="Print discovery result as JSON.")
    reddit.set_defaults(handler=run_source_discover_reddit)

    source_inspect = source_subcommands.add_parser(
        "inspect",
        help="Inspect a stored source discovery run.",
    )
    source_inspect.add_argument("discovery_id", help="Source discovery ID to inspect.")
    source_inspect.add_argument("--json", action="store_true", help="Print discovery run as JSON.")
    source_inspect.set_defaults(handler=run_source_inspect)

    source_import = source_subcommands.add_parser(
        "import",
        help="Import one discovered post as a canonical story record.",
    )
    source_import.add_argument("discovery_id", help="Source discovery ID to import from.")
    source_import.add_argument("source_id", help="Discovered source post ID, such as t3_example.")
    source_import.add_argument("--json", action="store_true", help="Print imported story as JSON.")
    source_import.set_defaults(handler=run_source_import)


def _add_script_parser(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    script = subcommands.add_parser(
        "script",
        help="Inspect, approve, and narrate reviewable narration scripts.",
    )
    script_subcommands = script.add_subparsers(dest="script_command", required=True)

    script_inspect = script_subcommands.add_parser(
        "inspect",
        help="Inspect a generated narration script.",
    )
    script_inspect.add_argument("script_id", help="Generated script ID to inspect.")
    script_inspect.add_argument("--json", action="store_true", help="Print script record as JSON.")
    script_inspect.set_defaults(handler=run_script_inspect)

    script_approve = script_subcommands.add_parser(
        "approve",
        help="Approve a generated narration script for later phases.",
    )
    script_approve.add_argument("script_id", help="Generated script ID to approve.")
    script_approve.add_argument(
        "--json", action="store_true", help="Print approved record as JSON."
    )
    script_approve.set_defaults(handler=run_script_approve)

    script_narrate = script_subcommands.add_parser(
        "narrate",
        help="Create or import validated narration audio for an approved script.",
    )
    script_narrate.add_argument("script_id", help="Approved script ID to narrate.")
    script_narrate.add_argument(
        "--provider",
        choices=["local_wav", "pyttsx3"],
        default=None,
        help="TTS provider for generated narration audio.",
    )
    script_narrate.add_argument(
        "--audio-file",
        type=Path,
        help="Use an existing local WAV file as manually supplied narration audio.",
    )
    script_narrate.add_argument(
        "--timeout-seconds",
        type=int,
        default=None,
        help="Provider timeout in seconds.",
    )
    script_narrate.add_argument(
        "--voice-id",
        default=None,
        help="pyttsx3 system voice ID to use for generated narration audio.",
    )
    script_narrate.add_argument(
        "--rate-wpm",
        type=int,
        default=None,
        help="pyttsx3 narration rate in words per minute.",
    )
    script_narrate.add_argument("--json", action="store_true", help="Print audio record as JSON.")
    script_narrate.set_defaults(handler=run_script_narrate)


def _add_audio_parser(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    audio = subcommands.add_parser(
        "audio",
        help="Inspect validated narration audio artifacts.",
    )
    audio_subcommands = audio.add_subparsers(dest="audio_command", required=True)
    audio_inspect = audio_subcommands.add_parser(
        "inspect",
        help="Inspect a narration audio record.",
    )
    audio_inspect.add_argument("audio_id", help="Generated or imported audio ID to inspect.")
    audio_inspect.add_argument("--json", action="store_true", help="Print audio record as JSON.")
    audio_inspect.set_defaults(handler=run_audio_inspect)


def _add_subtitle_parser(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    subtitle = subcommands.add_parser(
        "subtitle",
        help="Generate, inspect, and export subtitle documents.",
    )
    subtitle_subcommands = subtitle.add_subparsers(dest="subtitle_command", required=True)

    subtitle_generate = subtitle_subcommands.add_parser(
        "generate",
        help="Generate a validated subtitle document from script and narration audio.",
    )
    subtitle_generate.add_argument("script_id", help="Script ID used for subtitle text.")
    subtitle_generate.add_argument("audio_id", help="Narration audio ID used for timing.")
    subtitle_generate.add_argument(
        "--word-timings",
        type=Path,
        help="Optional provider word-timing JSON file.",
    )
    subtitle_generate.add_argument(
        "--format",
        choices=[item.value for item in SubtitleExportFormat],
        default=SubtitleExportFormat.SRT.value,
        help="Initial subtitle export format.",
    )
    subtitle_generate.add_argument(
        "--max-chars-per-line",
        type=int,
        default=DEFAULT_MAX_CHARS_PER_LINE,
        help="Maximum displayed characters per subtitle line.",
    )
    subtitle_generate.add_argument(
        "--max-lines-per-cue",
        type=int,
        default=DEFAULT_MAX_LINES_PER_CUE,
        help="Maximum displayed lines per subtitle cue.",
    )
    subtitle_generate.add_argument(
        "--max-words-per-cue",
        type=int,
        default=DEFAULT_MAX_WORDS_PER_CUE,
        help="Maximum words grouped into a subtitle cue.",
    )
    subtitle_generate.add_argument(
        "--json", action="store_true", help="Print subtitle record as JSON."
    )
    subtitle_generate.set_defaults(handler=run_subtitle_generate)

    subtitle_inspect = subtitle_subcommands.add_parser(
        "inspect",
        help="Inspect a generated subtitle document.",
    )
    subtitle_inspect.add_argument("subtitle_id", help="Subtitle document ID to inspect.")
    subtitle_inspect.add_argument(
        "--json", action="store_true", help="Print subtitle record as JSON."
    )
    subtitle_inspect.set_defaults(handler=run_subtitle_inspect)

    subtitle_export = subtitle_subcommands.add_parser(
        "export",
        help="Export an existing subtitle document to another format.",
    )
    subtitle_export.add_argument("subtitle_id", help="Subtitle document ID to export.")
    subtitle_export.add_argument(
        "--format",
        choices=[item.value for item in SubtitleExportFormat],
        required=True,
        help="Subtitle export format to write.",
    )
    subtitle_export.add_argument("--json", action="store_true", help="Print export path as JSON.")
    subtitle_export.set_defaults(handler=run_subtitle_export)


def _add_media_parser(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    media = subcommands.add_parser(
        "media",
        help="Catalog authorized background media and select prepared clips.",
    )
    media_subcommands = media.add_subparsers(dest="media_command", required=True)

    media_import = media_subcommands.add_parser(
        "import",
        help="Import an authorized background media file into the local catalog.",
    )
    media_import.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Local video file to catalog.",
    )
    media_import.add_argument(
        "--license-note",
        required=True,
        help="Required note describing why this clip is authorized for use.",
    )
    media_import.add_argument("--usage-note", help="Optional local usage note.")
    media_import.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Tag for filtering and deterministic selection; may be repeated.",
    )
    media_import.add_argument(
        "--ffprobe-path",
        type=Path,
        default=Path("ffprobe"),
        help="Path to ffprobe executable.",
    )
    media_import.add_argument("--json", action="store_true", help="Print media record as JSON.")
    media_import.set_defaults(handler=run_media_import)

    media_inspect = media_subcommands.add_parser(
        "inspect",
        help="Inspect a cataloged background media record.",
    )
    media_inspect.add_argument("media_id", help="Cataloged media ID to inspect.")
    media_inspect.add_argument("--json", action="store_true", help="Print media record as JSON.")
    media_inspect.set_defaults(handler=run_media_inspect)

    media_select = media_subcommands.add_parser(
        "select",
        help="Select a deterministic background segment for a target duration.",
    )
    media_select.add_argument(
        "--target-seconds",
        type=float,
        required=True,
        help="Required segment duration in seconds.",
    )
    media_select.add_argument(
        "--orientation",
        choices=["any", *[item.value for item in MediaOrientation]],
        default="any",
        help="Required media orientation.",
    )
    media_select.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Required media tag; may be repeated.",
    )
    media_select.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SELECTION_SEED,
        help="Deterministic selection seed.",
    )
    media_select.add_argument(
        "--avoid-recent",
        type=int,
        default=DEFAULT_RECENT_AVOIDANCE_LIMIT,
        help="Number of recently selected media IDs to avoid when possible.",
    )
    media_select.add_argument("--json", action="store_true", help="Print clip record as JSON.")
    media_select.set_defaults(handler=run_media_select)


def _add_render_parser(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    render = subcommands.add_parser(
        "render",
        help="Create and inspect validated local video render packages.",
    )
    render_subcommands = render.add_subparsers(dest="render_command", required=True)

    render_create = render_subcommands.add_parser(
        "create",
        help="Render a validated portrait video package from completed artifacts.",
    )
    render_create.add_argument("audio_id", help="Narration audio ID to mix into the video.")
    render_create.add_argument("subtitle_id", help="Subtitle document ID to burn into the video.")
    render_create.add_argument("clip_id", help="Prepared background clip ID to render.")
    render_create.add_argument(
        "--ffmpeg-path",
        type=Path,
        default=Path("ffmpeg"),
        help="Path to ffmpeg executable.",
    )
    render_create.add_argument(
        "--ffprobe-path",
        type=Path,
        default=Path("ffprobe"),
        help="Path to ffprobe executable.",
    )
    render_create.add_argument("--json", action="store_true", help="Print render manifest as JSON.")
    render_create.set_defaults(handler=run_render_create)

    render_inspect = render_subcommands.add_parser(
        "inspect",
        help="Inspect a completed render package.",
    )
    render_inspect.add_argument("render_id", help="Render package ID to inspect.")
    render_inspect.add_argument(
        "--json", action="store_true", help="Print render manifest as JSON."
    )
    render_inspect.set_defaults(handler=run_render_inspect)


def _add_job_parser(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    job = subcommands.add_parser(
        "job",
        help="Create, inspect, resume, and clean up persistent local jobs.",
    )
    job_subcommands = job.add_subparsers(dest="job_command", required=True)

    job_create = job_subcommands.add_parser(
        "create",
        help="Create queued story-to-render job records.",
    )
    job_create.add_argument(
        "--story-id",
        action="append",
        required=True,
        help="Story ID to enqueue; may be repeated for a local batch.",
    )
    job_create.add_argument("--batch-id", help="Optional batch identifier to store on jobs.")
    job_create.add_argument(
        "--limit",
        type=int,
        help="Maximum number of provided story IDs to enqueue.",
    )
    job_create.add_argument("--json", action="store_true", help="Print created jobs as JSON.")
    job_create.set_defaults(handler=run_job_create)

    job_list = job_subcommands.add_parser(
        "list",
        help="List persistent jobs.",
    )
    job_list.add_argument(
        "--status",
        choices=[item.value for item in JobStatus],
        help="Only list jobs with this status.",
    )
    job_list.add_argument("--json", action="store_true", help="Print jobs as JSON.")
    job_list.set_defaults(handler=run_job_list)

    job_inspect = job_subcommands.add_parser(
        "inspect",
        help="Inspect a persistent job, its stages, attempts, and artifacts.",
    )
    job_inspect.add_argument("job_id", help="Job ID to inspect.")
    job_inspect.add_argument("--json", action="store_true", help="Print job details as JSON.")
    job_inspect.set_defaults(handler=run_job_inspect)

    for command_name in ("run", "resume"):
        job_run = job_subcommands.add_parser(
            command_name,
            help="Run or resume a story-to-render job.",
        )
        job_run.add_argument("job_id", help="Job ID to run or resume.")
        job_run.add_argument(
            "--target-seconds",
            type=int,
            default=DEFAULT_TARGET_SECONDS,
            help="Target narration duration for the transform stage.",
        )
        job_run.add_argument(
            "--tag",
            action="append",
            default=[],
            help="Required background-media tag for clip selection; may be repeated.",
        )
        job_run.add_argument(
            "--orientation",
            choices=["any", *[item.value for item in MediaOrientation]],
            default=MediaOrientation.PORTRAIT.value,
            help="Required background-media orientation for clip selection.",
        )
        job_run.add_argument(
            "--seed",
            type=int,
            default=DEFAULT_SELECTION_SEED,
            help="Deterministic clip-selection seed.",
        )
        job_run.add_argument(
            "--avoid-recent",
            type=int,
            default=DEFAULT_RECENT_AVOIDANCE_LIMIT,
            help="Number of recently selected media IDs to avoid when possible.",
        )
        job_run.add_argument(
            "--max-attempts",
            type=int,
            default=2,
            help="Maximum attempts per stage before the job fails.",
        )
        job_run.add_argument(
            "--stop-after",
            choices=["transform", "approve_script", "narrate", "subtitle", "select_clip", "render"],
            help="Stop after a successful stage to test resumability.",
        )
        job_run.add_argument(
            "--ffmpeg-path",
            type=Path,
            default=Path("ffmpeg"),
            help="Path to ffmpeg executable for the render stage.",
        )
        job_run.add_argument(
            "--ffprobe-path",
            type=Path,
            default=Path("ffprobe"),
            help="Path to ffprobe executable for render output validation.",
        )
        job_run.add_argument("--json", action="store_true", help="Print run summary as JSON.")
        job_run.set_defaults(handler=run_job_run)

    job_run_batch = job_subcommands.add_parser(
        "run-batch",
        help="Run or resume jobs in one local batch serially.",
    )
    job_run_batch.add_argument("batch_id", help="Batch ID to run or resume.")
    job_run_batch.add_argument(
        "--limit",
        type=int,
        help="Maximum jobs from the batch to run in this invocation.",
    )
    job_run_batch.add_argument(
        "--target-seconds",
        type=int,
        default=DEFAULT_TARGET_SECONDS,
        help="Target narration duration for the transform stage.",
    )
    job_run_batch.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Required background-media tag for clip selection; may be repeated.",
    )
    job_run_batch.add_argument(
        "--orientation",
        choices=["any", *[item.value for item in MediaOrientation]],
        default=MediaOrientation.PORTRAIT.value,
        help="Required background-media orientation for clip selection.",
    )
    job_run_batch.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SELECTION_SEED,
        help="Deterministic clip-selection seed.",
    )
    job_run_batch.add_argument(
        "--avoid-recent",
        type=int,
        default=DEFAULT_RECENT_AVOIDANCE_LIMIT,
        help="Number of recently selected media IDs to avoid when possible.",
    )
    job_run_batch.add_argument(
        "--max-attempts",
        type=int,
        default=2,
        help="Maximum attempts per stage before a job fails.",
    )
    job_run_batch.add_argument(
        "--stop-after",
        choices=["transform", "approve_script", "narrate", "subtitle", "select_clip", "render"],
        help="Stop each run job after a successful stage to test resumability.",
    )
    job_run_batch.add_argument(
        "--ffmpeg-path",
        type=Path,
        default=Path("ffmpeg"),
        help="Path to ffmpeg executable for the render stage.",
    )
    job_run_batch.add_argument(
        "--ffprobe-path",
        type=Path,
        default=Path("ffprobe"),
        help="Path to ffprobe executable for render output validation.",
    )
    job_run_batch.add_argument("--json", action="store_true", help="Print batch summary as JSON.")
    job_run_batch.set_defaults(handler=run_job_run_batch)

    job_cleanup = job_subcommands.add_parser(
        "cleanup",
        help="Dry-run or apply cleanup of old job records and job manifests.",
    )
    job_cleanup.add_argument(
        "--status",
        choices=[item.value for item in JobStatus],
        default=JobStatus.SUCCEEDED.value,
        help="Job status eligible for cleanup.",
    )
    job_cleanup.add_argument(
        "--older-than-days",
        type=int,
        default=30,
        help="Only match jobs whose updated timestamp is at least this old.",
    )
    job_cleanup.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete matching job records and job manifests.",
    )
    job_cleanup.add_argument("--json", action="store_true", help="Print cleanup result as JSON.")
    job_cleanup.set_defaults(handler=run_job_cleanup)


def _add_review_parser(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    review = subcommands.add_parser(
        "review",
        help="Serve and inspect the local review dashboard.",
    )
    review_subcommands = review.add_subparsers(dest="review_command", required=True)

    review_serve = review_subcommands.add_parser(
        "serve",
        help="Start the local browser-based review dashboard.",
    )
    review_serve.add_argument(
        "--host",
        default=DEFAULT_REVIEW_HOST,
        help="Host interface for the local dashboard server.",
    )
    review_serve.add_argument(
        "--port",
        type=int,
        default=DEFAULT_REVIEW_PORT,
        help="Port for the local dashboard server.",
    )
    review_serve.set_defaults(handler=run_review_serve)

    review_list = review_subcommands.add_parser(
        "list",
        help="List review packages discovered from local render outputs.",
    )
    review_list.add_argument("--json", action="store_true", help="Print review packages as JSON.")
    review_list.set_defaults(handler=run_review_list)

    review_inspect = review_subcommands.add_parser(
        "inspect",
        help="Inspect one review package.",
    )
    review_inspect.add_argument("render_id", help="Render package ID to inspect for review.")
    review_inspect.add_argument("--json", action="store_true", help="Print review package as JSON.")
    review_inspect.set_defaults(handler=run_review_inspect)


def _add_publish_parser(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    publish = subcommands.add_parser(
        "publish",
        help="Prepare and inspect local manual upload packages.",
    )
    publish_subcommands = publish.add_subparsers(dest="publish_command", required=True)

    tiktok = publish_subcommands.add_parser(
        "tiktok",
        help="Prepare a local TikTok manual upload package.",
    )
    tiktok.add_argument("render_id", help="Approved render package ID to publish.")
    tiktok.add_argument("--json", action="store_true", help="Print publication result as JSON.")
    tiktok.add_argument("--privacy-level", default="SELF_ONLY")
    tiktok.add_argument("--disable-duet", action="store_true")
    tiktok.add_argument("--disable-comment", action="store_true")
    tiktok.add_argument("--disable-stitch", action="store_true")
    tiktok.add_argument("--cover-ms", type=int, default=0)
    tiktok.set_defaults(handler=run_publish_tiktok)

    status = publish_subcommands.add_parser(
        "status",
        help="Inspect local manual upload package state.",
    )
    status.add_argument("render_id", help="Render package ID with publication state.")
    status.add_argument("--json", action="store_true", help="Print status as JSON.")
    status.set_defaults(handler=run_publish_status)

    mark = publish_subcommands.add_parser(
        "mark",
        help="Record that a TikTok package was manually published.",
    )
    mark.add_argument("render_id", help="Render package ID with a prepared upload package.")
    mark.add_argument("--url", help="Optional TikTok URL after manual publishing.")
    mark.add_argument("--json", action="store_true", help="Print status as JSON.")
    mark.set_defaults(handler=run_publish_mark)


def _add_analytics_parser(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    analytics = subcommands.add_parser(
        "analytics",
        help="Record local performance analytics, experiments, templates, and reports.",
    )
    analytics_subcommands = analytics.add_subparsers(dest="analytics_command", required=True)

    template = analytics_subcommands.add_parser("template", help="Manage template variants.")
    template_subcommands = template.add_subparsers(dest="template_command", required=True)

    template_create = template_subcommands.add_parser(
        "create",
        help="Create a reusable content template variant.",
    )
    template_create.add_argument("--name", required=True)
    template_create.add_argument("--description", default="")
    template_create.add_argument("--hook", default="")
    template_create.add_argument("--outro", default="")
    template_create.add_argument("--caption-template", default="")
    template_create.add_argument("--hashtag", action="append", default=[])
    template_create.add_argument("--subtitle-theme", default="")
    template_create.add_argument("--json", action="store_true")
    template_create.set_defaults(handler=run_analytics_template_create)

    template_list = template_subcommands.add_parser("list", help="List template variants.")
    template_list.add_argument("--json", action="store_true")
    template_list.set_defaults(handler=run_analytics_template_list)

    template_inspect = template_subcommands.add_parser(
        "inspect",
        help="Inspect a template variant.",
    )
    template_inspect.add_argument("template_id")
    template_inspect.add_argument("--json", action="store_true")
    template_inspect.set_defaults(handler=run_analytics_template_inspect)

    experiment = analytics_subcommands.add_parser("experiment", help="Manage experiments.")
    experiment_subcommands = experiment.add_subparsers(dest="experiment_command", required=True)

    experiment_create = experiment_subcommands.add_parser(
        "create",
        help="Create a local experiment definition.",
    )
    experiment_create.add_argument("--name", required=True)
    experiment_create.add_argument("--hypothesis", required=True)
    experiment_create.add_argument("--primary-metric", required=True)
    experiment_create.add_argument("--variant-id", action="append", required=True)
    experiment_create.add_argument("--notes", default="")
    experiment_create.add_argument("--json", action="store_true")
    experiment_create.set_defaults(handler=run_analytics_experiment_create)

    experiment_list = experiment_subcommands.add_parser("list", help="List experiments.")
    experiment_list.add_argument("--json", action="store_true")
    experiment_list.set_defaults(handler=run_analytics_experiment_list)

    experiment_assign = experiment_subcommands.add_parser(
        "assign",
        help="Assign a render to an experiment template variant.",
    )
    experiment_assign.add_argument("experiment_id")
    experiment_assign.add_argument("template_id")
    experiment_assign.add_argument("render_id")
    experiment_assign.add_argument("--notes", default="")
    experiment_assign.add_argument("--json", action="store_true")
    experiment_assign.set_defaults(handler=run_analytics_experiment_assign)

    performance_import = analytics_subcommands.add_parser(
        "import",
        help="Import manual or officially exported performance metrics for a render.",
    )
    performance_import.add_argument("render_id")
    performance_import.add_argument("--provider", default="manual")
    performance_import.add_argument(
        "--source",
        choices=[item.value for item in AnalyticsSource],
        default=AnalyticsSource.MANUAL.value,
    )
    performance_import.add_argument("--metric", action="append", required=True)
    performance_import.add_argument("--captured-at")
    performance_import.add_argument("--experiment-id")
    performance_import.add_argument("--template-id")
    performance_import.add_argument("--publication-id")
    performance_import.add_argument("--notes", default="")
    performance_import.add_argument("--json", action="store_true")
    performance_import.set_defaults(handler=run_analytics_import)

    report = analytics_subcommands.add_parser(
        "report",
        help="Build a local analytics report and recommendations.",
    )
    report.add_argument("--json", action="store_true")
    report.set_defaults(handler=run_analytics_report)


def _add_ops_parser(subcommands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    ops = subcommands.add_parser(
        "ops",
        help="Run local operational health, backup, audit, and maintenance commands.",
    )
    ops_subcommands = ops.add_subparsers(dest="ops_command", required=True)

    health = ops_subcommands.add_parser("health", help="Run local health checks.")
    health.add_argument("--json", action="store_true", help="Print health report as JSON.")
    health.set_defaults(handler=run_ops_health)

    metrics = ops_subcommands.add_parser("metrics", help="Print local artifact and job metrics.")
    metrics.add_argument("--json", action="store_true", help="Print metrics as JSON.")
    metrics.set_defaults(handler=run_ops_metrics)

    backup = ops_subcommands.add_parser("backup", help="Create a ZIP backup of the data directory.")
    backup.add_argument("--output", type=Path, required=True, help="Backup ZIP path to create.")
    backup.add_argument(
        "--include-cache",
        action="store_true",
        help="Include cache files that are excluded by default.",
    )
    backup.add_argument("--json", action="store_true", help="Print backup result as JSON.")
    backup.set_defaults(handler=run_ops_backup)

    restore = ops_subcommands.add_parser(
        "restore",
        help="Inspect or restore a backup archive into an empty data directory.",
    )
    restore.add_argument("--archive", type=Path, required=True, help="Backup ZIP to restore.")
    restore.add_argument(
        "--target-data-dir",
        type=Path,
        help="Restore target; defaults to the configured data directory.",
    )
    restore.add_argument("--apply", action="store_true", help="Actually restore files.")
    restore.add_argument("--json", action="store_true", help="Print restore result as JSON.")
    restore.set_defaults(handler=run_ops_restore)

    retention = ops_subcommands.add_parser(
        "retention",
        help="Plan or apply cleanup for transient cache/log/tmp files.",
    )
    retention.add_argument("--older-than-days", type=int, required=True)
    retention.add_argument("--apply", action="store_true", help="Delete matching transient files.")
    retention.add_argument("--json", action="store_true", help="Print retention plan as JSON.")
    retention.set_defaults(handler=run_ops_retention)

    audit = ops_subcommands.add_parser(
        "audit",
        help="Run local dependency inventory and high-confidence secret checks.",
    )
    audit.add_argument("--json", action="store_true", help="Print audit report as JSON.")
    audit.set_defaults(handler=run_ops_audit)

    profile = ops_subcommands.add_parser(
        "profile",
        help="Profile local metrics collection as an operational baseline.",
    )
    profile.add_argument("--iterations", type=int, default=3)
    profile.add_argument("--json", action="store_true", help="Print profile result as JSON.")
    profile.set_defaults(handler=run_ops_profile)


def run_analytics_template_create(args: argparse.Namespace) -> int:
    """Create a reusable analytics template variant."""
    config = _load_config(args)
    template = create_template_variant(
        AnalyticsStore(config.data_dir),
        name=args.name,
        description=args.description,
        hook=args.hook,
        outro=args.outro,
        caption_template=args.caption_template,
        hashtags=tuple(args.hashtag),
        subtitle_theme=args.subtitle_theme,
    )
    payload = template.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Template variant: {template.template_id}")
        print(f"Name: {template.name}")
        print(f"Hashtags: {', '.join(template.hashtags) or '(none)'}")
    return 0


def run_analytics_template_list(args: argparse.Namespace) -> int:
    """List analytics template variants."""
    config = _load_config(args)
    templates = AnalyticsStore(config.data_dir).list_templates()
    payload = {"templates": [template.to_dict() for template in templates]}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if not templates:
            print("No template variants found.")
        for template in templates:
            print(f"{template.template_id} {template.name}")
    return 0


def run_analytics_template_inspect(args: argparse.Namespace) -> int:
    """Inspect one analytics template variant."""
    config = _load_config(args)
    template = AnalyticsStore(config.data_dir).load_template(args.template_id)
    payload = template.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Template variant: {template.template_id}")
        print(f"Name: {template.name}")
        print(f"Description: {template.description or '(none)'}")
        print(f"Subtitle theme: {template.subtitle_theme or '(none)'}")
    return 0


def run_analytics_experiment_create(args: argparse.Namespace) -> int:
    """Create a local analytics experiment."""
    config = _load_config(args)
    experiment = create_experiment(
        AnalyticsStore(config.data_dir),
        name=args.name,
        hypothesis=args.hypothesis,
        primary_metric=args.primary_metric,
        variant_ids=tuple(args.variant_id),
        notes=args.notes,
    )
    payload = experiment.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Experiment: {experiment.experiment_id}")
        print(f"Name: {experiment.name}")
        print(f"Primary metric: {experiment.primary_metric}")
    return 0


def run_analytics_experiment_list(args: argparse.Namespace) -> int:
    """List local analytics experiments."""
    config = _load_config(args)
    experiments = AnalyticsStore(config.data_dir).list_experiments()
    payload = {"experiments": [experiment.to_dict() for experiment in experiments]}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if not experiments:
            print("No experiments found.")
        for experiment in experiments:
            print(
                f"{experiment.experiment_id} {experiment.status.value} "
                f"metric={experiment.primary_metric}"
            )
    return 0


def run_analytics_experiment_assign(args: argparse.Namespace) -> int:
    """Assign a render to an experiment template variant."""
    config = _load_config(args)
    assignment = assign_experiment_variant(
        AnalyticsStore(config.data_dir),
        data_dir=config.data_dir,
        experiment_id=args.experiment_id,
        template_id=args.template_id,
        render_id=args.render_id,
        notes=args.notes,
    )
    payload = assignment.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Experiment assignment: {assignment.assignment_id}")
        print(f"Render: {assignment.render_id}")
        print(f"Template: {assignment.template_id}")
    return 0


def run_analytics_import(args: argparse.Namespace) -> int:
    """Import render performance metrics."""
    config = _load_config(args)
    record = import_performance_record(
        AnalyticsStore(config.data_dir),
        data_dir=config.data_dir,
        render_id=args.render_id,
        provider=args.provider,
        metrics=parse_metric_pairs(tuple(args.metric)),
        source=AnalyticsSource(args.source),
        captured_at=args.captured_at,
        experiment_id=args.experiment_id,
        template_id=args.template_id,
        publication_id=args.publication_id,
        notes=args.notes,
    )
    payload = record.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Performance record: {record.performance_id}")
        print(f"Render: {record.render_id}")
        print(f"Metrics: {', '.join(f'{key}={value:g}' for key, value in record.metrics.items())}")
    return 0


def run_analytics_report(args: argparse.Namespace) -> int:
    """Build a local analytics report."""
    config = _load_config(args)
    report = build_analytics_report(AnalyticsStore(config.data_dir))
    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("Analytics report")
        print(f"Performance records: {report.performance_count}")
        print(f"Experiments: {report.experiment_count}")
        print(f"Templates: {report.template_count}")
        print(f"Recommendations: {len(report.recommendations)}")
        for recommendation in report.recommendations:
            print(f"{recommendation.confidence.value}: {recommendation.title}")
    return 0


def run_ops_health(args: argparse.Namespace) -> int:
    """Run local operational health checks."""
    config = _load_config(args)
    report = build_health_report(config.data_dir)
    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Operational health: {report.status}")
        for check in report.checks:
            print(f"{check.status}: {check.name} - {check.message}")
    return 1 if report.status == "error" else 0


def run_ops_metrics(args: argparse.Namespace) -> int:
    """Print local operational metrics."""
    config = _load_config(args)
    payload = build_metrics_report(config.data_dir)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        totals = payload["totals"]
        print("Operational metrics")
        if isinstance(totals, Mapping):
            print(f"Files: {totals['file_count']}")
            print(f"Bytes: {totals['bytes']}")
        print(f"Data directory: {payload['data_dir']}")
    return 0


def run_ops_backup(args: argparse.Namespace) -> int:
    """Create a data-directory backup."""
    config = _load_config(args)
    payload = create_backup(
        config.data_dir,
        args.output,
        include_cache=args.include_cache,
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        manifest = payload["manifest"]
        print(f"Backup: {payload['archive']}")
        if isinstance(manifest, Mapping):
            print(f"Files: {manifest['file_count']}")
            print(f"Bytes: {manifest['bytes']}")
    return 0


def run_ops_restore(args: argparse.Namespace) -> int:
    """Inspect or restore a backup archive."""
    config = _load_config(args)
    target = config.data_dir if args.target_data_dir is None else args.target_data_dir
    payload = inspect_restore(args.archive, target, apply=args.apply)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        mode = "Restored" if payload.get("restored") else "Restore dry run"
        print(f"{mode}: {payload['archive']}")
        print(f"Target: {payload['target_data_dir']}")
        print(f"Files: {payload['file_count']}")
        if not args.apply:
            print("Dry run: pass --apply to restore into an empty target directory.")
    return 0


def run_ops_retention(args: argparse.Namespace) -> int:
    """Plan or apply transient artifact cleanup."""
    config = _load_config(args)
    payload = plan_retention(
        config.data_dir,
        older_than_days=args.older_than_days,
        apply=args.apply,
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        mode = "Deleted" if args.apply else "Matched"
        print(f"{mode} transient files: {payload['candidate_count']}")
        if not args.apply:
            print("Dry run: pass --apply to delete matching transient files.")
    return 0


def run_ops_audit(args: argparse.Namespace) -> int:
    """Run local dependency and secret audit checks."""
    _load_config(args)
    report = audit_repository(Path.cwd())
    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Operational audit: {report.status}")
        for check in report.checks:
            print(f"{check.status}: {check.name} - {check.message}")
    return 1 if report.status == "error" else 0


def run_ops_profile(args: argparse.Namespace) -> int:
    """Profile local metrics collection."""
    config = _load_config(args)
    payload = profile_operations(config.data_dir, iterations=args.iterations)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("Operational profile")
        print(f"Operation: {payload['operation']}")
        print(f"Iterations: {payload['iterations']}")
        print(f"Average seconds: {payload['avg_seconds']:.6f}")
    return 0


def run_review_serve(args: argparse.Namespace) -> int:
    """Start the local review dashboard server."""
    config = _load_config(args)
    if args.port <= 0:
        raise UserInputError("Review dashboard port must be greater than zero.")
    url = f"http://{args.host}:{args.port}/"
    print(f"Serving AutoTok review dashboard at {url}")
    print("Press Ctrl+C to stop.")
    try:
        serve_review_dashboard(config.data_dir, host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("Review dashboard stopped.")
    return 0


def run_review_list(args: argparse.Namespace) -> int:
    """List local review packages."""
    config = _load_config(args)
    packages = ReviewStore(config.data_dir).list()
    payload = {"reviews": [package.to_dict() for package in packages]}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if not packages:
            print("No review packages found.")
        for package in packages:
            print(f"{package.render_id} {package.status.value} story={package.story_id}")
    return 0


def run_review_inspect(args: argparse.Namespace) -> int:
    """Inspect one local review package."""
    config = _load_config(args)
    store = ReviewStore(config.data_dir)
    details = store.details(args.render_id)
    if args.json:
        print(json.dumps(details, indent=2, sort_keys=True))
    else:
        package = store.load(args.render_id)
        print(f"Review package: {package.render_id}")
        print(f"Status: {package.status.value}")
        print(f"Story: {package.story_id}")
        print(f"Script: {package.script_id}")
        print(f"Output: {package.output_path}")
        print(f"Audit events: {len(package.audit_events)}")
    return 0


def run_publish_tiktok(args: argparse.Namespace) -> int:
    """Prepare a local TikTok manual upload package."""
    config = _load_config(args)
    result = prepare_tiktok_publication(
        config=config,
        render_id=args.render_id,
        options=_tiktok_options_from_args(args),
    )
    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        record = result.record
        package = result.package
        print(f"TikTok manual upload package: {record.publication_id}")
        print(f"Render: {record.render_id}")
        print(f"Status: {record.status.value}")
        print(f"Video: {package.video_path}")
        print(f"Caption: {package.caption_path}")
        print(f"Metadata: {package.metadata_path}")
        print(f"Instructions: {package.instructions_path}")
        record_path = PublicationStore(config.data_dir)._record_path(
            record.render_id,
            record.provider,
        )
        print(f"Record: {record_path}")
    return 0


def run_publish_status(args: argparse.Namespace) -> int:
    """Inspect local manual publication status."""
    config = _load_config(args)
    stored = PublicationStore(config.data_dir).load(args.render_id, PublishingProvider.TIKTOK)
    payload = _stored_publication_payload(stored)
    record = stored.record
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Publication: {record.publication_id}")
        print(f"Provider: {record.provider.value}")
        print(f"Render: {record.render_id}")
        print(f"Status: {record.status.value}")
        if record.upload_package is not None:
            print(f"Package: {record.upload_package.package_dir}")
            print(f"Video: {record.upload_package.video_path}")
            print(f"Instructions: {record.upload_package.instructions_path}")
        if record.manual_publish_url is not None:
            print(f"Manual TikTok URL: {record.manual_publish_url}")
        print(f"Audit events: {len(record.audit_events)}")
    return 0


def run_publish_mark(args: argparse.Namespace) -> int:
    """Record that the operator manually published a TikTok package."""
    config = _load_config(args)
    record = record_manual_tiktok_publish(config=config, render_id=args.render_id, url=args.url)
    stored = PublicationStore(config.data_dir).load(record.render_id, record.provider)
    payload = _stored_publication_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Publication: {record.publication_id}")
        print(f"Render: {record.render_id}")
        print(f"Status: {record.status.value}")
        if record.manual_publish_url is not None:
            print(f"Manual TikTok URL: {record.manual_publish_url}")
    return 0


def run_job_create(args: argparse.Namespace) -> int:
    """Create queued persistent jobs for one or more stories."""
    config = _load_config(args)
    story_store = StoryStore(config.data_dir)
    for story_id in args.story_id:
        story_store.load(story_id)
    jobs = create_story_jobs(
        JobStore(config.data_dir),
        args.story_id,
        batch_id=args.batch_id,
        limit=args.limit,
    )
    payload = {"jobs": [job.to_dict() for job in jobs]}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for job in jobs:
            print(f"Created job: {job.job_id}")
            print(f"Story: {job.story_id}")
            print(f"Status: {job.status.value}")
            if job.batch_id is not None:
                print(f"Batch: {job.batch_id}")
    return 0


def run_job_list(args: argparse.Namespace) -> int:
    """List persistent jobs."""
    config = _load_config(args)
    status = JobStatus(args.status) if args.status is not None else None
    jobs = JobStore(config.data_dir).list_jobs(status=status)
    payload = {"jobs": [job.to_dict() for job in jobs]}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if not jobs:
            print("No jobs found.")
        for job in jobs:
            story = job.story_id or "(none)"
            batch = f" batch={job.batch_id}" if job.batch_id is not None else ""
            print(f"{job.job_id} {job.status.value} story={story}{batch}")
    return 0


def run_job_inspect(args: argparse.Namespace) -> int:
    """Inspect a persistent job."""
    config = _load_config(args)
    store = JobStore(config.data_dir)
    payload = _job_payload(config, store, args.job_id)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        job = store.load_job(args.job_id)
        stages = store.list_stages(args.job_id)
        artifacts = store.list_artifacts(args.job_id)
        print(f"Job: {job.job_id}")
        print(f"Status: {job.status.value}")
        print(f"Story: {job.story_id or '(none)'}")
        print(f"Batch: {job.batch_id or '(none)'}")
        print(f"Manifest: {payload['manifest_path']}")
        print("Stages:")
        for stage in stages:
            print(f"  {stage.name}: {stage.status.value} attempts={stage.attempt_count}")
        print(f"Artifacts: {len(artifacts)}")
    return 0


def run_job_run(args: argparse.Namespace) -> int:
    """Run or resume a persistent story-to-render job."""
    config = _load_config(args)
    store = JobStore(config.data_dir)
    pipeline_options = _story_pipeline_options_from_args(args)
    summary = run_job(
        config=config,
        store=store,
        job_id=args.job_id,
        stage_definitions=build_story_to_render_stage_definitions(config, pipeline_options),
        options=JobRunOptions(max_attempts=args.max_attempts, stop_after=args.stop_after),
    )
    payload = summary.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Job: {summary.job.job_id}")
        print(f"Status: {summary.job.status.value}")
        print(f"Completed: {summary.completed}")
        if summary.stopped_after is not None:
            print(f"Stopped after: {summary.stopped_after}")
        print(f"Manifest: {summary.manifest_path}")
        for stage in summary.stages:
            print(f"{stage.name}: {stage.status.value} attempts={stage.attempt_count}")
    return 0 if summary.job.status is not JobStatus.FAILED else 1


def run_job_run_batch(args: argparse.Namespace) -> int:
    """Run or resume jobs in a persistent local batch."""
    if args.limit is not None and args.limit <= 0:
        raise UserInputError("Batch run limit must be greater than zero.")
    config = _load_config(args)
    store = JobStore(config.data_dir)
    jobs = [
        job
        for job in store.list_jobs()
        if job.batch_id == args.batch_id
        and job.status not in {JobStatus.CANCELED, JobStatus.SUCCEEDED}
    ]
    if args.limit is not None:
        jobs = jobs[: args.limit]
    if not jobs:
        raise UserInputError(f"No runnable jobs were found for batch: {args.batch_id}")
    pipeline_options = _story_pipeline_options_from_args(args)
    summaries = [
        run_job(
            config=config,
            store=store,
            job_id=job.job_id,
            stage_definitions=build_story_to_render_stage_definitions(config, pipeline_options),
            options=JobRunOptions(max_attempts=args.max_attempts, stop_after=args.stop_after),
        )
        for job in jobs
    ]
    payload = {
        "batch_id": args.batch_id,
        "job_count": len(summaries),
        "summaries": [summary.to_dict() for summary in summaries],
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Batch: {args.batch_id}")
        print(f"Jobs run: {len(summaries)}")
        for summary in summaries:
            print(f"{summary.job.job_id}: {summary.job.status.value} completed={summary.completed}")
    return 1 if any(summary.job.status is JobStatus.FAILED for summary in summaries) else 0


def run_job_cleanup(args: argparse.Namespace) -> int:
    """Dry-run or apply cleanup for old job records and manifests."""
    config = _load_config(args)
    result = cleanup_jobs(
        store=JobStore(config.data_dir),
        data_dir=config.data_dir,
        status=JobStatus(args.status),
        older_than_days=args.older_than_days,
        apply=args.apply,
    )
    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        mode = "Deleted" if args.apply else "Matched"
        print(
            f"{mode} jobs: {len(result.deleted_job_ids if args.apply else result.matched_job_ids)}"
        )
        if not args.apply:
            print("Dry run: pass --apply to delete matching job records and job manifests.")
        for job_id in result.deleted_job_ids if args.apply else result.matched_job_ids:
            print(job_id)
    return 0


def run_story_assess(args: argparse.Namespace) -> int:
    """Score a story and write its content gate decision."""
    config = _load_config(args)
    story_store = StoryStore(config.data_dir)
    story = story_store.load(args.story_id).record
    gate_config = _content_gate_config_from_args(args)
    record = assess_story(
        story,
        existing_stories=tuple(stored.record for stored in story_store.list()),
        config=gate_config,
    )
    stored = ContentGateStore(config.data_dir).save(record)
    payload = _stored_content_gate_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "created" if stored.created else "existing"
        print(f"Content gate: {stored.record.gate_id}")
        print(f"Status: {status}")
        print(f"Story: {stored.record.story_id}")
        print(f"Decision: {stored.record.decision.value}")
        print(f"Effective decision: {stored.record.effective_decision.value}")
        print(f"Quality score: {stored.record.quality_score.total}")
        print(f"Review flags: {', '.join(stored.record.review_flags) or '(none)'}")
        print(f"Reject reasons: {', '.join(stored.record.reject_reasons) or '(none)'}")
        print(f"Record: {stored.record_path}")
    return 0


def run_story_gate(args: argparse.Namespace) -> int:
    """Inspect a stored content gate decision."""
    config = _load_config(args)
    stored = ContentGateStore(config.data_dir).load_for_story(args.story_id)
    payload = _stored_content_gate_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Content gate: {stored.record.gate_id}")
        print(f"Story: {stored.record.story_id}")
        print(f"Decision: {stored.record.decision.value}")
        print(f"Effective decision: {stored.record.effective_decision.value}")
        print(f"Quality score: {stored.record.quality_score.total}")
        print(f"Duplicates: {len(stored.record.duplicate_matches)}")
        print(f"Warnings: {len(stored.record.warnings)}")
        print(f"Overrides: {len(stored.record.override_events)}")
        print(f"Record: {stored.record_path}")
    return 0


def run_story_override(args: argparse.Namespace) -> int:
    """Append a manual content gate override event."""
    config = _load_config(args)
    event = build_override_event(
        decision=ContentGateDecision(args.decision),
        reason=args.reason,
        reviewer=args.reviewer,
    )
    stored = ContentGateStore(config.data_dir).append_override(args.story_id, event)
    payload = _stored_content_gate_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Content gate: {stored.record.gate_id}")
        print(f"Story: {stored.record.story_id}")
        print(f"Effective decision: {stored.record.effective_decision.value}")
        print(f"Overrides: {len(stored.record.override_events)}")
        print(f"Record: {stored.record_path}")
    return 0


def run_source_discover_reddit(args: argparse.Namespace) -> int:
    """Discover approved Reddit posts and cache the discovery run."""
    config = _load_config(args)
    reddit_config = RedditDiscoveryConfig(
        subreddit=args.subreddit,
        sort=args.sort,
        limit=args.limit,
        max_pages=args.max_pages,
        user_agent=config.reddit_user_agent,
        oauth_token=config.reddit_oauth_token,
        timeout_seconds=config.reddit_timeout_seconds,
        use_cache=not args.no_cache,
    )
    if args.fixture_json is None:
        cache = SourceRetrievalCache(config.data_dir, SourceProvider.REDDIT)
        result = RedditDataApiAdapter().discover(reddit_config, cache=cache)
    else:
        result = discover_reddit_from_fixture(args.fixture_json, reddit_config)

    stored = SourceDiscoveryStore(config.data_dir).save(result.run, raw_pages=result.raw_pages)
    payload = _stored_source_discovery_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "created" if stored.created else "existing"
        print(f"Source discovery: {stored.record.discovery_id}")
        print(f"Status: {status}")
        print(f"Provider: {stored.record.provider.value}")
        print(f"Posts: {len(stored.record.posts)}")
        print(f"Cache hits: {stored.record.cache_hits}")
        print(f"Record: {stored.record_path}")
    return 0


def run_source_inspect(args: argparse.Namespace) -> int:
    """Inspect a stored source discovery run."""
    config = _load_config(args)
    stored = SourceDiscoveryStore(config.data_dir).load(args.discovery_id)
    payload = _stored_source_discovery_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Source discovery: {stored.record.discovery_id}")
        print(f"Provider: {stored.record.provider.value}")
        print(f"Created at: {stored.record.created_at}")
        print(f"Posts: {len(stored.record.posts)}")
        print(f"Record: {stored.record_path}")
        for post in stored.record.posts[:5]:
            print(f"- {post.source_id}: {_source_post_preview(post)}")
    return 0


def run_source_import(args: argparse.Namespace) -> int:
    """Import a discovered source post as a canonical story record."""
    config = _load_config(args)
    discovery = SourceDiscoveryStore(config.data_dir).load(args.discovery_id)
    post = _find_discovered_post(discovery.record.posts, args.source_id)
    record = build_source_post_record(post)
    stored = StoryStore(config.data_dir).save(record)
    payload = _stored_story_payload(stored)
    payload["source_discovery"] = {
        "discovery_id": discovery.record.discovery_id,
        "source_id": post.source_id,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "created" if stored.created else "existing"
        print(f"Imported discovered story: {stored.record.story_id}")
        print(f"Status: {status}")
        print(f"Source post: {post.source_id}")
        print(f"Source URL: {post.source_url}")
        print(f"Record: {stored.record_path}")
    return 0


def run_doctor(args: argparse.Namespace) -> int:
    """Run the harmless diagnostic command."""
    config = _load_config(args)

    diagnostic = {
        "application": "autotok",
        "version": __version__,
        "environment": config.environment,
        "log_level": config.log_level,
        "log_format": config.log_format,
        "data_dir": str(config.data_dir),
        "tts_provider": config.tts_provider,
        "tts_timeout_seconds": config.tts_timeout_seconds,
        "reddit_user_agent": config.reddit_user_agent,
        "reddit_oauth_token_configured": config.reddit_oauth_token is not None,
        "reddit_timeout_seconds": config.reddit_timeout_seconds,
        "tiktok_publishing_mode": "manual_upload",
        "status": "ok",
    }
    if args.json:
        print(json.dumps(diagnostic, indent=2, sort_keys=True))
    else:
        print("AutoTok diagnostic: ok")
        print(f"Version: {diagnostic['version']}")
        print(f"Environment: {diagnostic['environment']}")
        print(f"Log level: {diagnostic['log_level']}")
        print(f"Log format: {diagnostic['log_format']}")
        print(f"Data directory: {diagnostic['data_dir']}")
        print(f"TTS provider: {diagnostic['tts_provider']}")
        print(f"TTS timeout seconds: {diagnostic['tts_timeout_seconds']}")
        print(f"Reddit user agent: {diagnostic['reddit_user_agent']}")
        print(f"Reddit OAuth token configured: {diagnostic['reddit_oauth_token_configured']}")
        print(f"Reddit timeout seconds: {diagnostic['reddit_timeout_seconds']}")
        print(f"TikTok publishing mode: {diagnostic['tiktok_publishing_mode']}")
    return 0


def run_story_import(args: argparse.Namespace) -> int:
    """Import a manual story from text or a UTF-8 file."""
    config = _load_config(args)
    if args.text is not None:
        record = build_manual_text_record(args.text, title=args.title)
    else:
        record = build_manual_file_record(args.file, title=args.title)

    stored = StoryStore(config.data_dir).save(record)
    payload = _stored_story_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "created" if stored.created else "existing"
        print(f"Imported story: {stored.record.story_id}")
        print(f"Status: {status}")
        print(f"Source type: {stored.record.source.source_type.value}")
        print(f"Content SHA-256: {stored.record.source.content_sha256}")
        print(f"Record: {stored.record_path}")
    return 0


def run_story_inspect(args: argparse.Namespace) -> int:
    """Inspect a stored story record by ID."""
    config = _load_config(args)
    stored = StoryStore(config.data_dir).load(args.story_id)
    payload = _stored_story_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        record = stored.record
        print(f"Story: {record.story_id}")
        print(f"Title: {record.source.title or '(untitled)'}")
        print(f"Source type: {record.source.source_type.value}")
        print(f"Imported at: {record.source.imported_at}")
        print(f"Content SHA-256: {record.source.content_sha256}")
        print(f"Characters: {record.source.normalized_character_count}")
        if record.source.source_path is not None:
            print(f"Source path: {record.source.source_path}")
        print(f"Record: {stored.record_path}")
        print(f"Preview: {_story_preview(record)}")
    return 0


def run_story_transform(args: argparse.Namespace) -> int:
    """Transform a stored story into a reviewable narration script."""
    config = _load_config(args)
    story = StoryStore(config.data_dir).load(args.story_id).record
    _assert_story_transform_gate(config, story)
    transformer = _load_transformer(args.provider)
    script = transformer.transform(story, target_seconds=args.target_seconds)
    stored = ScriptStore(config.data_dir).save(script, before_text=story.normalized_text)
    payload = _stored_script_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "created" if stored.created else "existing"
        print(f"Generated script: {stored.record.script_id}")
        print(f"Status: {status}")
        print(f"Review status: {stored.record.review_status.value}")
        print(f"Target seconds: {stored.record.duration_budget.target_seconds}")
        print(f"Estimated seconds: {stored.record.duration_budget.estimated_seconds}")
        print(f"Record: {stored.record_path}")
    return 0


def run_script_inspect(args: argparse.Namespace) -> int:
    """Inspect a stored narration script."""
    config = _load_config(args)
    stored = ScriptStore(config.data_dir).load(args.script_id)
    payload = _stored_script_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        record = stored.record
        print(f"Script: {record.script_id}")
        print(f"Story: {record.story_id}")
        print(f"Review status: {record.review_status.value}")
        print(f"Provider: {record.provider_name} {record.provider_version}")
        print(f"Target seconds: {record.duration_budget.target_seconds}")
        print(f"Estimated seconds: {record.duration_budget.estimated_seconds}")
        print(f"Privacy redactions: {record.privacy_report.total_redactions}")
        print(f"Record: {stored.record_path}")
        print(f"Preview: {_script_preview(record)}")
    return 0


def run_script_approve(args: argparse.Namespace) -> int:
    """Approve a stored narration script."""
    config = _load_config(args)
    stored = ScriptStore(config.data_dir).approve(args.script_id)
    payload = _stored_script_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Approved script: {stored.record.script_id}")
        print(f"Approved at: {stored.record.approved_at}")
        print(f"Record: {stored.record_path}")
    return 0


def run_script_narrate(args: argparse.Namespace) -> int:
    """Create or import validated narration audio for an approved script."""
    config = _load_config(args)
    config = config.with_overrides(
        tts_provider=args.provider,
        tts_timeout_seconds=args.timeout_seconds,
    )
    script = ScriptStore(config.data_dir).load(args.script_id).record
    if args.audio_file is None:
        provider = _load_tts_provider(
            config.tts_provider,
            voice_id=args.voice_id,
            rate_wpm=args.rate_wpm,
        )
        record, source_audio_path = build_tts_audio_record(
            script,
            provider=provider,
            timeout_seconds=config.tts_timeout_seconds,
        )
    else:
        if args.voice_id is not None or args.rate_wpm is not None:
            raise UserInputError("pyttsx3 voice and rate options cannot be used with --audio-file.")
        record = build_manual_audio_record(script, audio_path=args.audio_file)
        source_audio_path = args.audio_file.expanduser()

    stored = AudioStore(config.data_dir).save(record, source_audio_path=source_audio_path)
    payload = _stored_audio_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "created" if stored.created else "existing"
        print(f"Narration audio: {stored.record.audio_id}")
        print(f"Status: {status}")
        print(f"Source type: {stored.record.source_type.value}")
        print(f"Provider: {stored.record.provider_name} {stored.record.provider_version}")
        print(f"Duration seconds: {stored.record.metadata.duration_seconds}")
        print(f"Record: {stored.record_path}")
        print(f"Audio: {stored.audio_path}")
    return 0


def run_audio_inspect(args: argparse.Namespace) -> int:
    """Inspect a stored narration audio record."""
    config = _load_config(args)
    stored = AudioStore(config.data_dir).load(args.audio_id)
    payload = _stored_audio_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        record = stored.record
        print(f"Audio: {record.audio_id}")
        print(f"Script: {record.script_id}")
        print(f"Story: {record.story_id}")
        print(f"Source type: {record.source_type.value}")
        print(f"Provider: {record.provider_name} {record.provider_version}")
        print(f"Duration seconds: {record.metadata.duration_seconds}")
        print(f"Sample rate Hz: {record.metadata.sample_rate_hz}")
        print(f"Channels: {record.metadata.channels}")
        print(f"Record: {stored.record_path}")
        print(f"Audio: {stored.audio_path}")
    return 0


def run_media_import(args: argparse.Namespace) -> int:
    """Import an authorized background media file."""
    config = _load_config(args)
    media_path = args.file.expanduser()
    record = build_background_media_record(
        media_path=media_path,
        license_note=args.license_note,
        usage_note=args.usage_note,
        tags=args.tag,
        ffprobe_command=[str(args.ffprobe_path)],
    )
    stored = MediaStore(config.data_dir).save_media(record, source_media_path=media_path)
    payload = _stored_media_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "created" if stored.created else "existing"
        print(f"Background media: {stored.record.media_id}")
        print(f"Status: {status}")
        print(f"Orientation: {stored.record.metadata.orientation.value}")
        print(f"Duration seconds: {stored.record.metadata.duration_seconds}")
        print(f"Tags: {', '.join(stored.record.tags) or '(none)'}")
        print(f"Record: {stored.record_path}")
        print(f"Media: {stored.media_path}")
    return 0


def run_media_inspect(args: argparse.Namespace) -> int:
    """Inspect a cataloged background media record."""
    config = _load_config(args)
    stored = MediaStore(config.data_dir).load_media(args.media_id)
    payload = _stored_media_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        record = stored.record
        print(f"Background media: {record.media_id}")
        print(f"Original filename: {record.original_filename}")
        print(f"Orientation: {record.metadata.orientation.value}")
        print(f"Duration seconds: {record.metadata.duration_seconds}")
        print(f"Resolution: {record.metadata.width}x{record.metadata.height}")
        print(f"Tags: {', '.join(record.tags) or '(none)'}")
        print(f"License note: {record.license_note}")
        print(f"Record: {stored.record_path}")
        print(f"Media: {stored.media_path}")
    return 0


def run_media_select(args: argparse.Namespace) -> int:
    """Select and store a background clip-preparation artifact."""
    config = _load_config(args)
    store = MediaStore(config.data_dir)
    orientation = None if args.orientation == "any" else MediaOrientation(args.orientation)
    recent_media_ids = recent_media_ids_from_clips(store.list_clips(), limit=args.avoid_recent)
    record = select_background_clip(
        store.list_media(),
        target_duration_seconds=args.target_seconds,
        seed=args.seed,
        orientation=orientation,
        required_tags=args.tag,
        recent_media_ids=recent_media_ids,
    )
    stored = store.save_clip(record)
    payload = _stored_clip_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "created" if stored.created else "existing"
        print(f"Prepared clip: {stored.record.clip_id}")
        print(f"Status: {status}")
        print(f"Media: {stored.record.media_id}")
        print(f"Start seconds: {stored.record.start_seconds}")
        print(f"End seconds: {stored.record.end_seconds}")
        print(f"Seed: {stored.record.seed}")
        print(f"Record: {stored.record_path}")
    return 0


def run_render_create(args: argparse.Namespace) -> int:
    """Create a validated local video render package."""
    config = _load_config(args)
    audio = AudioStore(config.data_dir).load(args.audio_id)
    subtitle = SubtitleStore(config.data_dir).load(args.subtitle_id)
    media_store = MediaStore(config.data_dir)
    clip = media_store.load_clip(args.clip_id)
    media = media_store.load_media(clip.record.media_id)
    spec = build_render_spec(audio=audio, subtitle=subtitle, media=media, clip=clip)
    stored = render_video_package(
        store=RenderStore(config.data_dir),
        spec=spec,
        subtitle=subtitle,
        ffmpeg_command=[str(args.ffmpeg_path)],
        ffprobe_command=[str(args.ffprobe_path)],
    )
    payload = _stored_render_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "created" if stored.created else "existing"
        metadata = stored.manifest.output_metadata
        print(f"Render package: {stored.manifest.render_id}")
        print(f"Status: {status}")
        print(f"Output: {stored.paths.output_path}")
        print(f"Duration seconds: {metadata.duration_seconds}")
        print(f"Resolution: {metadata.width}x{metadata.height}")
        print(f"Manifest: {stored.paths.manifest_path}")
    return 0


def run_render_inspect(args: argparse.Namespace) -> int:
    """Inspect a completed local video render package."""
    config = _load_config(args)
    stored = RenderStore(config.data_dir).load(args.render_id)
    payload = _stored_render_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        metadata = stored.manifest.output_metadata
        print(f"Render package: {stored.manifest.render_id}")
        print(f"Status: {stored.manifest.status}")
        print(f"Output: {stored.paths.output_path}")
        print(f"Duration seconds: {metadata.duration_seconds}")
        print(f"Resolution: {metadata.width}x{metadata.height}")
        print(f"Manifest: {stored.paths.manifest_path}")
    return 0


def run_subtitle_generate(args: argparse.Namespace) -> int:
    """Generate a subtitle document from a script/audio pair."""
    config = _load_config(args)
    script = ScriptStore(config.data_dir).load(args.script_id).record
    audio = AudioStore(config.data_dir).load(args.audio_id).record
    export_format = SubtitleExportFormat(args.format)
    timing_strategy: SubtitleTimingStrategy
    if args.word_timings is None:
        timing_strategy = ApproximateAudioDurationStrategy()
    else:
        timing_strategy = ProviderWordTimingStrategy(load_word_timings(args.word_timings))
    document = build_subtitle_document(
        script=script,
        audio=audio,
        timing_strategy=timing_strategy,
        export_format=export_format,
        max_chars_per_line=args.max_chars_per_line,
        max_lines_per_cue=args.max_lines_per_cue,
        max_words_per_cue=args.max_words_per_cue,
    )
    stored = SubtitleStore(config.data_dir).save(document)
    payload = _stored_subtitle_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "created" if stored.created else "existing"
        print(f"Subtitle document: {stored.document.subtitle_id}")
        print(f"Status: {status}")
        print(f"Timing strategy: {stored.document.metadata.timing_strategy.value}")
        print(f"Approximate: {stored.document.metadata.approximate}")
        print(f"Cues: {len(stored.document.cues)}")
        print(f"Record: {stored.record_path}")
        print(f"Export: {stored.export_path}")
    return 0


def run_subtitle_inspect(args: argparse.Namespace) -> int:
    """Inspect a stored subtitle document."""
    config = _load_config(args)
    stored = SubtitleStore(config.data_dir).load(args.subtitle_id)
    payload = _stored_subtitle_payload(stored)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        document = stored.document
        print(f"Subtitle document: {document.subtitle_id}")
        print(f"Script: {document.script_id}")
        print(f"Audio: {document.audio_id}")
        print(f"Timing strategy: {document.metadata.timing_strategy.value}")
        print(f"Approximate: {document.metadata.approximate}")
        print(f"Cues: {len(document.cues)}")
        print(f"Record: {stored.record_path}")
        print(f"Export: {stored.export_path}")
    return 0


def run_subtitle_export(args: argparse.Namespace) -> int:
    """Export a stored subtitle document to a requested format."""
    config = _load_config(args)
    export_format = SubtitleExportFormat(args.format)
    export_path = SubtitleStore(config.data_dir).export(args.subtitle_id, export_format)
    if args.json:
        print(json.dumps({"subtitle_id": args.subtitle_id, "export": str(export_path)}, indent=2))
    else:
        print(f"Exported subtitle: {export_path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the CLI and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return int(args.handler(args))
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except AutoTokError as exc:
        print(f"AutoTok error: {exc}", file=sys.stderr)
        return 1


def _load_config(args: argparse.Namespace) -> AppConfig:
    config = AppConfig.from_environment().with_overrides(data_dir=args.data_dir)
    configure_logging(config.log_level, log_format=config.log_format)
    return config


def _load_transformer(provider: str) -> DeterministicScriptTransformer:
    if provider == "deterministic":
        return DeterministicScriptTransformer()
    raise UserInputError(f"Unsupported script transformation provider: {provider}")


def _load_tts_provider(
    provider: str,
    *,
    voice_id: str | None = None,
    rate_wpm: int | None = None,
) -> LocalWavTtsProvider | Pyttsx3TtsProvider:
    if provider == "local_wav":
        if voice_id is not None or rate_wpm is not None:
            raise UserInputError("pyttsx3 voice and rate options require --provider pyttsx3.")
        return LocalWavTtsProvider()
    if provider == "pyttsx3":
        if rate_wpm is None:
            return Pyttsx3TtsProvider(voice_id=voice_id)
        return Pyttsx3TtsProvider(voice_id=voice_id, rate_wpm=rate_wpm)
    raise UserInputError(f"Unsupported TTS provider: {provider}")


def _content_gate_config_from_args(args: argparse.Namespace) -> ContentGateConfig:
    return ContentGateConfig(
        min_words=args.min_words,
        max_words=args.max_words,
        min_duration_seconds=args.min_duration_seconds,
        max_duration_seconds=args.max_duration_seconds,
        auto_approve_min_score=args.auto_approve_min_score,
        reject_below_score=args.reject_below_score,
        near_duplicate_threshold=args.near_duplicate_threshold,
    )


def _assert_story_transform_gate(config: AppConfig, story: StoryRecord) -> None:
    try:
        stored = ContentGateStore(config.data_dir).load_for_story(story.story_id)
    except UserInputError as exc:
        if story.source.source_type is SourceType.REDDIT_POST:
            raise UserInputError(
                "Discovered stories must pass `autotok story assess` before transformation."
            ) from exc
        return

    if stored.record.effective_decision is not ContentGateDecision.APPROVED:
        raise UserInputError(
            "Story content gate must be approved before transformation; "
            f"current effective decision is {stored.record.effective_decision.value}."
        )


def _tiktok_options_from_args(args: argparse.Namespace) -> TikTokManualUploadOptions:
    if args.cover_ms < 0:
        raise UserInputError("--cover-ms must be greater than or equal to zero.")
    return TikTokManualUploadOptions(
        privacy_level=args.privacy_level,
        disable_duet=args.disable_duet,
        disable_comment=args.disable_comment,
        disable_stitch=args.disable_stitch,
        cover_timestamp_ms=args.cover_ms,
    )


def _story_pipeline_options_from_args(args: argparse.Namespace) -> StoryPipelineOptions:
    orientation = None if args.orientation == "any" else MediaOrientation(args.orientation)
    return StoryPipelineOptions(
        target_seconds=args.target_seconds,
        media_tags=tuple(args.tag),
        media_orientation=orientation,
        seed=args.seed,
        avoid_recent=args.avoid_recent,
        ffmpeg_path=args.ffmpeg_path,
        ffprobe_path=args.ffprobe_path,
    )


def _job_payload(config: AppConfig, store: JobStore, job_id: str) -> dict[str, object]:
    job = store.load_job(job_id)
    stages = store.list_stages(job_id)
    return {
        "job": job.to_dict(),
        "stages": [stage.to_dict() for stage in stages],
        "attempts_by_stage": {
            stage.stage_id: [attempt.to_dict() for attempt in store.list_attempts(stage.stage_id)]
            for stage in stages
        },
        "artifacts": [artifact.to_dict() for artifact in store.list_artifacts(job_id)],
        "manifest_path": str(
            config.data_dir / JOB_MANIFEST_DIRNAME / job_id / JOB_MANIFEST_FILENAME
        ),
    }


def _stored_publication_payload(stored: StoredPublication) -> dict[str, Any]:
    payload = stored.record.to_dict()
    payload["created"] = stored.created
    payload["artifacts"] = {"record": str(stored.record_path)}
    return payload


def _stored_content_gate_payload(stored: StoredContentGate) -> dict[str, Any]:
    payload = stored.record.to_dict()
    payload["created"] = stored.created
    payload["artifacts"] = {"record": str(stored.record_path)}
    return payload


def _stored_source_discovery_payload(stored: StoredSourceDiscovery) -> dict[str, Any]:
    payload = stored.record.to_dict()
    payload["created"] = stored.created
    payload["artifacts"] = {
        "record": str(stored.record_path),
        "raw_pages_dir": str(stored.raw_pages_dir),
        "raw_pages": [str(path) for path in stored.raw_page_paths],
    }
    return payload


def _find_discovered_post(
    posts: tuple[DiscoveredSourcePost, ...],
    source_id: str,
) -> DiscoveredSourcePost:
    for post in posts:
        if post.source_id == source_id:
            return post
    raise UserInputError(f"Discovered source post was not found: {source_id}")


def _stored_story_payload(stored: StoredStory) -> dict[str, Any]:
    payload = stored.record.to_dict()
    payload["created"] = stored.created
    payload["artifacts"] = {
        "record": str(stored.record_path),
        "original_text": str(stored.original_text_path),
        "normalized_text": str(stored.normalized_text_path),
    }
    return payload


def _stored_script_payload(stored: StoredScript) -> dict[str, Any]:
    payload = stored.record.to_dict()
    payload["created"] = stored.created
    payload["full_text"] = stored.record.full_text
    payload["artifacts"] = {
        "record": str(stored.record_path),
        "before_text": str(stored.before_text_path),
        "script_text": str(stored.script_text_path),
    }
    return payload


def _stored_audio_payload(stored: StoredAudio) -> dict[str, Any]:
    payload = stored.record.to_dict()
    payload["created"] = stored.created
    payload["artifacts"] = {
        "record": str(stored.record_path),
        "audio": str(stored.audio_path),
    }
    return payload


def _stored_media_payload(stored: StoredMedia) -> dict[str, Any]:
    payload = stored.record.to_dict()
    payload["created"] = stored.created
    payload["artifacts"] = {
        "record": str(stored.record_path),
        "media": str(stored.media_path),
    }
    return payload


def _stored_clip_payload(stored: StoredClip) -> dict[str, Any]:
    payload = stored.record.to_dict()
    payload["created"] = stored.created
    payload["artifacts"] = {"record": str(stored.record_path)}
    return payload


def _stored_render_payload(stored: StoredRender) -> dict[str, Any]:
    payload = stored.manifest.to_dict()
    payload["created"] = stored.created
    payload["artifacts"] = {
        "manifest": str(stored.paths.manifest_path),
        "render_spec": str(stored.paths.spec_path),
        "output": str(stored.paths.output_path),
        "subtitle_ass": str(stored.paths.subtitle_ass_path),
    }
    return payload


def _stored_subtitle_payload(stored: StoredSubtitle) -> dict[str, Any]:
    payload = stored.document.to_dict()
    payload["created"] = stored.created
    payload["artifacts"] = {
        "record": str(stored.record_path),
        "export": str(stored.export_path),
    }
    return payload


def _source_post_preview(post: DiscoveredSourcePost) -> str:
    text = " ".join(post.story_text.split())
    if len(text) <= 100:
        return text
    return f"{text[:97]}..."


def _story_preview(record: StoryRecord) -> str:
    text = " ".join(record.normalized_text.split())
    if len(text) <= 120:
        return text
    return f"{text[:117]}..."


def _script_preview(record: NarrationScriptRecord) -> str:
    text = " ".join(record.full_text.split())
    if len(text) <= 120:
        return text
    return f"{text[:117]}..."


if __name__ == "__main__":
    raise SystemExit(main())
