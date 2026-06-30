# AutoTok Phases

This document is the canonical phase roadmap after Phase 0. Each phase must be
implemented, tested, documented, and reported before the next phase begins.

## Phase 0 - Repository Bootstrap and Architecture

Goal: turn the initial repository into a clean, runnable Python project
foundation.

Status: complete.

In scope:

- Python project configuration and dependency strategy
- `src/` package layout
- harmless CLI diagnostic command
- configuration model and `.env.example`
- logging foundation
- custom exception hierarchy
- test, lint, format, and type-check setup
- README, architecture, and status documentation
- Git ignore rules
- development commands
- CI workflow

Excluded:

- story processing
- AI calls
- audio
- subtitles
- FFmpeg rendering
- Reddit/source ingestion
- database
- UI
- publishing

Exit gate: a fresh developer can install the project, run the CLI, and execute
all configured checks.

## Phase 1 - Manual Story Ingestion and Canonical Models

Goal: accept a local text story and turn it into a validated internal source
record.

Status: complete.

In scope:

- manual text ingestion from `--text`
- UTF-8 local text file ingestion from `--file`
- canonical source/story dataclasses
- Unicode normalization, line-ending normalization, and unsupported control
  character sanitization
- SHA-256 content hashing and stable `story_<hash-prefix>` IDs
- source preservation in local filesystem artifacts
- filesystem artifact workspace under `data/sources/`
- CLI commands for import and inspection
- invalid-input handling for empty text, missing files, invalid UTF-8 files, and
  invalid story IDs
- unit and integration tests

Excluded:

- LLM rewriting
- TTS or manually supplied narration audio
- subtitles
- video rendering
- Reddit or automated source ingestion
- database persistence
- UI
- publishing

Exit gate: a local story can be imported repeatably, inspected, and represented
by validated metadata without modifying the source.

## Phase 2 - Script Transformation and Review Artifacts

Goal: convert an imported story into a narration-ready script while preserving
provenance and requiring review.

Status: implemented in this working tree.

In scope:

- deterministic baseline cleaner
- privacy-cleaning rules for common contact details
- hook/body/outro script structure
- target-duration budgeting and estimated narration duration
- provider-independent transformation interface
- deterministic provider and fake provider test double
- before/after artifacts and transformation metadata
- pending-review and approved script statuses
- CLI commands for transform, inspect, and approve
- tests using deterministic and fake providers

Excluded:

- real narration generation
- subtitle timing
- video rendering
- Reddit or automated source ingestion
- review UI
- publishing
- real external AI calls

Exit gate: an imported story can produce a reviewable narration script with
transformation history and duration estimate.

## Later Phases

Phase 3: narration audio.

Phase 4: subtitle generation and alignment.

Phase 5: background-media library.

Phase 6: end-to-end vertical video rendering for the first local MVP.

Phase 7: approved Reddit and source ingestion.

Phase 8: scoring, deduplication, and content gates.

Phase 9: persistent orchestration and batch generation.

Phase 10: local review dashboard.

Phase 11: official publishing and scheduling.

Phase 12: production hardening and deployment.

Phase 13: optional analytics and advanced templates.
