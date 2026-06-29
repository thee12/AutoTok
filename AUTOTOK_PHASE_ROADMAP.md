# AutoTok Phase Roadmap

## Development strategy

Each phase receives a separate, highly specific Codex prompt. Codex must finish, test, document, and report on that phase before receiving the next prompt.

The first usable local MVP is complete after Phase 6. Phases 7–13 extend the MVP into an automated content-discovery, review, publishing, and operational platform.

---

## Phase 0 — Repository bootstrap and architecture

**Goal:** Turn the repository containing only `AGENTS.md` into a clean, runnable Python project foundation.

**Deliverables:**
- Python project configuration and dependency strategy
- initial package layout selected by Codex
- CLI entry point with a harmless diagnostic command
- configuration model and `.env.example`
- logging foundation
- custom exception hierarchy
- test, lint, format, and type-check setup
- README and architecture documentation
- `docs/PHASES.md` and current-status documentation
- Git ignore rules
- development commands
- CI workflow if appropriate for the repository

**Excluded:** Real story processing, AI calls, audio, subtitles, FFmpeg rendering, Reddit, database, UI, and publishing.

**Exit gate:** A fresh developer can install the project, run the CLI, and execute all configured checks.

---

## Phase 1 — Manual story ingestion and canonical models

**Goal:** Accept a local text story and turn it into a validated internal source record.

**Deliverables:**
- manual text and file ingestion
- canonical source/story models
- UTF-8 normalization
- content hashing and stable IDs
- source preservation
- filesystem artifact workspace
- CLI commands for import and inspection
- invalid-input handling
- unit and integration tests

**Excluded:** LLM rewriting, TTS, subtitles, video, Reddit, database, UI, publishing.

**Exit gate:** A local story can be imported repeatably, inspected, and represented by validated metadata without modifying the source.

---

## Phase 2 — Script transformation and review artifacts

**Goal:** Convert an imported story into a narration-ready script while preserving provenance and requiring review.

**Deliverables:**
- deterministic baseline cleaner
- privacy-cleaning rules
- hook/body/outro structure
- target-duration budgeting
- provider-independent transformation interface
- optional AI adapter only when credentials are configured
- before/after artifacts and transformation metadata
- review status
- CLI commands for transform, inspect, and approve
- tests using fake providers

**Excluded:** Real narration generation, subtitle timing, video, Reddit, UI, publishing.

**Exit gate:** An imported story can produce a reviewable narration script with transformation history and duration estimate.

---

## Phase 3 — Narration audio

**Goal:** Produce validated narration audio from an approved script.

**Deliverables:**
- provider-independent TTS interface
- manually supplied audio path
- one explicitly selected TTS provider
- credential-safe configuration
- request timeouts and error mapping
- deterministic fake provider
- audio probing and validation
- audio metadata
- optional normalization
- CLI narration command
- paid calls disabled in tests

**Excluded:** Subtitles, gameplay, final video, Reddit, UI, publishing.

**Exit gate:** An approved script can produce or accept a validated narration audio artifact.

---

## Phase 4 — Subtitle generation and alignment

**Goal:** Produce accurate, readable subtitle artifacts synchronized to narration.

**Deliverables:**
- canonical subtitle document model
- timing strategy hierarchy
- use of provider word timing when available
- fallback alignment/transcription strategy
- explicit approximate fallback if necessary
- line breaking and readability rules
- SRT/VTT/ASS export as selected
- subtitle validation
- CLI subtitle command
- timing fixtures and tests

**Excluded:** Background video and final composition.

**Exit gate:** Narration audio and script produce a validated subtitle document that can be previewed or exported.

---

## Phase 5 — Background-media library

**Goal:** Manage authorized gameplay or background clips and select a suitable segment.

**Deliverables:**
- media import/catalog command
- FFprobe-based metadata extraction
- license/usage-note support
- invalid-media detection
- tags
- deterministic selection with seed
- duration and orientation filtering
- start-offset selection
- recent-use avoidance design
- clip preparation artifact
- compact synthetic media fixtures

**Excluded:** Final video composition, Reddit, publishing.

**Exit gate:** AutoTok can catalog authorized clips and deterministically select a valid segment for a target narration duration.

---

## Phase 6 — End-to-end vertical video rendering

**Goal:** Complete the first local MVP by producing a validated vertical video package.

**Deliverables:**
- render specification
- FFmpeg composition pipeline
- portrait crop/scale policy
- narration audio mix
- burned-in subtitles
- optional authorized music with ducking if included in scope
- output profile configuration
- per-run work directories
- post-render probing and validation
- manifest
- end-to-end CLI command
- small end-to-end test
- manual review instructions

**Excluded:** Reddit, automated discovery, web dashboard, posting.

**Exit gate:** One command can transform approved local inputs into a validated, reviewable short-form video package.

---

## Phase 7 — Approved Reddit and source ingestion

**Goal:** Add automated discovery from approved public sources without coupling source access to the rendering pipeline.

**Deliverables:**
- source-adapter interface
- official Reddit/API or approved feed integration chosen at implementation time
- authentication and configuration
- pagination and rate-limit handling
- filtering for deleted/removed/empty content
- source provenance
- retrieval cache
- fixture-based tests
- CLI discovery/import commands

**Excluded:** Automated publication and engagement automation.

**Exit gate:** Approved source posts can be discovered and imported as the same canonical source records used by manual ingestion.

---

## Phase 8 — Scoring, deduplication, and content gates

**Goal:** Prevent low-quality, repeated, sensitive, or unsuitable stories from automatically entering production.

**Deliverables:**
- exact duplicate detection
- normalized-content fingerprints
- near-duplicate strategy
- configurable quality scoring
- duration suitability
- content warnings and reject reasons
- policy and privacy review flags
- manual override trail
- tests for scoring and duplicate scenarios

**Exit gate:** Every discovered story receives a reproducible decision and explanation before transformation.

---

## Phase 9 — Persistent orchestration and batch generation

**Goal:** Turn isolated commands into resumable, traceable jobs.

**Deliverables:**
- SQLite persistence
- jobs, stages, artifacts, attempts, and statuses
- idempotent stage execution
- retries for transient failures
- resume from failed stage
- batch limits
- concurrency controls appropriate for local execution
- run manifests
- cleanup and retention commands
- crash-recovery tests

**Exit gate:** A batch can be interrupted and safely resumed without duplicating completed work.

---

## Phase 10 — Local review dashboard

**Goal:** Provide a browser-based local interface for reviewing generated stories, scripts, audio, subtitles, videos, and metadata.

**Deliverables:**
- local backend/API
- focused review UI
- preview playback
- script and metadata editing
- approval/rejection states
- regenerate-stage controls
- audit history
- accessible error displays
- no duplicated business logic in UI
- tests for state transitions and key API routes

**Exit gate:** A user can review and approve an export package without editing files manually.

---

## Phase 11 — Official publishing and scheduling

**Goal:** Publish approved content through an official, supported platform integration.

**Deliverables:**
- publishing-adapter interface
- platform capability verification from official docs
- OAuth/token lifecycle
- secure secret storage approach
- dry run
- upload/publish status
- idempotency and duplicate prevention
- scheduling only where officially supported
- failure recovery
- explicit approval gate
- audit record

**Exit gate:** An approved package can be published or scheduled through the selected official integration without duplicate posting.

---

## Phase 12 — Production hardening and deployment

**Goal:** Make the system maintainable for regular use.

**Deliverables:**
- deployment packaging selected from actual needs
- health checks
- structured operational logs
- metrics
- backup and restore for persistent state
- artifact-retention policies
- performance profiling
- dependency and security scanning
- operational runbook
- recovery procedures
- upgrade/migration process

**Exit gate:** The deployment can be installed, monitored, backed up, restored, and upgraded using documented procedures.

---

## Phase 13 — Optional analytics and advanced templates

**Goal:** Improve the workflow using measured results rather than assumptions.

**Possible deliverables:**
- approved analytics ingestion
- content-performance records
- experiment definitions
- template variants
- subtitle-theme variants
- hook variants
- provider cost tracking
- quality and throughput reports
- human-reviewed recommendations

**Excluded:** Fake engagement, bot interactions, or guaranteed-growth claims.

**Exit gate:** Changes can be evaluated against recorded outcomes without compromising review, authorization, or platform compliance.

---

## Prompt sequence

Prompts should be delivered in this order:

1. Phase 0 implementation prompt
2. Phase 0 verification/remediation prompt if needed
3. Phase 1 implementation prompt
4. Phase 1 verification/remediation prompt if needed
5. Continue one phase at a time

Every phase prompt should contain:

- objective
- repository context
- exact in-scope requirements
- exclusions
- architecture constraints
- expected user-facing commands
- expected data models and behaviors
- error cases
- testing requirements
- documentation requirements
- acceptance checklist
- required final report format
- explicit instruction to stop after the phase
