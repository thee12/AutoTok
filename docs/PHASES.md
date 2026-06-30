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

Status: complete.

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

## Phase 3 - Narration Audio

Goal: produce validated narration audio from an approved script.

Status: complete.

In scope:

- provider-independent TTS interface
- manually supplied WAV narration audio path
- explicit local WAV provider for credential-free development
- credential-safe TTS provider and timeout configuration
- timeout validation and provider error mapping
- deterministic fake provider for tests
- WAV PCM probing and validation
- audio metadata and content hashing
- idempotent audio artifact storage under `data/audio/`
- CLI narration command and audio inspection command
- tests that do not make paid calls

Excluded:

- subtitles
- transcription or alignment
- background media
- final video rendering
- Reddit or automated source ingestion
- review UI
- publishing
- real paid/cloud TTS calls

Exit gate: an approved script can produce or accept a validated narration audio
artifact.

## Phase 4 - Subtitle Generation and Alignment

Goal: produce accurate, readable subtitle artifacts synchronized to narration.

Status: complete.

In scope:

- canonical subtitle document dataclasses
- provider word-timing strategy using supplied timing fixtures
- explicit approximate fallback alignment based on narration audio duration
- line breaking and readability rules
- subtitle timing and cue validation
- SRT, VTT, and ASS exports
- subtitle artifact storage under `data/subtitles/`
- CLI commands for subtitle generation, inspection, and export
- timing fixtures and tests

Excluded:

- background-media selection
- final video composition
- burned-in subtitle rendering
- Reddit or automated source ingestion
- review UI
- publishing
- real transcription-provider calls

Exit gate: narration audio and script produce a validated subtitle document that
can be inspected and exported.

## Phase 5 - Background-Media Library

Goal: manage authorized gameplay or background clips and select a suitable
segment.

Status: complete.

In scope:

- media import/catalog command
- ffprobe-based metadata extraction
- license and usage-note support
- invalid media detection
- tags
- deterministic selection with seed
- duration and orientation filtering
- start-offset selection
- recent-use avoidance design
- clip-preparation artifacts under `data/clips/`
- compact synthetic media fixtures for tests

Excluded:

- final video composition
- actual clip trimming
- burned-in subtitle rendering
- Reddit or automated source ingestion
- review UI
- publishing

Exit gate: AutoTok can catalog authorized clips and deterministically select a
valid segment for a target narration duration.

## Phase 6 - End-to-End Vertical Video Rendering

Goal: complete the first local MVP by producing a validated vertical video
package.

Status: complete.

In scope:

- render specification
- FFmpeg composition pipeline
- portrait crop/scale policy
- narration audio mix
- burned-in subtitles
- output profile configuration
- per-render work directories
- post-render probing and validation
- render manifest
- CLI commands for render creation and inspection
- small end-to-end CLI test with synthetic media and fake FFmpeg/FFprobe
- manual review instructions in project documentation

Excluded:

- Reddit or automated source ingestion
- automated discovery
- web dashboard
- posting or scheduling
- persistent job orchestration
- analytics

Exit gate: one command can transform approved local inputs into a validated,
reviewable short-form video package.

## Later Phases

Phase 7: approved Reddit and source ingestion.

Phase 8: scoring, deduplication, and content gates.

Phase 9: persistent orchestration and batch generation.

Phase 10: local review dashboard.

Phase 11: official publishing and scheduling.

Phase 12: production hardening and deployment.

Phase 13: optional analytics and advanced templates.
