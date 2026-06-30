# AutoTok Status

## Current Phase

Phase 1 - Manual story ingestion and canonical models.

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
- idempotent filesystem artifact storage under `data/sources/`
- story inspection through `autotok story inspect`
- pytest, ruff, and mypy configuration
- README, architecture documentation, and phase roadmap
- local runtime-data ignore rules
- GitHub Actions CI workflow

## Not Implemented

The repository does not yet transform stories, call AI providers, generate audio,
create subtitles, render video, ingest Reddit content, store data in a database,
provide a UI, or publish content.

## Phase 1 Acceptance Evidence

A local story can be imported repeatedly into the same stable story ID, inspected
through the CLI, and represented by validated metadata and preserved text
artifacts without modifying the source file.
