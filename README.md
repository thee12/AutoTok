# AutoTok

AutoTok is a local-first, human-reviewed pipeline for creating short-form
vertical video packages from approved source stories. This repository is
currently complete through Phase 13, with persistent local jobs, a browser-based local review dashboard, local TikTok manual upload packages, local operations tooling, and local analytics feedback.

Reddit discovery is available only through authenticated official Data API configuration or local fixtures. Content gates are local filesystem artifacts. Phase 10 adds local review state and a localhost dashboard for generated render packages. Phase 11 now prepares approval-gated TikTok manual upload packages and local publication audit records without API publishing. Phase 12 adds health checks, metrics, backup/restore, retention, audits, profiling, JSON logs, and an operations runbook. Phase 13 adds local analytics records, experiment definitions, template variants, reports, and human-reviewed recommendations. No paid
provider calls are made by tests.

## Requirements

- Python 3.12 or newer
- FFmpeg's `ffmpeg` and `ffprobe` executables for real media imports and renders

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On macOS or Linux, activate the virtual environment with:

```bash
source .venv/bin/activate
```

## Commands

Run the harmless diagnostic command:

```bash
autotok doctor
```

Run local operational checks:

```bash
autotok ops health
autotok ops metrics --json
autotok ops audit
```

Track local analytics feedback and experiments:

```bash
autotok analytics template create --name "Fast hook" --hook "Wait until you hear this" --hashtag storytime
autotok analytics experiment create --name "Hook test" --hypothesis "A direct hook improves completion" --primary-metric completions --variant-id template_a --variant-id template_b
autotok analytics experiment assign experiment_0123456789abcdef template_0123456789abcdef render_0123456789abcdef
autotok analytics import render_0123456789abcdef --provider tiktok --source manual --metric views=1200 --metric completions=430
autotok analytics report --json
```

Import manually supplied story text:

```bash
autotok story import --text "A short approved story." --title "Optional title"
```

Import a local UTF-8 story file:

```bash
autotok story import --file path/to/story.txt
```

Inspect an imported story:

```bash
autotok story inspect story_0123456789abcdef
```

Discover approved public Reddit posts with live OAuth-backed API access:

```bash
autotok source discover reddit --subreddit AskReddit --sort hot --limit 10
```

Discover from a local Reddit listing fixture without network access:

```bash
autotok source discover reddit --subreddit autotok_test --fixture-json tests/fixtures/reddit_listing.json
```

Inspect a discovery run and import one discovered post as a canonical story:

```bash
autotok source inspect discovery_0123456789abcdef
autotok source import discovery_0123456789abcdef t3_example
```

Score a story, inspect its gate decision, or append a manual override:

```bash
autotok story assess story_0123456789abcdef
autotok story gate story_0123456789abcdef
autotok story override story_0123456789abcdef --decision approved --reason "Reviewed locally"
```

Transform an imported story into a reviewable narration script:

```bash
autotok story transform story_0123456789abcdef --target-seconds 60
```

Inspect and approve a generated script:

```bash
autotok script inspect script_0123456789abcdef
autotok script approve script_0123456789abcdef
```

Create validated narration audio for an approved script with the local WAV
provider:

```bash
autotok script narrate script_0123456789abcdef --provider local_wav
```

Use an existing local WAV file as manually supplied narration audio:

```bash
autotok script narrate script_0123456789abcdef --audio-file path/to/narration.wav
```

Inspect generated or imported narration audio:

```bash
autotok audio inspect audio_0123456789abcdef
```

Generate validated subtitles for a narration script and audio artifact:

```bash
autotok subtitle generate script_0123456789abcdef audio_0123456789abcdef --format srt
```

Generate subtitles from provider-supplied word timings:

```bash
autotok subtitle generate script_0123456789abcdef audio_0123456789abcdef --word-timings path/to/word-timings.json --format vtt
```

Inspect or export a subtitle artifact:

```bash
autotok subtitle inspect subtitle_0123456789abcdef
autotok subtitle export subtitle_0123456789abcdef --format ass
```

Catalog an authorized background media file:

```bash
autotok media import --file path/to/clip.mp4 --license-note "User-owned gameplay capture" --tag gameplay
```

Inspect cataloged background media and select a deterministic segment:

```bash
autotok media inspect media_0123456789abcdef
autotok media select --target-seconds 45 --orientation portrait --tag gameplay --seed 7
```

Render a validated local vertical video package:

```bash
autotok render create audio_0123456789abcdef subtitle_0123456789abcdef clip_0123456789abcdef
```

Inspect a completed render package:

```bash
autotok render inspect render_0123456789abcdef
```

Prepare a TikTok manual upload package for an approved review package:

```bash
autotok publish tiktok render_0123456789abcdef
```

Inspect or mark local manual publishing status:

```bash
autotok publish status render_0123456789abcdef
autotok publish mark render_0123456789abcdef --url https://www.tiktok.com/@you/video/123
```

Create and restore local data backups:

```bash
autotok ops backup --output backups/autotok-data.zip
autotok ops restore --archive backups/autotok-data.zip --target-data-dir restored-data --apply
```

Preview transient artifact retention cleanup:

```bash
autotok ops retention --older-than-days 30
```

Use a specific local artifact workspace:

```bash
autotok --data-dir data story import --file path/to/story.txt --json
```

Run all configured checks:

```bash
ruff check .
ruff format --check .
mypy .
pytest
```

Format code:

```bash
ruff format .
```

## Configuration

Copy `.env.example` to `.env` for local settings if needed. Real secrets must
not be committed.

Current environment variables:

- `AUTOTOK_ENV`, default `local`
- `AUTOTOK_LOG_LEVEL`, default `INFO`
- `AUTOTOK_LOG_FORMAT`, default `text`, set to `json` for structured operational logs
- `AUTOTOK_DATA_DIR`, default `data`
- `AUTOTOK_TTS_PROVIDER`, default `local_wav`
- `AUTOTOK_TTS_TIMEOUT_SECONDS`, default `30`
- `AUTOTOK_REDDIT_OAUTH_TOKEN`, optional bearer token for live Reddit Data API discovery
- `AUTOTOK_REDDIT_USER_AGENT`, default `AutoTok/0.1 local-source-ingestion`
- `AUTOTOK_REDDIT_TIMEOUT_SECONDS`, default `20`

The CLI `--data-dir` option overrides `AUTOTOK_DATA_DIR` for that command. Reddit secrets are never printed by the CLI; TikTok publishing is manual-only and does not require TikTok API secrets.

## Story Artifacts

Imported stories are stored under:

```text
data/sources/story_<hash-prefix>/
```

Each imported story directory contains:

- `record.json`, canonical metadata and text representation
- `original.txt`, the source text as supplied or read from the UTF-8 file
- `normalized.txt`, normalized story text used for stable IDs and hashes

Re-importing the same normalized story text is idempotent and returns the same
story ID.

## Source Discovery Artifacts

Approved public source discovery runs are stored under:

```text
data/source_discovery/discovery_<hash-prefix>/
```

Each discovery directory contains:

- `record.json`, filtered source-post metadata, query information, pagination state, rate-limit header snapshots, and source provenance
- `raw_pages/page_001.json`, raw listing response cache material for inspection and reproducibility

Live Reddit discovery uses the authenticated Reddit Data API configuration from environment variables and records rate-limit headers. Local fixture discovery uses `--fixture-json` and does not require credentials or network access. Phase 7 filters deleted, removed, empty, and age-restricted posts, keeps minimal provenance, and imports selected posts through the same `data/sources/story_<hash-prefix>/` store used by manual ingestion.

Raw live retrieval responses may also be cached under:

```text
data/cache/source_retrieval/reddit/
```

## Content Gate Artifacts

Story content gate records are stored under:

```text
data/content_gates/story_<hash-prefix>/
```

Each gate directory contains `record.json` with deterministic quality scoring,
exact and near-duplicate signals, normalized fingerprints, estimated narration
duration suitability, content warnings, reject reasons, review flags, and manual
override events. Discovered Reddit stories must have an approved effective gate
decision before `autotok story transform` will run. Manual stories can still be
transformed without a gate unless a stored gate exists and is not approved.

## Script Artifacts

Generated narration scripts are stored under:

```text
data/scripts/script_<hash-prefix>/
```

Each script directory contains:

- `record.json`, review status, section data, duration budget, privacy report,
  provider metadata, and transformation history
- `before.txt`, the normalized source story text used for transformation
- `script.txt`, the full hook/body/outro narration script

Scripts are created with `pending_review` status and must be approved before
Phase 3 narration audio can be produced or accepted.

## Audio Artifacts

Validated narration audio is stored under:

```text
data/audio/audio_<hash-prefix>/
```

Each audio directory contains:

- `record.json`, audio metadata, source/provider metadata, and request metadata
- `narration.wav`, the validated WAV PCM audio artifact

The `local_wav` provider is a credential-free local development provider that
creates deterministic valid WAV placeholder audio. Real speech-provider adapters
are deferred until explicitly selected in a later prompt.

## Subtitle Artifacts

Validated subtitle documents are stored under:

```text
data/subtitles/subtitle_<hash-prefix>/
```

Each subtitle directory contains:

- `record.json`, canonical subtitle cues, timing strategy metadata, readability
  settings, validation status, and script/audio provenance
- `subtitles.srt`, `subtitles.vtt`, or `subtitles.ass`, depending on the
  requested export format

Phase 4 supports provider word timings when supplied as JSON and an explicit
approximate fallback that distributes script words across the narration audio
duration. Subtitle generation validates the script/audio relationship, cue
timing, text readability constraints, and export format.

## Background Media Artifacts

Authorized background media records are stored under:

```text
data/media/media_<hash-prefix>/
```

Each media directory contains:

- `record.json`, FFprobe-derived video metadata, authorization/license notes,
  tags, source path, and content hash
- `source.<ext>`, the copied local media file

Prepared background clip selections are stored under:

```text
data/clips/clip_<hash-prefix>/
```

Each clip directory contains `record.json` with the selected media ID, target
segment duration, deterministic seed, start/end offsets, requested tags and
orientation, and recent media IDs avoided when possible.

Phase 5 does not trim or render media. It only catalogs authorized local clips
and prepares a segment record for the later composition phase.

## Render Artifacts

Validated render packages are stored under:

```text
data/renders/render_<hash-prefix>/
```

Each render directory contains:

- `render_spec.json`, the resolved audio, subtitle, media, clip, and output
  profile configuration
- `output.mp4`, a portrait MP4 composed with background video, narration audio,
  and burned-in subtitles
- `manifest.json`, output metadata, FFmpeg command arguments, artifact paths,
  status, and provenance IDs
- `work/subtitles.ass`, the subtitle file passed to FFmpeg for rendering

Phase 6 completes the first local MVP. The output is saved for human review.
Phase 7 adds approved public source discovery and import. Phase 8 adds local
scoring, duplicate detection, review flags, and content gates before discovered
stories enter transformation. Phase 9 adds persistent local jobs and resumable
story-to-render orchestration. Phase 10 adds a localhost review dashboard. Phase 11 adds approval-gated official publishing support for TikTok. Phase 12 adds local operations tooling. Phase 13 adds local analytics feedback, experiments, and reusable template variants. AutoTok still does not automate engagement, unsupported scheduling, or analytics collection from providers.

## Persistent Jobs

Phase 9 stores job state in `data/jobs.sqlite3` and writes job manifests under
`data/jobs/<job_id>/manifest.json`. Jobs track stages, attempts, artifact
references, statuses, retry failures, and resumable progress.

Useful commands:

- `autotok job create --story-id <story_id>` queues one or more story jobs.
- `autotok job run <job_id>` runs or resumes a story-to-render job.
- `autotok job run-batch <batch_id> --limit <n>` runs a bounded serial batch.
- `autotok job inspect <job_id>` inspects stages, attempts, and artifacts.
- `autotok job cleanup` previews retention cleanup; pass `--apply` to delete
  matching job records and job manifests without deleting generated media.


## Local Review Dashboard

Phase 10 stores review packages under `data/reviews/<render_id>/review.json` and
serves a local browser dashboard with:

- render queue discovery from `data/renders/`
- video preview from the local rendered MP4
- editable script and export metadata snapshots
- approve, reject, and regeneration-request controls
- append-only local audit history
- JSON API routes for the same review state used by the UI

Start the dashboard with:

```powershell
autotok review serve
```

Then open `http://127.0.0.1:8765/`. The review dashboard is local-only and does
not publish, schedule, upload, or contact platform APIs.

## Publication Artifacts

Phase 11 stores publication records under:

```text
data/publications/<render_id>/tiktok/publication.json
```

TikTok publishing is manual-only. AutoTok prepares a local `manual_upload` package with `video.mp4`, `caption.txt`, `metadata.json`, and `instructions.md`; the operator uploads and publishes from their own TikTok account. AutoTok does not request TikTok scopes, store TikTok API credentials, call Direct Post, schedule posts, or automate other platforms. See `docs/PUBLISHING.md`.

## Analytics Artifacts

Phase 13 stores local analytics feedback under:

```text
data/analytics/
```

Analytics records include template variants, experiment definitions, render assignments, and manually supplied or officially exported performance records. Reports summarize recorded outcomes and produce human-reviewed recommendations only. Phase 13 does not scrape analytics dashboards, manipulate engagement, guarantee growth, or automatically change content or publishing behavior. See `docs/ANALYTICS.md`.

## Operations

Phase 12 keeps deployment local-first: install the Python package into an isolated environment on the machine that owns the media and data directory. It adds:

- `autotok ops health` for local health checks
- `autotok ops metrics` for artifact, job, review, publication, and analytics counts
- `autotok ops backup` and `autotok ops restore` for ZIP-based data recovery
- `autotok ops retention` for dry-run-first cleanup of transient cache/log/tmp files
- `autotok ops audit` for dependency inventory and high-confidence secret scanning
- `autotok ops profile` for a lightweight local performance baseline
- `AUTOTOK_LOG_FORMAT=json` for structured logs

See `docs/OPERATIONS.md` for install, monitoring, backup, restore, retention, audit, profiling, recovery, and upgrade procedures.

## Documentation

- `docs/ARCHITECTURE.md`
- `docs/PHASES.md`
- `docs/STATUS.md`
- `docs/PUBLISHING.md`
- `docs/OPERATIONS.md`
- `docs/ANALYTICS.md`
