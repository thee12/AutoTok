# AutoTok Architecture

AutoTok is being built as a local-first modular monolith. Phase 12 adds local-first operations tooling while keeping rendering, review state, approvals, publication audit records, backups, and metrics on the operator machine.

## Current Shape

- `src/autotok/cli.py` exposes the `autotok` command.
- `autotok doctor` validates local configuration and prints a diagnostic summary.
- `autotok story import` imports manually supplied text or a local UTF-8 file.
- `autotok story inspect` loads and summarizes a stored story record.
- `autotok source discover reddit` discovers approved public Reddit posts through authenticated Data API access or a local listing fixture.
- `autotok source inspect` loads and summarizes a stored source discovery run.
- `autotok source import` imports one discovered post as a canonical story record.
- `autotok story assess` writes a deterministic content gate decision for a story.
- `autotok story gate` inspects a stored content gate decision.
- `autotok story override` appends a manual override event to the gate trail.
- `autotok story transform` creates a reviewable narration script from a story.
- `autotok script inspect` loads and summarizes a generated script record.
- `autotok script approve` marks a generated script approved for later phases.
- `autotok script narrate` creates or imports validated narration audio for an
  approved script.
- `autotok audio inspect` loads and summarizes a narration audio record.
- `autotok subtitle generate` creates a validated subtitle document from an
  approved script and matching narration audio.
- `autotok subtitle inspect` loads and summarizes a stored subtitle document.
- `autotok subtitle export` exports an existing subtitle document as SRT, VTT,
  or ASS.
- `autotok media import` catalogs an authorized local video file using ffprobe
  metadata, license notes, and tags.
- `autotok media inspect` loads and summarizes a cataloged media record.
- `autotok media select` creates a deterministic clip-preparation artifact for a
  target duration.
- `autotok render create` composes background media, narration audio, and
  burned-in subtitles into a validated portrait MP4 package.
- `autotok render inspect` loads and summarizes a completed render manifest.
- `autotok job create`, `job run`, `job resume`, `job run-batch`, `job inspect`,
  `job list`, and `job cleanup` manage persistent resumable local jobs.
- `autotok review serve` starts the local browser dashboard.
- `autotok review list` and `autotok review inspect` expose review state without
  opening a browser.
- `autotok publish tiktok` prepares a dry run or explicitly executes an approved TikTok Direct Post publish.
- `autotok publish status` inspects local publication state or fetches official TikTok status.
- `autotok publish token exchange` and `autotok publish token refresh` build or execute redacted OAuth token lifecycle requests.
- `autotok ops health`, `metrics`, `backup`, `restore`, `retention`, `audit`, and `profile` provide local operational hardening commands.
- `src/autotok/config.py` contains the initial configuration model.
- `src/autotok/models.py` contains canonical story/source dataclasses.
- `src/autotok/content_gate_models.py` contains scoring, duplicate, warning, decision, and override dataclasses.
- `src/autotok/content_gates.py` contains deterministic local scoring and gate rules.
- `src/autotok/content_gate_storage.py` persists content gate artifacts.
- `src/autotok/job_models.py` contains persistent job, stage, attempt, and artifact dataclasses.
- `src/autotok/job_storage.py` contains SQLite job persistence.
- `src/autotok/job_orchestration.py` contains resumable stage execution, retry,
  crash-recovery, batch-run, manifest, and retention helpers.
- `src/autotok/review_models.py` contains review package, editable metadata,
  regeneration request, approval state, and audit event dataclasses.
- `src/autotok/review_storage.py` persists review packages under `data/reviews/`.
- `src/autotok/publishing_models.py` contains publication records, TikTok capability verification, options, statuses, and audit events.
- `src/autotok/publishing_storage.py` persists publication records under `data/publications/`.
- `src/autotok/publishing.py` contains the official TikTok Content Posting API adapter, OAuth helpers, dry-run workflow, status fetch, and duplicate-prevention logic.
- `src/autotok/operations.py` contains health checks, metrics snapshots, ZIP backup/restore, transient retention, dependency/secret audit checks, and lightweight profiling.
- `src/autotok/review_api.py` routes local dashboard API requests and serves the
  static review UI.
- `src/autotok/review_server.py` adapts the review API to a localhost HTTP
  server.
- `src/autotok/source_models.py` contains source discovery dataclasses.
- `src/autotok/source_adapters.py` contains the Phase 7 Reddit Data API adapter, pagination, rate-limit capture, and filtering.
- `src/autotok/source_ingestion.py` converts discovered posts into canonical story records.
- `src/autotok/script_models.py` contains canonical script/review dataclasses.
- `src/autotok/audio_models.py` contains canonical audio dataclasses.
- `src/autotok/subtitle_models.py` contains canonical subtitle dataclasses.
- `src/autotok/media_models.py` contains canonical background-media and clip
  preparation dataclasses.
- `src/autotok/render_models.py` contains render profiles, render specs,
  rendered-output metadata, and render manifests.
- `src/autotok/normalization.py` normalizes UTF-8 story text and computes stable
  content identifiers.
- `src/autotok/ingestion.py` creates validated manual story records.
- `src/autotok/transform.py` defines the provider-independent script
  transformation interface, deterministic baseline provider, privacy rules, and
  duration budgeting.
- `src/autotok/tts.py` defines the provider-independent TTS interface, local WAV
  provider, fake test provider, and manual-audio record builder.
- `src/autotok/audio_probe.py` probes and validates WAV PCM narration audio.
- `src/autotok/subtitles.py` contains timing strategies, readability checks,
  subtitle validation, and SRT/VTT/ASS export formatting.
- `src/autotok/media_probe.py` wraps `ffprobe` JSON metadata extraction for
  local background clips.
- `src/autotok/media_selection.py` builds authorized media records and performs
  deterministic segment selection with recent-use avoidance.
- `src/autotok/render.py` builds FFmpeg command arguments, writes ASS subtitles,
  runs local rendering, probes output, and validates the portrait MP4.
- `src/autotok/storage.py` persists story artifacts in the filesystem workspace.
- `src/autotok/source_storage.py` persists source discovery runs and raw retrieval cache entries.
- `src/autotok/script_storage.py` persists script review artifacts.
- `src/autotok/audio_storage.py` persists narration audio artifacts.
- `src/autotok/subtitle_storage.py` persists subtitle documents and exports.
- `src/autotok/media_storage.py` persists background-media records and
  clip-preparation artifacts.
- `src/autotok/render_storage.py` persists render specs, manifests, working
  subtitle files, and output MP4 packages.
- `src/autotok/logging.py` centralizes logging setup.
- `src/autotok/errors.py` defines the base exception hierarchy.
- `tests/` covers CLI, configuration, normalization, ingestion, storage,
  transformation, script review, audio probing, TTS providers, audio storage,
  subtitle timing, subtitle exports, subtitle CLI behavior, background-media
  probing, media storage, deterministic selection, media CLI behavior, render
  command construction, render validation, manifests, render CLI behavior,
  SQLite job storage, job orchestration, crash recovery, job CLI behavior,
  review state transitions, review API routes, and media preview serving.

## Configuration

Configuration currently uses command-line overrides, environment variables, and
safe built-in defaults:

1. `--data-dir`, command-specific override
2. `AUTOTOK_DATA_DIR`, default `data`
3. `AUTOTOK_ENV`, default `local`
4. `AUTOTOK_LOG_LEVEL`, default `INFO`
5. `AUTOTOK_TTS_PROVIDER`, default `local_wav`
6. `AUTOTOK_TTS_TIMEOUT_SECONDS`, default `30`
7. `AUTOTOK_REDDIT_OAUTH_TOKEN`, optional live Reddit bearer token
8. `AUTOTOK_REDDIT_USER_AGENT`, default `AutoTok/0.1 local-source-ingestion`
9. `AUTOTOK_REDDIT_TIMEOUT_SECONDS`, default `20`
10. `AUTOTOK_TIKTOK_CLIENT_KEY`, optional TikTok OAuth client key
11. `AUTOTOK_TIKTOK_CLIENT_SECRET`, optional TikTok OAuth client secret
12. `AUTOTOK_TIKTOK_ACCESS_TOKEN`, optional TikTok user access token
13. `AUTOTOK_TIKTOK_REFRESH_TOKEN`, optional TikTok refresh token
14. `AUTOTOK_TIKTOK_TIMEOUT_SECONDS`, default `30`
15. `AUTOTOK_LOG_FORMAT`, default `text`, set to `json` for structured operational logs

Secrets must remain in environment variables or local ignored files. Phase 7 live Reddit discovery requires an OAuth bearer token supplied by environment; fixture discovery and all automated tests remain credential-free. Rendering still only reads approved local artifacts and uses local FFmpeg/FFprobe executables.

## Runtime Data

Generated runtime data must stay outside source code. Phase 1 writes imported
story artifacts under `data/sources/<story_id>/` by default. Phase 2 writes
script review artifacts under `data/scripts/<script_id>/`. Phase 3 writes
audio artifacts under `data/audio/<audio_id>/`. Phase 4 writes subtitle
artifacts under `data/subtitles/<subtitle_id>/`. Phase 5 writes background-media
catalog records under `data/media/<media_id>/` and clip-preparation records under
`data/clips/<clip_id>/`. Phase 6 writes render packages under
`data/renders/<render_id>/`. Phase 10 writes review packages under
`data/reviews/<render_id>/`. Phase 11 writes publication records under
`data/publications/<render_id>/tiktok/`. Phase 12 backup and restore commands operate on the configured data directory and write backup archives only where explicitly requested.

A stored story currently contains:

- `record.json`, canonical JSON representation
- `original.txt`, original manually supplied text or file text
- `normalized.txt`, normalized text used for hashing and stable IDs

A stored source discovery currently contains:

- `record.json`, filtered post metadata, source provenance, query information,
  pagination state, cache hit count, and rate-limit header snapshots
- `raw_pages/page_*.json`, raw listing responses saved for local inspection

A stored content gate currently contains:

- `record.json`, quality score components, duration suitability, duplicate
  matches, content warnings, reject reasons, review flags, deterministic
  fingerprints, gate decision, effective decision, and manual override events

A stored script currently contains:

- `record.json`, canonical script metadata and review status
- `before.txt`, normalized story text before transformation
- `script.txt`, complete narration script text

A stored audio artifact currently contains:

- `record.json`, canonical audio metadata and provider/source details
- `narration.wav`, validated WAV PCM narration audio

A stored subtitle artifact currently contains:

- `record.json`, canonical subtitle cues, timing metadata, readability settings,
  validation status, and script/audio provenance
- `subtitles.srt`, `subtitles.vtt`, or `subtitles.ass`, depending on the
  requested export

A stored background media artifact currently contains:

- `record.json`, FFprobe-derived video metadata, authorization notes, tags, and
  source provenance
- `source.<ext>`, the copied local media file

A stored clip-preparation artifact currently contains:

- `record.json`, selected media ID, target duration, start/end offsets, seed,
  requested orientation and tags, and recent media IDs avoided when possible

A stored render package currently contains:

- `render_spec.json`, resolved artifact IDs, source paths, clip timing, and
  output profile
- `output.mp4`, the rendered portrait video package
- `manifest.json`, render status, output probe metadata, FFmpeg command
  arguments, artifact paths, and provenance IDs
- `work/subtitles.ass`, the generated subtitle file used by FFmpeg

The repository ignores local runtime directories such as `data/`, `inputs/`,
`work/`, `outputs/`, `logs/`, and `cache/`.

## Phase 8 Boundaries

Phase 8 assesses stories with deterministic local rules before production use. It records exact duplicate matches by content hash, near-duplicate matches by token-set similarity, quality score components, duration suitability, privacy and policy warnings, reject reasons, review flags, and a manual override trail. Discovered Reddit stories must have an approved effective gate decision before transformation; manual stories remain transformable unless a stored gate exists and is not approved.

Phase 9 runs story-to-render jobs through persisted ordered stages. The runner marks stale running attempts failed before resume, skips already successful stages, retries failed stages up to the configured local attempt limit, records artifacts, and writes a job manifest. Batch execution is intentionally serial with explicit limits; no distributed queue or parallel worker pool is introduced.

Phase 10 exposes completed render packages through a localhost-only review dashboard. The UI reads and writes review state through the same local API used by tests; it does not duplicate rendering, job, or publishing logic. Review edits are stored as snapshots and audit events under `data/reviews/` so original render artifacts remain intact.

Phase 12 operational tooling is intentionally local and conservative. Health, metrics, audit, and profile commands are read-only except for harmless health probes. Backup writes a requested ZIP archive. Restore and retention are dry-run by default and require `--apply`; restore refuses non-empty targets and unsafe archive paths, while retention only targets transient cache/log/tmp files.

## Deferred Architecture

The following concerns are intentionally deferred to later phases:

- real paid or cloud TTS providers;
- transcription providers;
- unsupported post scheduling;
- analytics ingestion or engagement automation.
