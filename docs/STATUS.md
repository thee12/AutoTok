# AutoTok Status

## Current Phase

Phase 9 - Persistent orchestration and batch generation (complete).

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
- pytest, ruff, and mypy configuration
- README, architecture documentation, and phase roadmap
- local runtime-data ignore rules
- GitHub Actions CI workflow

## Not Implemented

The repository does not yet provide a UI, publish content, schedule posts, run distributed workers, execute jobs in parallel, or automate engagement. It also does not call real paid/cloud TTS or transcription providers.

## Phase 9 Completion Evidence

Phase 9 adds a SQLite-backed `JobStore`, resumable local job runner, story-to-render stage definitions, batch creation and serial batch execution, retry limits, stale running-attempt recovery, manifest writing, and safe cleanup/retention. Focused tests cover storage initialization and updates, resume without rerunning successful stages, crash recovery, max-attempt failure, cleanup dry-run/apply behavior, full job CLI execution through fake FFmpeg/FFprobe, and batch run limits. Full verification passed with 88 tests.
