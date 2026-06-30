# AutoTok Architecture

AutoTok is being built as a local-first modular monolith. Phase 4 adds subtitle
documents and exports only; no background-media selection, video rendering,
database, UI, or publishing behavior exists yet.

## Current Shape

- `src/autotok/cli.py` exposes the `autotok` command.
- `autotok doctor` validates local configuration and prints a diagnostic summary.
- `autotok story import` imports manually supplied text or a local UTF-8 file.
- `autotok story inspect` loads and summarizes a stored story record.
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
- `src/autotok/config.py` contains the initial configuration model.
- `src/autotok/models.py` contains canonical story/source dataclasses.
- `src/autotok/script_models.py` contains canonical script/review dataclasses.
- `src/autotok/audio_models.py` contains canonical audio dataclasses.
- `src/autotok/subtitle_models.py` contains canonical subtitle dataclasses.
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
- `src/autotok/storage.py` persists story artifacts in the filesystem workspace.
- `src/autotok/script_storage.py` persists script review artifacts.
- `src/autotok/audio_storage.py` persists narration audio artifacts.
- `src/autotok/subtitle_storage.py` persists subtitle documents and exports.
- `src/autotok/logging.py` centralizes logging setup.
- `src/autotok/errors.py` defines the base exception hierarchy.
- `tests/` covers CLI, configuration, normalization, ingestion, storage,
  transformation, script review, audio probing, TTS providers, audio storage,
  subtitle timing, subtitle exports, and subtitle CLI behavior.

## Configuration

Configuration currently uses command-line overrides, environment variables, and
safe built-in defaults:

1. `--data-dir`, command-specific override
2. `AUTOTOK_DATA_DIR`, default `data`
3. `AUTOTOK_ENV`, default `local`
4. `AUTOTOK_LOG_LEVEL`, default `INFO`
5. `AUTOTOK_TTS_PROVIDER`, default `local_wav`
6. `AUTOTOK_TTS_TIMEOUT_SECONDS`, default `30`

Secrets must remain in environment variables or local ignored files. Phase 4 does
not require any credentials because subtitle generation uses local script/audio
artifacts and optional manually supplied timing fixtures.

## Runtime Data

Generated runtime data must stay outside source code. Phase 1 writes imported
story artifacts under `data/sources/<story_id>/` by default. Phase 2 writes
script review artifacts under `data/scripts/<script_id>/`. Phase 3 writes
audio artifacts under `data/audio/<audio_id>/`. Phase 4 writes subtitle
artifacts under `data/subtitles/<subtitle_id>/`.

A stored story currently contains:

- `record.json`, canonical JSON representation
- `original.txt`, original manually supplied text or file text
- `normalized.txt`, normalized text used for hashing and stable IDs

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

The repository ignores local runtime directories such as `data/`, `inputs/`,
`work/`, `outputs/`, `logs/`, and `cache/`.

## Phase 4 Boundaries

Phase 4 intentionally stops at subtitle documents and text-based subtitle
exports. Provider word timings can be used when explicitly supplied; otherwise,
AutoTok records that an approximate local fallback distributed script words
across the audio duration. Subtitle rendering into video, background media,
composition, and publication remain deferred.

## Deferred Architecture

The following concerns are intentionally deferred to later phases:

- real paid or cloud TTS providers;
- transcription providers;
- FFmpeg/FFprobe wrappers;
- authorized media cataloging;
- burned-in subtitle rendering;
- SQLite persistence;
- review UI;
- official publishing adapters.
