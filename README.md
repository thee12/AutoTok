# AutoTok

AutoTok is a local-first, human-reviewed pipeline for creating short-form
vertical video packages from approved source stories. This repository is
currently complete through Phase 3: narration audio.

No subtitle generation, video rendering, Reddit ingestion, database, UI, or
publishing behavior exists yet. No paid provider calls are made by tests.

## Requirements

- Python 3.12 or newer

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On macOS or Linux, activate the virtual environment with:

```bash
source .venv/bin/activate
```

## Commands

Run the harmless diagnostic command:

```bash
autotok doctor
```

Import manually supplied story text:

```bash
autotok story import --text "A short approved story." --title "Optional title"
```

Import a local UTF-8 story file:

```bash
autotok story import --file path/to/story.txt
```

Inspect an imported story:

```bash
autotok story inspect story_0123456789abcdef
```

Transform an imported story into a reviewable narration script:

```bash
autotok story transform story_0123456789abcdef --target-seconds 60
```

Inspect and approve a generated script:

```bash
autotok script inspect script_0123456789abcdef
autotok script approve script_0123456789abcdef
```

Create validated narration audio for an approved script with the local WAV
provider:

```bash
autotok script narrate script_0123456789abcdef --provider local_wav
```

Use an existing local WAV file as manually supplied narration audio:

```bash
autotok script narrate script_0123456789abcdef --audio-file path/to/narration.wav
```

Inspect generated or imported narration audio:

```bash
autotok audio inspect audio_0123456789abcdef
```

Use a specific local artifact workspace:

```bash
autotok --data-dir data story import --file path/to/story.txt --json
```

Run all configured checks:

```bash
ruff check .
ruff format --check .
mypy .
pytest
```

Format code:

```bash
ruff format .
```

## Configuration

Copy `.env.example` to `.env` for local settings if needed. Real secrets must
not be committed.

Current environment variables:

- `AUTOTOK_ENV`, default `local`
- `AUTOTOK_LOG_LEVEL`, default `INFO`
- `AUTOTOK_DATA_DIR`, default `data`
- `AUTOTOK_TTS_PROVIDER`, default `local_wav`
- `AUTOTOK_TTS_TIMEOUT_SECONDS`, default `30`

The CLI `--data-dir` option overrides `AUTOTOK_DATA_DIR` for that command.

## Story Artifacts

Imported stories are stored under:

```text
data/sources/story_<hash-prefix>/
```

Each imported story directory contains:

- `record.json`, canonical metadata and text representation
- `original.txt`, the source text as supplied or read from the UTF-8 file
- `normalized.txt`, normalized story text used for stable IDs and hashes

Re-importing the same normalized story text is idempotent and returns the same
story ID.

## Script Artifacts

Generated narration scripts are stored under:

```text
data/scripts/script_<hash-prefix>/
```

Each script directory contains:

- `record.json`, review status, section data, duration budget, privacy report,
  provider metadata, and transformation history
- `before.txt`, the normalized source story text used for transformation
- `script.txt`, the full hook/body/outro narration script

Scripts are created with `pending_review` status and must be approved before
Phase 3 narration audio can be produced or accepted.

## Audio Artifacts

Validated narration audio is stored under:

```text
data/audio/audio_<hash-prefix>/
```

Each audio directory contains:

- `record.json`, audio metadata, source/provider metadata, and request metadata
- `narration.wav`, the validated WAV PCM audio artifact

The `local_wav` provider is a credential-free local development provider that
creates deterministic valid WAV placeholder audio. Real speech-provider adapters
are deferred until explicitly selected in a later prompt.

## Documentation

- `docs/ARCHITECTURE.md`
- `docs/PHASES.md`
- `docs/STATUS.md`
