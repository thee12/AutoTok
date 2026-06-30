# AutoTok Architecture

AutoTok is being built as a local-first modular monolith. Phase 1 establishes
manual story ingestion and canonical source records only; no AI provider calls,
audio handling, subtitle generation, video rendering, database, UI, or publishing
behavior exists yet.

## Current Shape

- `src/autotok/cli.py` exposes the `autotok` command.
- `autotok doctor` validates local configuration and prints a diagnostic summary.
- `autotok story import` imports manually supplied text or a local UTF-8 file.
- `autotok story inspect` loads and summarizes a stored story record.
- `src/autotok/config.py` contains the initial configuration model.
- `src/autotok/models.py` contains canonical Phase 1 story/source dataclasses.
- `src/autotok/normalization.py` normalizes UTF-8 story text and computes stable
  content identifiers.
- `src/autotok/ingestion.py` creates validated manual story records.
- `src/autotok/storage.py` persists story artifacts in the filesystem workspace.
- `src/autotok/logging.py` centralizes logging setup.
- `src/autotok/errors.py` defines the base exception hierarchy.
- `tests/` covers the CLI, configuration, normalization, ingestion, and storage
  behavior.

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
story artifacts under `data/sources/<story_id>/` by default.

A stored story currently contains:

- `record.json`, canonical JSON representation
- `original.txt`, original manually supplied text or file text
- `normalized.txt`, normalized text used for hashing and stable IDs

The repository ignores local runtime directories such as `data/`, `inputs/`,
`work/`, `outputs/`, `logs/`, and `cache/`.

## Phase 1 Boundaries

Phase 1 intentionally stops at manual story ingestion and inspection. The stored
record preserves source text, normalized text, source metadata, a SHA-256 content
hash, and a stable story ID derived from the normalized content hash.

## Deferred Architecture

The following concerns are intentionally deferred to later phases:

- script transformation providers;
- TTS and transcription providers;
- subtitle models and alignment;
- FFmpeg/FFprobe wrappers;
- authorized media cataloging;
- SQLite persistence;
- review UI;
- official publishing adapters.
