# AutoTok Architecture

AutoTok is being built as a local-first modular monolith. Phase 2 adds local
story-to-script transformation and review artifacts only; no AI provider calls,
audio handling, subtitle generation, video rendering, database, UI, or publishing
behavior exists yet.

## Current Shape

- `src/autotok/cli.py` exposes the `autotok` command.
- `autotok doctor` validates local configuration and prints a diagnostic summary.
- `autotok story import` imports manually supplied text or a local UTF-8 file.
- `autotok story inspect` loads and summarizes a stored story record.
- `autotok story transform` creates a reviewable narration script from a story.
- `autotok script inspect` loads and summarizes a generated script record.
- `autotok script approve` marks a generated script approved for later phases.
- `src/autotok/config.py` contains the initial configuration model.
- `src/autotok/models.py` contains canonical story/source dataclasses.
- `src/autotok/script_models.py` contains canonical script/review dataclasses.
- `src/autotok/normalization.py` normalizes UTF-8 story text and computes stable
  content identifiers.
- `src/autotok/ingestion.py` creates validated manual story records.
- `src/autotok/transform.py` defines the provider-independent transformation
  interface, deterministic baseline provider, privacy rules, and duration
  budgeting.
- `src/autotok/storage.py` persists story artifacts in the filesystem workspace.
- `src/autotok/script_storage.py` persists script review artifacts.
- `src/autotok/logging.py` centralizes logging setup.
- `src/autotok/errors.py` defines the base exception hierarchy.
- `tests/` covers the CLI, configuration, normalization, ingestion, storage,
  transformation, and script review behavior.

## Configuration

Configuration currently uses command-line overrides, environment variables, and
safe built-in defaults:

1. `--data-dir`, command-specific override
2. `AUTOTOK_DATA_DIR`, default `data`
3. `AUTOTOK_ENV`, default `local`
4. `AUTOTOK_LOG_LEVEL`, default `INFO`

Future phases may add file-based configuration if a concrete need appears.
Secrets must remain in environment variables or local ignored files.

## Runtime Data

Generated runtime data must stay outside source code. Phase 1 writes imported
story artifacts under `data/sources/<story_id>/` by default. Phase 2 writes
script review artifacts under `data/scripts/<script_id>/`.

A stored story currently contains:

- `record.json`, canonical JSON representation
- `original.txt`, original manually supplied text or file text
- `normalized.txt`, normalized text used for hashing and stable IDs

A stored script currently contains:

- `record.json`, canonical script metadata and review status
- `before.txt`, normalized story text before transformation
- `script.txt`, complete narration script text

The repository ignores local runtime directories such as `data/`, `inputs/`,
`work/`, `outputs/`, `logs/`, and `cache/`.

## Phase 2 Boundaries

Phase 2 intentionally stops at reviewable script artifacts. The deterministic
baseline transformer performs local cleanup, common contact-detail redaction,
hook/body/outro sectioning, duration budgeting, and transformation metadata
capture. A fake transformer exists only as a test double for the provider
interface. No real external AI adapter is configured or called.

## Deferred Architecture

The following concerns are intentionally deferred to later phases:

- real AI transformation adapters;
- TTS and transcription providers;
- subtitle models and alignment;
- FFmpeg/FFprobe wrappers;
- authorized media cataloging;
- SQLite persistence;
- review UI;
- official publishing adapters.
