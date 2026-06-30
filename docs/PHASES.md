# AutoTok Phases

This document is the canonical phase roadmap after Phase 0. Each phase must be
implemented, tested, documented, and reported before the next phase begins.

## Phase 0 - Repository Bootstrap and Architecture

Goal: turn the initial repository into a clean, runnable Python project
foundation.

In scope:

- Python project configuration and dependency strategy
- `src/` package layout
- harmless CLI diagnostic command
- configuration model and `.env.example`
- logging foundation
- custom exception hierarchy
- test, lint, format, and type-check setup
- README, architecture, and status documentation
- Git ignore rules
- development commands
- CI workflow

Excluded:

- story processing
- AI calls
- audio
- subtitles
- FFmpeg rendering
- Reddit/source ingestion
- database
- UI
- publishing

Exit gate: a fresh developer can install the project, run the CLI, and execute
all configured checks.

## Later Phases

Phase 1: manual story ingestion and canonical models.

Phase 2: script transformation and review artifacts.

Phase 3: narration audio.

Phase 4: subtitle generation and alignment.

Phase 5: background-media library.

Phase 6: end-to-end vertical video rendering for the first local MVP.

Phase 7: approved Reddit and source ingestion.

Phase 8: scoring, deduplication, and content gates.

Phase 9: persistent orchestration and batch generation.

Phase 10: local review dashboard.

Phase 11: official publishing and scheduling.

Phase 12: production hardening and deployment.

Phase 13: optional analytics and advanced templates.
