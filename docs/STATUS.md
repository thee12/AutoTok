# AutoTok Status

## Current Phase

Phase 5 - Background-media library.

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
- pytest, ruff, and mypy configuration
- README, architecture documentation, and phase roadmap
- local runtime-data ignore rules
- GitHub Actions CI workflow

## Not Implemented

The repository does not yet render video, trim selected clips, ingest Reddit
content, store data in a database, provide a UI, or publish content. It also does
not call real paid/cloud TTS or transcription providers.

## Phase 5 Acceptance Evidence

An authorized local background clip can be cataloged with ffprobe metadata,
license/usage notes, and tags, inspected through the CLI, and selected into a
clip-preparation record with deterministic seed-based start offsets. Selection
filters by target duration, orientation, and tags, and avoids recently selected
media IDs when alternatives exist.
