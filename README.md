# AutoTok

AutoTok is a local-first, human-reviewed pipeline for creating short-form
vertical video packages from approved source stories. This repository is
currently complete through Phase 2: script transformation and review artifacts.

No AI provider calls, audio generation, subtitle generation, video rendering,
Reddit ingestion, database, UI, or publishing behavior exists yet.

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
later phases consume them.

## Documentation

- `docs/ARCHITECTURE.md`
- `docs/PHASES.md`
- `docs/STATUS.md`
