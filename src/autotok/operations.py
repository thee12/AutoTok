"""Production hardening and local operations helpers for Phase 12."""

from __future__ import annotations

import json
import re
import shutil
import time
import tomllib
import zipfile
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from autotok.errors import PersistenceError, UserInputError
from autotok.job_models import JobStatus
from autotok.job_storage import DEFAULT_JOB_DB_FILENAME, JobStore
from autotok.publishing_models import PublicationStatus
from autotok.publishing_storage import PublicationStore

BACKUP_MANIFEST = "autotok_backup_manifest.json"
RESTORE_MANIFEST = "autotok_restore_manifest.json"
DEFAULT_TRANSIENT_DIRS = ("cache", "logs", "tmp")
ARTIFACT_DIRS = (
    "sources",
    "scripts",
    "audio",
    "subtitles",
    "media",
    "clips",
    "renders",
    "source_discovery",
    "content_gates",
    "jobs",
    "reviews",
    "publications",
    "cache",
)
SECRET_FILE_EXCLUDES = {
    ".env.example",
    "docs/PUBLISHING.md",
}
SECRET_PATH_EXCLUDES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".pytest-tmp",
    ".ruff_cache",
    ".venv",
    "data",
}
SECRET_PATTERNS = (
    re.compile(
        r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"
    ),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-.]{30,}"),
)


@dataclass(frozen=True, slots=True)
class OperationCheck:
    """One health or audit check result."""

    name: str
    status: str
    message: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class OperationReport:
    """A generic structured operations report."""

    generated_at: str
    status: str
    checks: tuple[OperationCheck, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "status": self.status,
            "checks": [check.to_dict() for check in self.checks],
            "metadata": dict(self.metadata),
        }


def build_health_report(data_dir: Path) -> OperationReport:
    """Build a local health report without contacting external providers."""
    checks = [
        _data_dir_check(data_dir),
        _job_database_check(data_dir),
        _directory_check(data_dir, "renders"),
        _directory_check(data_dir, "reviews"),
        _directory_check(data_dir, "publications"),
        _executable_check("ffmpeg"),
        _executable_check("ffprobe"),
    ]
    return OperationReport(
        generated_at=_utc_timestamp(),
        status=_overall_status(checks),
        checks=tuple(checks),
        metadata={"data_dir": str(data_dir)},
    )


def build_metrics_report(data_dir: Path) -> dict[str, Any]:
    """Return local metrics for artifacts, jobs, reviews, and publications."""
    directories: dict[str, dict[str, int | bool]] = {
        name: _directory_metrics(data_dir / name) for name in ARTIFACT_DIRS
    }
    total_files = sum(int(item["file_count"]) for item in directories.values())
    total_bytes = sum(int(item["bytes"]) for item in directories.values())
    return {
        "generated_at": _utc_timestamp(),
        "data_dir": str(data_dir),
        "directories": directories,
        "totals": {"file_count": total_files, "bytes": total_bytes},
        "jobs": _job_metrics(data_dir),
        "reviews": _review_metrics(data_dir),
        "publications": _publication_metrics(data_dir),
    }


def create_backup(
    data_dir: Path,
    output_path: Path,
    *,
    include_cache: bool = False,
) -> dict[str, Any]:
    """Create a ZIP backup of the local data directory."""
    output_path = output_path.expanduser()
    if output_path.exists() and output_path.is_dir():
        raise UserInputError("--output must be a backup ZIP file path, not a directory.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    files = list(_iter_backup_files(data_dir, include_cache=include_cache, output_path=output_path))
    manifest = {
        "backup_id": f"backup_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
        "created_at": _utc_timestamp(),
        "data_dir": str(data_dir),
        "include_cache": include_cache,
        "file_count": len(files),
        "bytes": sum(path.stat().st_size for path in files),
    }
    try:
        with zipfile.ZipFile(output_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(BACKUP_MANIFEST, json.dumps(manifest, indent=2, sort_keys=True))
            for path in files:
                archive.write(path, _archive_name(data_dir, path))
    except OSError as exc:
        raise PersistenceError(f"Could not create backup: {output_path}") from exc
    return {"archive": str(output_path), "manifest": manifest}


def inspect_restore(
    archive_path: Path,
    target_data_dir: Path,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    """Validate a backup archive and optionally restore it into an empty target."""
    archive_path = archive_path.expanduser()
    target_data_dir = target_data_dir.expanduser()
    members = _safe_archive_members(archive_path)
    restore_files = [member for member in members if member.filename != BACKUP_MANIFEST]
    result: dict[str, Any] = {
        "archive": str(archive_path),
        "target_data_dir": str(target_data_dir),
        "apply": apply,
        "file_count": len(restore_files),
        "members": [member.filename for member in restore_files],
    }
    if not apply:
        result["restored"] = False
        return result
    if target_data_dir.exists() and any(target_data_dir.iterdir()):
        raise UserInputError("Restore target must be empty; choose a new data directory.")
    target_data_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for member in restore_files:
                target_path = _restore_target(target_data_dir, member.filename)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
        (target_data_dir / RESTORE_MANIFEST).write_text(
            json.dumps(
                {
                    "restored_at": _utc_timestamp(),
                    "archive": str(archive_path),
                    "file_count": len(restore_files),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise PersistenceError(f"Could not restore backup: {archive_path}") from exc
    result["restored"] = True
    return result


def plan_retention(
    data_dir: Path,
    *,
    older_than_days: int,
    apply: bool = False,
    transient_dirs: Iterable[str] = DEFAULT_TRANSIENT_DIRS,
) -> dict[str, Any]:
    """Plan or apply cleanup for transient local artifacts only."""
    if older_than_days <= 0:
        raise UserInputError("--older-than-days must be greater than zero.")
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    candidates = list(_retention_candidates(data_dir, cutoff, transient_dirs))
    deleted: list[str] = []
    if apply:
        for path in candidates:
            _remove_safe_transient_path(data_dir, path)
            deleted.append(str(path))
    return {
        "generated_at": _utc_timestamp(),
        "data_dir": str(data_dir),
        "apply": apply,
        "older_than_days": older_than_days,
        "candidate_count": len(candidates),
        "candidates": [str(path) for path in candidates],
        "deleted": deleted,
        "policy": (
            "Only transient cache/log/tmp files are eligible. Durable story, media, render, "
            "review, and publication artifacts require explicit user deletion."
        ),
    }


def audit_repository(repo_root: Path) -> OperationReport:
    """Run a local dependency and high-confidence secret audit."""
    checks = [
        _dependency_check(repo_root / "pyproject.toml"),
        _secret_scan_check(repo_root),
        _gitignore_check(repo_root / ".gitignore"),
    ]
    return OperationReport(
        generated_at=_utc_timestamp(),
        status=_overall_status(checks),
        checks=tuple(checks),
        metadata={"repo_root": str(repo_root)},
    )


def profile_operations(data_dir: Path, *, iterations: int = 3) -> dict[str, Any]:
    """Profile local metrics collection as a lightweight operational baseline."""
    if iterations <= 0:
        raise UserInputError("--iterations must be greater than zero.")
    durations: list[float] = []
    last_file_count = 0
    for _ in range(iterations):
        started = time.perf_counter()
        metrics = build_metrics_report(data_dir)
        durations.append(time.perf_counter() - started)
        totals = metrics["totals"]
        if isinstance(totals, Mapping):
            last_file_count = int(totals["file_count"])
    return {
        "generated_at": _utc_timestamp(),
        "data_dir": str(data_dir),
        "iterations": iterations,
        "operation": "metrics_snapshot",
        "min_seconds": min(durations),
        "max_seconds": max(durations),
        "avg_seconds": sum(durations) / len(durations),
        "last_file_count": last_file_count,
    }


def _data_dir_check(data_dir: Path) -> OperationCheck:
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".autotok_healthcheck"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return OperationCheck("data_dir_writable", "ok", "Data directory is writable.")
    except OSError as exc:
        return OperationCheck(
            "data_dir_writable",
            "error",
            "Data directory is not writable.",
            {"error": str(exc)},
        )


def _job_database_check(data_dir: Path) -> OperationCheck:
    db_path = data_dir / DEFAULT_JOB_DB_FILENAME
    if not db_path.exists():
        return OperationCheck("job_database", "warning", "Job database has not been created yet.")
    try:
        JobStore(data_dir).initialize()
        return OperationCheck("job_database", "ok", "Job database schema is valid.")
    except PersistenceError as exc:
        return OperationCheck(
            "job_database",
            "error",
            "Job database check failed.",
            {"error": str(exc)},
        )


def _directory_check(data_dir: Path, name: str) -> OperationCheck:
    path = data_dir / name
    if path.exists():
        return OperationCheck(f"{name}_directory", "ok", f"{name} directory exists.")
    return OperationCheck(f"{name}_directory", "warning", f"{name} directory has no artifacts yet.")


def _executable_check(name: str) -> OperationCheck:
    path = shutil.which(name)
    if path is None:
        return OperationCheck(
            f"{name}_available",
            "warning",
            f"{name} was not found on PATH; media import/render commands may need explicit paths.",
        )
    return OperationCheck(f"{name}_available", "ok", f"{name} is available.", {"path": path})


def _directory_metrics(path: Path) -> dict[str, int | bool]:
    if not path.exists():
        return {"exists": False, "file_count": 0, "bytes": 0}
    file_count = 0
    bytes_total = 0
    for child in path.rglob("*"):
        if child.is_file():
            file_count += 1
            bytes_total += child.stat().st_size
    return {"exists": True, "file_count": file_count, "bytes": bytes_total}


def _job_metrics(data_dir: Path) -> dict[str, object]:
    if not (data_dir / DEFAULT_JOB_DB_FILENAME).exists():
        return {"database_exists": False, "status_counts": {}}
    counts = Counter(job.status.value for job in JobStore(data_dir).list_jobs())
    return {
        "database_exists": True,
        "status_counts": {status.value: counts.get(status.value, 0) for status in JobStatus},
    }


def _review_metrics(data_dir: Path) -> dict[str, object]:
    counts: Counter[str] = Counter()
    for record_path in sorted((data_dir / "reviews").glob("render_*/review.json")):
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            counts["unreadable"] += 1
            continue
        counts[str(payload.get("status", "unknown"))] += 1
    return {"status_counts": dict(counts)}


def _publication_metrics(data_dir: Path) -> dict[str, object]:
    counts = Counter(stored.record.status.value for stored in PublicationStore(data_dir).list())
    return {
        "status_counts": {status.value: counts.get(status.value, 0) for status in PublicationStatus}
    }


def _iter_backup_files(
    data_dir: Path,
    *,
    include_cache: bool,
    output_path: Path,
) -> Iterable[Path]:
    if not data_dir.exists():
        return ()
    data_root = data_dir.resolve()
    output_resolved = output_path.resolve()
    files: list[Path] = []
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved == output_resolved:
            continue
        relative = resolved.relative_to(data_root)
        if not include_cache and relative.parts and relative.parts[0] == "cache":
            continue
        files.append(path)
    return tuple(files)


def _archive_name(data_dir: Path, path: Path) -> str:
    return path.resolve().relative_to(data_dir.resolve()).as_posix()


def _safe_archive_members(archive_path: Path) -> list[zipfile.ZipInfo]:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise UserInputError(f"Backup archive is not readable: {archive_path}") from exc
    for member in members:
        _validate_archive_name(member.filename)
    return members


def _validate_archive_name(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise UserInputError(f"Backup archive contains an unsafe path: {name}")


def _restore_target(target_data_dir: Path, name: str) -> Path:
    _validate_archive_name(name)
    resolved = (target_data_dir / Path(*PurePosixPath(name).parts)).resolve()
    root = target_data_dir.resolve()
    if resolved != root and root not in resolved.parents:
        raise UserInputError(f"Backup archive contains an unsafe path: {name}")
    return resolved


def _retention_candidates(
    data_dir: Path,
    cutoff: datetime,
    transient_dirs: Iterable[str],
) -> Iterable[Path]:
    candidates: list[Path] = []
    cutoff_timestamp = cutoff.timestamp()
    for directory_name in transient_dirs:
        root = data_dir / directory_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.stat().st_mtime < cutoff_timestamp:
                candidates.append(path)
    return tuple(candidates)


def _remove_safe_transient_path(data_dir: Path, path: Path) -> None:
    resolved = path.resolve()
    allowed_roots = tuple((data_dir / name).resolve() for name in DEFAULT_TRANSIENT_DIRS)
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise UserInputError(f"Retention candidate is outside transient directories: {path}")
    resolved.unlink()
    parent = resolved.parent
    data_root = data_dir.resolve()
    while parent != data_root and parent.exists() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def _dependency_check(pyproject_path: Path) -> OperationCheck:
    try:
        payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return OperationCheck(
            "dependency_inventory",
            "error",
            "pyproject.toml could not be read.",
            {"error": str(exc)},
        )
    project = payload.get("project", {})
    if not isinstance(project, Mapping):
        return OperationCheck(
            "dependency_inventory",
            "error",
            "pyproject project table is invalid.",
        )
    runtime = project.get("dependencies", [])
    optional = project.get("optional-dependencies", {})
    runtime_count = len(runtime) if isinstance(runtime, list) else 0
    optional_count = (
        sum(len(value) for value in optional.values()) if isinstance(optional, dict) else 0
    )
    return OperationCheck(
        "dependency_inventory",
        "ok",
        "Dependency inventory parsed from pyproject.toml.",
        {"runtime_dependencies": runtime_count, "optional_dependencies": optional_count},
    )


def _secret_scan_check(repo_root: Path) -> OperationCheck:
    findings: list[dict[str, object]] = []
    for path in _iter_repo_text_files(repo_root):
        relative = path.relative_to(repo_root).as_posix()
        if relative in SECRET_FILE_EXCLUDES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in SECRET_PATTERNS):
                findings.append({"path": relative, "line": line_number})
    status = "ok" if not findings else "error"
    message = (
        "No high-confidence committed secrets found."
        if not findings
        else "Potential secrets found."
    )
    return OperationCheck("secret_scan", status, message, {"findings": findings})


def _iter_repo_text_files(repo_root: Path) -> Iterable[Path]:
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        parts = set(path.relative_to(repo_root).parts)
        if parts & SECRET_PATH_EXCLUDES:
            continue
        if path.stat().st_size > 250_000:
            continue
        allowed_suffixes = {
            "",
            ".cfg",
            ".ini",
            ".json",
            ".md",
            ".py",
            ".toml",
            ".txt",
            ".yml",
            ".yaml",
        }
        if path.suffix.lower() not in allowed_suffixes:
            continue
        yield path


def _gitignore_check(path: Path) -> OperationCheck:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return OperationCheck(
            "gitignore",
            "error",
            ".gitignore could not be read.",
            {"error": str(exc)},
        )
    required = {".env", "data/", "logs/"}
    missing = sorted(item for item in required if item not in text)
    status = "ok" if not missing else "warning"
    message = (
        "Runtime and secret patterns are ignored."
        if not missing
        else "Some ignore patterns are missing."
    )
    return OperationCheck("gitignore", status, message, {"missing": missing})


def _overall_status(checks: Iterable[OperationCheck]) -> str:
    statuses = {check.status for check in checks}
    if "error" in statuses:
        return "error"
    if "warning" in statuses:
        return "warning"
    return "ok"


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
