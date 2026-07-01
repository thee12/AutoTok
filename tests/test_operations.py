from __future__ import annotations

import json
import logging
import os
import time
import zipfile
from pathlib import Path
from typing import Any, cast

import pytest

from autotok.cli import main
from autotok.config import AppConfig, ConfigError
from autotok.job_storage import JobStore
from autotok.logging import JsonFormatter
from autotok.operations import (
    audit_repository,
    build_health_report,
    build_metrics_report,
    create_backup,
    inspect_restore,
    plan_retention,
    profile_operations,
)


def test_health_and_metrics_report_local_state(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    (data_dir / "sources" / "story_example").mkdir(parents=True)
    (data_dir / "sources" / "story_example" / "record.json").write_text("{}", encoding="utf-8")
    JobStore(data_dir).create_job(story_id="story_example")

    health = build_health_report(data_dir)
    metrics = build_metrics_report(data_dir)

    assert health.status in {"ok", "warning"}
    totals = cast(dict[str, Any], metrics["totals"])
    jobs = cast(dict[str, Any], metrics["jobs"])
    job_status_counts = cast(dict[str, int], jobs["status_counts"])

    assert totals["file_count"] >= 1
    assert jobs["database_exists"] is True
    assert job_status_counts["queued"] == 1


def test_backup_and_restore_round_trip_with_dry_run(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    source_path = data_dir / "sources" / "story_example" / "record.json"
    source_path.parent.mkdir(parents=True)
    source_path.write_text('{"story_id":"story_example"}', encoding="utf-8")
    cache_path = data_dir / "cache" / "source_retrieval" / "raw.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text("{}", encoding="utf-8")
    archive_path = tmp_path / "backup.zip"

    backup = create_backup(data_dir, archive_path)
    dry_run = inspect_restore(archive_path, tmp_path / "restored", apply=False)
    restored = inspect_restore(archive_path, tmp_path / "restored", apply=True)

    backup_manifest = cast(dict[str, Any], backup["manifest"])

    assert backup_manifest["file_count"] == 1
    assert dry_run["restored"] is False
    assert restored["restored"] is True
    assert (tmp_path / "restored" / "sources" / "story_example" / "record.json").exists()
    assert not (tmp_path / "restored" / "cache").exists()


def test_restore_rejects_unsafe_archive_member(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.txt", "nope")

    with pytest.raises(Exception, match="unsafe path"):
        inspect_restore(archive_path, tmp_path / "restore", apply=False)


def test_retention_only_deletes_old_transient_files(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    old_cache = data_dir / "cache" / "old.json"
    old_cache.parent.mkdir(parents=True)
    old_cache.write_text("{}", encoding="utf-8")
    durable = data_dir / "renders" / "render_example" / "manifest.json"
    durable.parent.mkdir(parents=True)
    durable.write_text("{}", encoding="utf-8")
    old_time = time.time() - 10 * 24 * 60 * 60
    os.utime(old_cache, (old_time, old_time))
    os.utime(durable, (old_time, old_time))

    dry_run = plan_retention(data_dir, older_than_days=7)
    applied = plan_retention(data_dir, older_than_days=7, apply=True)

    assert dry_run["candidate_count"] == 1
    candidates = cast(list[str], dry_run["candidates"])

    assert str(old_cache) in candidates
    assert applied["deleted"] == [str(old_cache)]
    assert not old_cache.exists()
    assert durable.exists()


def test_audit_repository_detects_secret_like_values(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = []\n',
        encoding="utf-8",
    )
    (tmp_path / ".gitignore").write_text(".env\ndata/\nlogs/\n", encoding="utf-8")
    secret_name = "ACCESS" + "_TOKEN"
    secret_value = "abcdefghijklmnopqrstuvwxyz" + "123456"
    (tmp_path / "settings.py").write_text(
        f'{secret_name} = "{secret_value}"\\n',
        encoding="utf-8",
    )

    report = audit_repository(tmp_path)

    assert report.status == "error"
    assert report.checks[1].name == "secret_scan"
    assert report.checks[1].metadata["findings"][0]["path"] == "settings.py"


def test_profile_operations_records_timing(tmp_path: Path) -> None:
    result = profile_operations(tmp_path / "data", iterations=2)

    assert result["iterations"] == 2
    assert cast(float, result["avg_seconds"]) >= 0
    assert result["operation"] == "metrics_snapshot"


def test_ops_cli_health_metrics_backup_and_restore(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = tmp_path / "data"
    artifact = data_dir / "sources" / "story_example" / "record.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}", encoding="utf-8")
    archive = tmp_path / "backup.zip"
    restored_dir = tmp_path / "restored"

    health_exit = main(["--data-dir", str(data_dir), "ops", "health", "--json"])
    health = json.loads(capsys.readouterr().out)
    metrics_exit = main(["--data-dir", str(data_dir), "ops", "metrics", "--json"])
    metrics = json.loads(capsys.readouterr().out)
    backup_exit = main(
        ["--data-dir", str(data_dir), "ops", "backup", "--output", str(archive), "--json"]
    )
    backup = json.loads(capsys.readouterr().out)
    restore_exit = main(
        [
            "--data-dir",
            str(data_dir),
            "ops",
            "restore",
            "--archive",
            str(archive),
            "--target-data-dir",
            str(restored_dir),
            "--apply",
            "--json",
        ]
    )
    restore = json.loads(capsys.readouterr().out)

    assert health_exit in {0, 1}
    assert health["status"] in {"ok", "warning", "error"}
    assert metrics_exit == 0
    assert metrics["totals"]["file_count"] >= 1
    assert backup_exit == 0
    backup_manifest = cast(dict[str, Any], backup["manifest"])

    assert backup_manifest["file_count"] == 1
    assert restore_exit == 0
    assert restore["restored"] is True


def test_config_and_json_log_format() -> None:
    config = AppConfig.from_environment({"AUTOTOK_LOG_FORMAT": "json"})
    record = logging.LogRecord(
        "autotok.test",
        logging.INFO,
        __file__,
        10,
        "hello",
        (),
        None,
    )
    payload = json.loads(JsonFormatter().format(record))

    assert config.log_format == "json"
    assert payload["level"] == "INFO"
    assert payload["message"] == "hello"
    with pytest.raises(ConfigError, match="AUTOTOK_LOG_FORMAT"):
        AppConfig.from_environment({"AUTOTOK_LOG_FORMAT": "xml"})
