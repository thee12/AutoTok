"""Command-line interface for AutoTok."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from autotok import __version__
from autotok.audio_storage import AudioStore, StoredAudio
from autotok.config import AppConfig, ConfigError
from autotok.errors import AutoTokError, UserInputError
from autotok.ingestion import build_manual_file_record, build_manual_text_record
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
from autotok.models import StoryRecord
from autotok.script_models import NarrationScriptRecord
from autotok.script_storage import ScriptStore, StoredScript
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
    _add_script_parser(subcommands)
    _add_audio_parser(subcommands)
    _add_subtitle_parser(subcommands)
    _add_media_parser(subcommands)
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
        choices=["local_wav"],
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


def run_doctor(args: argparse.Namespace) -> int:
    """Run the harmless diagnostic command."""
    config = _load_config(args)

    diagnostic = {
        "application": "autotok",
        "version": __version__,
        "environment": config.environment,
        "log_level": config.log_level,
        "data_dir": str(config.data_dir),
        "tts_provider": config.tts_provider,
        "tts_timeout_seconds": config.tts_timeout_seconds,
        "status": "ok",
    }
    if args.json:
        print(json.dumps(diagnostic, indent=2, sort_keys=True))
    else:
        print("AutoTok diagnostic: ok")
        print(f"Version: {diagnostic['version']}")
        print(f"Environment: {diagnostic['environment']}")
        print(f"Log level: {diagnostic['log_level']}")
        print(f"Data directory: {diagnostic['data_dir']}")
        print(f"TTS provider: {diagnostic['tts_provider']}")
        print(f"TTS timeout seconds: {diagnostic['tts_timeout_seconds']}")
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
        provider = _load_tts_provider(config.tts_provider)
        record, source_audio_path = build_tts_audio_record(
            script,
            provider=provider,
            timeout_seconds=config.tts_timeout_seconds,
        )
    else:
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
    configure_logging(config.log_level)
    return config


def _load_transformer(provider: str) -> DeterministicScriptTransformer:
    if provider == "deterministic":
        return DeterministicScriptTransformer()
    raise UserInputError(f"Unsupported script transformation provider: {provider}")


def _load_tts_provider(provider: str) -> LocalWavTtsProvider:
    if provider == "local_wav":
        return LocalWavTtsProvider()
    raise UserInputError(f"Unsupported TTS provider: {provider}")


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


def _stored_subtitle_payload(stored: StoredSubtitle) -> dict[str, Any]:
    payload = stored.document.to_dict()
    payload["created"] = stored.created
    payload["artifacts"] = {
        "record": str(stored.record_path),
        "export": str(stored.export_path),
    }
    return payload


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
