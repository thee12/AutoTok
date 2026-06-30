# AutoTok Status

## Current Phase

Phase 4 - Subtitle generation and alignment.

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
- pytest, ruff, and mypy configuration
- README, architecture documentation, and phase roadmap
- local runtime-data ignore rules
- GitHub Actions CI workflow

## Not Implemented

The repository does not yet select background media, render video, ingest Reddit
content, store data in a database, provide a UI, or publish content. It also does
not call real paid/cloud TTS or transcription providers.

## Phase 4 Acceptance Evidence

An approved script and matching narration audio can produce a validated subtitle
document, store it locally, inspect it through the CLI, and export SRT, VTT, or
ASS subtitle files. Provider word timings are supported through a local JSON
fixture, and approximate alignment is explicitly recorded when used.
