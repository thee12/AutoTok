# AutoTok Architecture

AutoTok is being built as a local-first modular monolith. Phase 0 establishes the
project foundation only; no content ingestion, AI provider calls, audio handling,
subtitle generation, video rendering, database, UI, or publishing behavior exists
yet.

## Current Shape

- `src/autotok/cli.py` exposes the `autotok` command.
- `autotok doctor` is a harmless diagnostic command that validates local
  configuration and prints a summary.
- `src/autotok/config.py` contains the initial configuration model.
- `src/autotok/logging.py` centralizes logging setup.
- `src/autotok/errors.py` defines the base exception hierarchy.
- `tests/` covers the Phase 0 CLI and configuration behavior.

## Configuration

Configuration currently uses environment variables with safe built-in defaults:

1. `AUTOTOK_ENV`, default `local`
2. `AUTOTOK_LOG_LEVEL`, default `INFO`
3. `AUTOTOK_DATA_DIR`, default `data`

Future phases may add file-based configuration if a concrete need appears.
Secrets must remain in environment variables or local ignored files.

## Runtime Data

Generated runtime data must stay outside source code. The repository ignores
local directories such as `data/`, `inputs/`, `work/`, `outputs/`, `logs/`, and
`cache/`.

## Deferred Architecture

The following concerns are intentionally deferred to later phases:

- source/story domain models and artifact storage;
- script transformation providers;
- TTS and transcription providers;
- FFmpeg/FFprobe wrappers;
- SQLite persistence;
- review UI;
- official publishing adapters.
