# AutoTok Status

## Current Phase

Phase 2 - Script transformation and review artifacts.

## Implemented

- Python package metadata in `pyproject.toml`
- `src/autotok` package layout
- `autotok doctor` diagnostic CLI command
- environment-backed configuration model with CLI `--data-dir` override
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
- fake transformer test double
- script artifacts under `data/scripts/`
- script inspection and approval through `autotok script inspect` and
  `autotok script approve`
- pytest, ruff, and mypy configuration
- README, architecture documentation, and phase roadmap
- local runtime-data ignore rules
- GitHub Actions CI workflow

## Not Implemented

The repository does not yet call real AI providers, generate audio, create
subtitles, render video, ingest Reddit content, store data in a database, provide
a UI, or publish content.

## Phase 2 Acceptance Evidence

An imported story can be transformed into a pending-review narration script,
inspected through the CLI, approved locally, and represented by before/after
artifacts, transformation history, privacy-redaction metadata, and a duration
estimate.
