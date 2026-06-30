# AutoTok Architecture

AutoTok is being built as a local-first modular monolith. Phase 6 adds local
portrait video render packages only; no Reddit ingestion, database, UI, or
publishing behavior exists yet.

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
- `autotok media import` catalogs an authorized local video file using ffprobe
  metadata, license notes, and tags.
- `autotok media inspect` loads and summarizes a cataloged media record.
- `autotok media select` creates a deterministic clip-preparation artifact for a
  target duration.
- `autotok render create` composes background media, narration audio, and
  burned-in subtitles into a validated portrait MP4 package.
- `autotok render inspect` loads and summarizes a completed render manifest.
- `src/autotok/config.py` contains the initial configuration model.
- `src/autotok/models.py` contains canonical story/source dataclasses.
- `src/autotok/script_models.py` contains canonical script/review dataclasses.
- `src/autotok/audio_models.py` contains canonical audio dataclasses.
- `src/autotok/subtitle_models.py` contains canonical subtitle dataclasses.
- `src/autotok/media_models.py` contains canonical background-media and clip
  preparation dataclasses.
- `src/autotok/render_models.py` contains render profiles, render specs,
  rendered-output metadata, and render manifests.
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
- `src/autotok/media_probe.py` wraps `ffprobe` JSON metadata extraction for
  local background clips.
- `src/autotok/media_selection.py` builds authorized media records and performs
  deterministic segment selection with recent-use avoidance.
- `src/autotok/render.py` builds FFmpeg command arguments, writes ASS subtitles,
  runs local rendering, probes output, and validates the portrait MP4.
- `src/autotok/storage.py` persists story artifacts in the filesystem workspace.
- `src/autotok/script_storage.py` persists script review artifacts.
- `src/autotok/audio_storage.py` persists narration audio artifacts.
- `src/autotok/subtitle_storage.py` persists subtitle documents and exports.
- `src/autotok/media_storage.py` persists background-media records and
  clip-preparation artifacts.
- `src/autotok/render_storage.py` persists render specs, manifests, working
  subtitle files, and output MP4 packages.
- `src/autotok/logging.py` centralizes logging setup.
- `src/autotok/errors.py` defines the base exception hierarchy.
- `tests/` covers CLI, configuration, normalization, ingestion, storage,
  transformation, script review, audio probing, TTS providers, audio storage,
  subtitle timing, subtitle exports, subtitle CLI behavior, background-media
  probing, media storage, deterministic selection, media CLI behavior, render
  command construction, render validation, manifests, and render CLI behavior.

## Configuration

Configuration currently uses command-line overrides, environment variables, and
safe built-in defaults:

1. `--data-dir`, command-specific override
2. `AUTOTOK_DATA_DIR`, default `data`
3. `AUTOTOK_ENV`, default `local`
4. `AUTOTOK_LOG_LEVEL`, default `INFO`
5. `AUTOTOK_TTS_PROVIDER`, default `local_wav`
6. `AUTOTOK_TTS_TIMEOUT_SECONDS`, default `30`

Secrets must remain in environment variables or local ignored files. Phase 6 does
not require credentials because rendering only reads approved local artifacts and
uses local FFmpeg/FFprobe executables.

## Runtime Data

Generated runtime data must stay outside source code. Phase 1 writes imported
story artifacts under `data/sources/<story_id>/` by default. Phase 2 writes
script review artifacts under `data/scripts/<script_id>/`. Phase 3 writes
audio artifacts under `data/audio/<audio_id>/`. Phase 4 writes subtitle
artifacts under `data/subtitles/<subtitle_id>/`. Phase 5 writes background-media
catalog records under `data/media/<media_id>/` and clip-preparation records under
`data/clips/<clip_id>/`. Phase 6 writes render packages under
`data/renders/<render_id>/`.

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

A stored background media artifact currently contains:

- `record.json`, FFprobe-derived video metadata, authorization notes, tags, and
  source provenance
- `source.<ext>`, the copied local media file

A stored clip-preparation artifact currently contains:

- `record.json`, selected media ID, target duration, start/end offsets, seed,
  requested orientation and tags, and recent media IDs avoided when possible

A stored render package currently contains:

- `render_spec.json`, resolved artifact IDs, source paths, clip timing, and
  output profile
- `output.mp4`, the rendered portrait video package
- `manifest.json`, render status, output probe metadata, FFmpeg command
  arguments, artifact paths, and provenance IDs
- `work/subtitles.ass`, the generated subtitle file used by FFmpeg

The repository ignores local runtime directories such as `data/`, `inputs/`,
`work/`, `outputs/`, `logs/`, and `cache/`.

## Phase 6 Boundaries

Phase 6 completes the first local MVP by composing existing approved artifacts
into a reviewable portrait MP4. It uses FFmpeg through explicit argument arrays,
burns generated subtitles into the video, mixes narration audio, probes the
output, and records a manifest. Automated source discovery, persistent jobs,
review UI, scheduling, and publishing remain deferred.

## Deferred Architecture

The following concerns are intentionally deferred to later phases:

- real paid or cloud TTS providers;
- transcription providers;
- SQLite persistence;
- review UI;
- official publishing adapters.
