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
- explicit local WAV provider for credential-free placeholder audio
- pyttsx3 provider for no-cost offline spoken narration with system voices
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

## Phase 7 - Approved Reddit and Source Ingestion

Goal: add automated discovery from approved public sources without coupling source
access to the rendering pipeline.

Status: complete.

In scope:

- source-adapter interface
- authenticated Reddit Data API adapter selected for live source access
- local fixture discovery path for credential-free development and tests
- Reddit OAuth token, User-Agent, and timeout configuration
- pagination through listing cursors
- rate-limit header capture and no rate-limit bypassing
- filtering for deleted, removed, empty, and age-restricted posts
- minimal source provenance without author identifier retention
- source discovery records under `data/source_discovery/`
- raw live retrieval cache under `data/cache/source_retrieval/reddit/`
- CLI commands for discovery, inspection, and import
- fixture-based unit and CLI tests

Excluded:

- automated publication
- engagement automation
- scoring, deduplication, and content gates
- persistent jobs or batch orchestration
- review UI
- scraping private, deleted, age-restricted, or access-controlled content

Exit gate: approved source posts can be discovered and imported as the same
canonical source records used by manual ingestion.

## Phase 8 - Scoring, Deduplication, and Content Gates

Goal: prevent low-quality, repeated, sensitive, or unsuitable stories from
automatically entering production.

Status: complete.

In scope:

- exact duplicate detection using content hashes
- normalized-content and token fingerprints
- near-duplicate detection using token-set similarity
- configurable deterministic quality scoring
- duration suitability checks
- content warnings, reject reasons, and review flags
- policy and privacy review flags
- manual override trail
- filesystem content gate artifacts under `data/content_gates/`
- CLI commands for assessment, inspection, and override
- transform-time enforcement for discovered Reddit stories
- tests for scoring, duplicate scenarios, CLI behavior, and gate enforcement

Excluded:

- persistent jobs or batch orchestration
- database persistence
- review dashboard or UI
- automated publishing or scheduling
- automated engagement
- analytics feedback

Exit gate: every assessed story receives a reproducible decision and explanation
before transformation.

## Phase 9 - Persistent Orchestration and Batch Generation

Goal: turn isolated local commands into resumable, traceable jobs.

Status: complete.

In scope:

- SQLite schema initialization and version check
- persistent job, stage, attempt, and artifact dataclasses
- local job store create/load/list/update/delete operations
- deterministic insertion-order listing for jobs, stages, and artifacts
- idempotent ordered stage execution that skips already successful stages
- retries for failed stages up to a local attempt limit
- stale running-attempt recovery before resume
- story-to-render orchestration using the existing local Phase 1-6 components
- batch job creation with limits and serial `run-batch` execution
- local concurrency boundary: one serial runner per command invocation, no worker pool
- run manifests under `data/jobs/<job_id>/manifest.json`
- safe cleanup/retention command with dry-run default and explicit `--apply`
- CLI commands for job creation, listing, inspection, run, resume, batch run, and cleanup
- focused storage, orchestration, crash-recovery, cleanup, and CLI tests

Excluded:

- review dashboard or UI
- distributed queues, background workers, or parallel execution
- publishing, scheduling, or engagement automation
- analytics feedback

Exit gate: a batch can be interrupted and safely resumed without duplicating completed work.

## Phase 10 - Local Review Dashboard

Goal: provide a browser-based local interface for reviewing generated stories,
scripts, audio, subtitles, videos, and metadata.

Status: complete.

In scope:

- localhost backend/API using the Python standard library
- focused browser review UI served by `autotok review serve`
- review package discovery from completed render outputs
- local video preview for rendered MP4 packages
- editable script and export metadata snapshots
- approve, reject, and regeneration-request states
- append-only audit history for review actions
- CLI access through `autotok review list` and `autotok review inspect`
- route and state-transition tests

Excluded:

- publishing, uploading, or scheduling
- platform credentials or OAuth
- analytics feedback
- distributed review server deployment
- replacing existing pipeline business logic in the UI

Exit gate: a user can review and approve an export package without editing files manually.

## Phase 11 - Manual TikTok Publishing Handoff

Goal: prepare approved content for manual TikTok publishing without platform API access.

Status: complete.

In scope:

- TikTok manual upload package generation
- approved review package requirement
- copied rendered video, caption, metadata, and instructions files
- local publication records and audit events
- manual status recording after the operator publishes
- explicit exclusion of API publishing, OAuth, scopes, app review, and other platforms

Excluded:

- TikTok Login Kit, Content Posting API, Direct Post, or API credentials
- YouTube, Shorts, Instagram, or other sites
- browser automation or autonomous posting
- unsupported scheduling
- engagement automation
- analytics feedback

Exit gate: an approved package can be prepared locally, handed to the operator, and marked manually published after the operator posts it on TikTok.

## Phase 12 - Production Hardening and Deployment

Goal: make the system maintainable for regular local use.

Status: complete.

In scope:

- local Python package deployment guidance
- structured JSON logs
- operational health checks
- local metrics snapshots
- ZIP backup and safe restore
- transient artifact-retention policy
- dependency inventory and high-confidence secret scanning
- lightweight performance profiling
- operations runbook
- recovery and upgrade procedures

Excluded:

- hosted service deployment
- distributed workers
- parallel job execution
- analytics feedback
- advanced templates

Exit gate: the local deployment can be installed, monitored, backed up, restored, and upgraded using documented procedures.

## Phase 13 - Optional Analytics Feedback and Advanced Templates

Goal: improve the workflow using measured local results rather than assumptions.

Status: complete.

In scope:

- local analytics template variants for hooks, outros, caption templates,
  hashtags, subtitle-theme labels, and metadata
- local experiment definitions with hypotheses, primary metrics, variant IDs,
  statuses, and notes
- assignments linking completed render packages to experiment template variants
- manually supplied or officially exported performance records
- local reports with totals, averages, experiment summaries, leading variants,
  and recommendations
- human-reviewed recommendations that never modify content or publishing
  automatically
- CLI commands for template variants, experiments, metric import, and reports
- tests for analytics models, storage, reporting, assignment safety, metric
  parsing, and CLI behavior
- documentation for commands, runtime data, and scope boundaries

Excluded:

- fake engagement or engagement manipulation
- automated comments, messages, follows, likes, or bot interactions
- scraping analytics dashboards or bypassing platform controls
- automatic analytics-provider API integration
- automatic content, template, review, publication, or scheduling changes based
  on metrics
- guaranteed-growth claims

Exit gate: changes can be evaluated against recorded outcomes without compromising review, authorization, or platform compliance.
