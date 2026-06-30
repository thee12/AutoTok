"""Command-line interface for AutoTok."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from autotok import __version__
from autotok.config import AppConfig, ConfigError
from autotok.errors import AutoTokError, UserInputError
from autotok.ingestion import build_manual_file_record, build_manual_text_record
from autotok.logging import configure_logging
from autotok.models import StoryRecord
from autotok.script_models import NarrationScriptRecord
from autotok.script_storage import ScriptStore, StoredScript
from autotok.storage import StoredStory, StoryStore
from autotok.transform import DEFAULT_TARGET_SECONDS, DeterministicScriptTransformer


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

    script = subcommands.add_parser(
        "script",
        help="Inspect and approve reviewable narration scripts.",
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
    return parser


def run_doctor(args: argparse.Namespace) -> int:
    """Run the harmless diagnostic command."""
    config = _load_config(args)

    diagnostic = {
        "application": "autotok",
        "version": __version__,
        "environment": config.environment,
        "log_level": config.log_level,
        "data_dir": str(config.data_dir),
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
