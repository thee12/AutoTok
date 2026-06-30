# AutoTok Status

## Current Phase

Phase 3 - Narration audio.

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
- pytest, ruff, and mypy configuration
- README, architecture documentation, and phase roadmap
- local runtime-data ignore rules
- GitHub Actions CI workflow

## Not Implemented

The repository does not yet create subtitles, render video, ingest Reddit
content, store data in a database, provide a UI, or publish content. It also does
not call real paid/cloud TTS providers.

## Phase 3 Acceptance Evidence

An approved script can produce deterministic local WAV narration audio, accept a
manually supplied WAV narration file, validate audio metadata, store the artifact
locally, and inspect the resulting audio record through the CLI.
