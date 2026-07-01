# AutoTok Status

## Current Phase

Phase 13 - Optional analytics feedback, experiments, and advanced templates (complete).

## Implemented

- Python package metadata in `pyproject.toml`
- `src/autotok` package layout
- `autotok doctor` diagnostic CLI command
- environment-backed configuration model with CLI `--data-dir` override
- credential-safe local TTS provider and timeout configuration
- standard-library logging setup
- application exception hierarchy
- canonical story/source dataclasses
- deterministic text normalization and content hashing
- stable story IDs derived from normalized content
- manual text import through `autotok story import --text`
- UTF-8 file import through `autotok story import --file`
- idempotent filesystem story storage under `data/sources/`
- story inspection through `autotok story inspect`
- canonical narration script and review dataclasses
- provider-independent script transformation interface
- deterministic local transformer with privacy redaction and duration budgeting
- fake script transformer test double
- script artifacts under `data/scripts/`
- script inspection and approval through `autotok script inspect` and
  `autotok script approve`
- canonical narration audio dataclasses
- provider-independent TTS interface
- local WAV provider for credential-free generated audio
- manually supplied WAV audio path
- fake TTS provider test double
- WAV PCM probing, validation, metadata, and hashing
- narration audio artifacts under `data/audio/`
- narration and audio inspection through `autotok script narrate` and
  `autotok audio inspect`
- canonical subtitle document dataclasses
- provider word-timing and approximate audio-duration timing strategies
- subtitle readability validation and cue timing validation
- SRT, VTT, and ASS subtitle exports
- subtitle artifacts under `data/subtitles/`
- subtitle generation, inspection, and export through
  `autotok subtitle generate`, `autotok subtitle inspect`, and
  `autotok subtitle export`
- canonical background-media and clip-preparation dataclasses
- ffprobe-backed video metadata probing and invalid-media handling
- authorization/license notes, usage notes, and tags for cataloged media
- background media artifacts under `data/media/`
- deterministic clip-preparation artifacts under `data/clips/`
- duration, orientation, tag, seed, start-offset, and recent-use-aware selection
- background media import, inspection, and selection through
  `autotok media import`, `autotok media inspect`, and `autotok media select`
- canonical render profile, render specification, output metadata, and manifest
  dataclasses
- FFmpeg command construction for portrait crop/scale, burned-in ASS subtitles,
  and narration audio mixing
- rendered output probing and validation for portrait dimensions, duration,
  audio stream presence, and non-empty output
- render packages under `data/renders/`
- render creation and inspection through `autotok render create` and
  `autotok render inspect`
- source discovery interface and Reddit Data API adapter
- live Reddit source discovery using OAuth bearer token configuration,
  descriptive User-Agent headers, timeouts, pagination, local raw retrieval
  cache entries, and rate-limit header capture
- local Reddit listing fixture discovery for credential-free tests and smoke
  runs
- filtering for deleted, removed, empty, and age-restricted Reddit posts
- minimal source provenance for discovered posts without storing author
  identifiers
- source discovery artifacts under `data/source_discovery/`
- raw source retrieval cache under `data/cache/source_retrieval/reddit/`
- discovered-post import into the same canonical `data/sources/` story records
  used by manual ingestion
- source discovery, inspection, and import through `autotok source discover
  reddit`, `autotok source inspect`, and `autotok source import`
- deterministic content gate dataclasses and local scoring rules
- exact duplicate detection using content hashes
- near-duplicate detection using token-set similarity
- normalized-content and token fingerprints for gate records
- quality scoring with length, structure, readability, originality, and safety
  components
- duration suitability checks for story length
- privacy and policy content warnings with review/reject severities
- reject reasons and review flags for every assessed story
- manual override trail with reviewer, reason, decision, and timestamp
- content gate artifacts under `data/content_gates/`
- content gate assessment, inspection, and override through `autotok story
  assess`, `autotok story gate`, and `autotok story override`
- transform-time gate enforcement for discovered Reddit stories
- SQLite-backed persistent jobs under `data/jobs.sqlite3`
- persistent job, stage, attempt, and artifact dataclasses
- job/stage status updates, attempt tracking, artifact references, deterministic ordered queries, and job deletion
- resumable story-to-render orchestration with idempotent stage skipping
- retry limits for failed stages and stale running-attempt recovery before resume
- job manifests under `data/jobs/<job_id>/manifest.json`
- batch job creation, bounded serial `run-batch` execution, and local no-worker concurrency boundary
- safe job cleanup/retention with dry-run default and explicit `--apply`
- job creation, listing, inspection, run, resume, batch-run, and cleanup through `autotok job ...`
- local review package state under `data/reviews/<render_id>/review.json`
- editable review script and export metadata snapshots
- review approval, rejection, and regeneration-request states
- append-only local review audit history
- localhost review API and static browser dashboard
- local rendered-video preview through the dashboard media route
- review dashboard serving through `autotok review serve`
- review listing and inspection through `autotok review list` and `autotok review inspect`
- TikTok Content Posting API capability verification from official documentation
- publication domain models, adapter interface, and filesystem publication records under `data/publications/`
- approval-gated TikTok dry runs and explicit `--execute --confirm` real publish path
- official TikTok Direct Post request building for file upload and pull-from-URL modes
- upload initialization, local file upload, provider status fetch, status mapping, and retryable failure surface
- duplicate prevention for submitted, processing, and published render/provider pairs
- OAuth authorization-code and refresh-token request helpers with redacted output
- secure secret configuration through environment variables only
- scheduling rejection for TikTok Direct Post because official support was not verified
- publication audit trail and CLI commands through `autotok publish ...`
- structured JSON log format via `AUTOTOK_LOG_FORMAT=json`
- local operational health checks through `autotok ops health`
- artifact, job, review, publication, and analytics metrics through `autotok ops metrics`
- ZIP data-directory backups through `autotok ops backup`
- safe backup inspection and empty-target restore through `autotok ops restore`
- dry-run-first transient cache/log/tmp retention through `autotok ops retention`
- dependency inventory, ignore-pattern check, and high-confidence secret scan through `autotok ops audit`
- lightweight metrics snapshot profiling through `autotok ops profile`
- operations runbook covering install, monitoring, backup, restore, retention, audit, profiling, recovery, and upgrade
- local analytics template variants for hooks, outros, captions, hashtags, subtitle-theme labels, and metadata
- local experiment definitions with hypotheses, primary metrics, variant IDs, statuses, and notes
- render-to-experiment assignment records for completed render packages
- manual and official-export performance record import for completed renders
- analytics artifacts under `data/analytics/`
- analytics reports with metric totals, averages, experiment summaries, leading variants, and recommendations
- human-reviewed recommendation output that does not change content or publishing automatically
- analytics CLI commands through `autotok analytics template`, `autotok analytics experiment`, `autotok analytics import`, and `autotok analytics report`
- analytics documentation covering scope, exclusions, commands, runtime data, and recommendation boundaries
- pytest, ruff, and mypy configuration
- README, architecture documentation, and phase roadmap
- local runtime-data ignore rules
- GitHub Actions CI workflow

## Not Implemented

The repository does not schedule posts, run distributed workers, execute jobs in parallel, scrape analytics dashboards, automate engagement, guarantee growth, or automatically change content from metric results. TikTok publishing exists only through the official Content Posting API and requires explicit approval, credentials, `--execute`, and `--confirm`. Phase 12 operations are local-first and do not introduce a hosted deployment service. Phase 13 analytics ingestion is limited to manually supplied or officially exported records. AutoTok also does not call real paid/cloud TTS or transcription providers.

## Phase 13 Completion Evidence

Phase 13 adds local analytics template variants, experiments, render assignments, performance records, reports, and human-reviewed recommendations. Focused tests cover template creation, experiment creation, render assignment idempotency and mismatch rejection, metric import, report recommendations, metric parsing, and CLI smoke paths. Full verification passed with ruff, format, mypy, and pytest checks.
