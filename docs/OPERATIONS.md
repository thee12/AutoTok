# Operations Runbook

Phase 12 keeps AutoTok local-first. The selected deployment package is the
existing Python package installed into a virtual environment or `pipx`-style
isolated environment on the machine that owns the media and data directory. No
server process, distributed worker, database service, or cloud runtime is
introduced.

## Install

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
autotok doctor
```

Use `AUTOTOK_DATA_DIR` or `--data-dir` to point commands at the local runtime
data directory. Keep real secrets in a local ignored `.env` or the shell
environment, never in committed files.

## Structured Logs

Text logs remain the default. JSON logs are available for scheduled runs or log
collectors:

```text
AUTOTOK_LOG_FORMAT=json
```

JSON log records include timestamp, level, logger, message, and exception text
when present.

## Monitor

Run a local health check:

```bash
autotok ops health --json
```

The health check validates data-directory writability, the job database schema
when present, major artifact directories, and FFmpeg/FFprobe availability.
Warnings are allowed for optional components that have not been used yet.

Collect local metrics:

```bash
autotok ops metrics --json
```

Metrics include artifact file counts and byte totals, job status counts, review
status counts, and publication status counts.

## Backup

Create a ZIP backup of the configured data directory:

```bash
autotok ops backup --output backups/autotok-data.zip
```

Cache files are excluded by default. Add `--include-cache` only when raw cache
material is required for troubleshooting.

## Restore

Inspect a backup without writing files:

```bash
autotok ops restore --archive backups/autotok-data.zip --target-data-dir restored-data
```

Restore into an empty target directory:

```bash
autotok ops restore --archive backups/autotok-data.zip --target-data-dir restored-data --apply
```

Restore refuses unsafe archive paths and refuses to write into a non-empty
target. To replace an existing data directory, restore into a new directory,
inspect it, then deliberately update `AUTOTOK_DATA_DIR`.

## Retention

Preview cleanup for transient files:

```bash
autotok ops retention --older-than-days 30
```

Apply cleanup:

```bash
autotok ops retention --older-than-days 30 --apply
```

The retention policy only targets transient `cache/`, `logs/`, and `tmp/` files
under the data directory. Durable story, media, render, review, publication, and
job artifacts are retained until the operator explicitly deletes them or uses a
future purpose-built deletion command.

## Audit

Run the local dependency inventory and high-confidence secret scan:

```bash
autotok ops audit --json
```

The audit parses `pyproject.toml`, checks committed ignore patterns, and scans
repository text files for likely committed secrets while excluding local runtime
folders and `.env.example` placeholders. It does not contact vulnerability
databases; use an external scanner such as `pip-audit` in environments that
require advisory lookups.

## Profile

Capture a lightweight operational performance baseline:

```bash
autotok ops profile --iterations 5 --json
```

The profile command measures local metrics collection time. This gives a cheap
signal when data directories grow large without adding profiling dependencies.

## Upgrade

1. Run `autotok ops health --json`.
2. Create a backup with `autotok ops backup --output backups/pre-upgrade.zip`.
3. Update the checkout or installed package.
4. Run `python -m pip install -e ".[dev]"` if dependencies changed.
5. Run `ruff check .`, `ruff format --check .`, `mypy .`, and `pytest`.
6. Run `autotok ops health --json` and `autotok ops metrics --json`.
7. If a rollback is needed, restore the pre-upgrade backup into a new data
   directory and point `AUTOTOK_DATA_DIR` at it.

The current persistent schema is the Phase 9 job SQLite schema. AutoTok validates
that schema at startup and fails with an actionable error if the schema version
is unsupported.
