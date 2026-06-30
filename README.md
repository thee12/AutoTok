# AutoTok

AutoTok is a local-first, human-reviewed pipeline for creating short-form
vertical video packages from approved source stories. This repository is
currently in Phase 0: project bootstrap and architecture only.

No story processing, AI calls, audio generation, subtitle generation, video
rendering, Reddit ingestion, database, UI, or publishing behavior exists yet.

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

Print the diagnostic as JSON:

```bash
autotok doctor --json
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

## Documentation

- `docs/ARCHITECTURE.md`
- `docs/PHASES.md`
- `docs/STATUS.md`
