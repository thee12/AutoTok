"""Filesystem storage for Phase 13 analytics feedback artifacts."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, TypeVar

from autotok.analytics_models import (
    ExperimentAssignment,
    ExperimentDefinition,
    PerformanceRecord,
    TemplateVariant,
)
from autotok.errors import PersistenceError, UserInputError

ANALYTICS_DIRNAME = "analytics"


class _JsonRecord(Protocol):
    def to_dict(self) -> dict[str, object]: ...


_RecordT = TypeVar("_RecordT", bound=_JsonRecord)


class AnalyticsStore:
    """Store analytics records, experiments, assignments, and templates."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.analytics_dir = data_dir / ANALYTICS_DIRNAME
        self.performance_dir = self.analytics_dir / "performance"
        self.experiments_dir = self.analytics_dir / "experiments"
        self.assignments_dir = self.analytics_dir / "assignments"
        self.templates_dir = self.analytics_dir / "templates"

    def save_template(self, template: TemplateVariant) -> TemplateVariant:
        return self._save(
            self.templates_dir / template.template_id / "template.json",
            template,
            f"Could not write template variant: {template.template_id}",
        )

    def load_template(self, template_id: str) -> TemplateVariant:
        return self._load_template(self.templates_dir / template_id / "template.json")

    def list_templates(self) -> tuple[TemplateVariant, ...]:
        return tuple(
            self._load_template(path)
            for path in sorted(self.templates_dir.glob("template_*/template.json"))
        )

    def save_experiment(self, experiment: ExperimentDefinition) -> ExperimentDefinition:
        return self._save(
            self.experiments_dir / experiment.experiment_id / "experiment.json",
            experiment,
            f"Could not write experiment: {experiment.experiment_id}",
        )

    def load_experiment(self, experiment_id: str) -> ExperimentDefinition:
        return self._load_experiment(self.experiments_dir / experiment_id / "experiment.json")

    def list_experiments(self) -> tuple[ExperimentDefinition, ...]:
        return tuple(
            self._load_experiment(path)
            for path in sorted(self.experiments_dir.glob("experiment_*/experiment.json"))
        )

    def save_assignment(self, assignment: ExperimentAssignment) -> ExperimentAssignment:
        return self._save(
            self.assignments_dir / assignment.assignment_id / "assignment.json",
            assignment,
            f"Could not write experiment assignment: {assignment.assignment_id}",
        )

    def list_assignments(self) -> tuple[ExperimentAssignment, ...]:
        return tuple(
            self._load_assignment(path)
            for path in sorted(self.assignments_dir.glob("assignment_*/assignment.json"))
        )

    def assignment_for_render(
        self,
        render_id: str,
        *,
        experiment_id: str | None = None,
    ) -> ExperimentAssignment | None:
        for assignment in self.list_assignments():
            if assignment.render_id != render_id:
                continue
            if experiment_id is not None and assignment.experiment_id != experiment_id:
                continue
            return assignment
        return None

    def save_performance(self, record: PerformanceRecord) -> PerformanceRecord:
        return self._save(
            self.performance_dir / record.performance_id / "performance.json",
            record,
            f"Could not write performance record: {record.performance_id}",
        )

    def list_performance(self) -> tuple[PerformanceRecord, ...]:
        return tuple(
            self._load_performance(path)
            for path in sorted(self.performance_dir.glob("performance_*/performance.json"))
        )

    def _load_template(self, path: Path) -> TemplateVariant:
        payload = self._read_payload(path, "Template variant was not found.")
        try:
            return TemplateVariant.from_dict(payload)
        except ValueError as exc:
            raise PersistenceError(f"Could not load template variant: {path}") from exc

    def _load_experiment(self, path: Path) -> ExperimentDefinition:
        payload = self._read_payload(path, "Experiment was not found.")
        try:
            return ExperimentDefinition.from_dict(payload)
        except ValueError as exc:
            raise PersistenceError(f"Could not load experiment: {path}") from exc

    def _load_assignment(self, path: Path) -> ExperimentAssignment:
        payload = self._read_payload(path, "Experiment assignment was not found.")
        try:
            return ExperimentAssignment.from_dict(payload)
        except ValueError as exc:
            raise PersistenceError(f"Could not load experiment assignment: {path}") from exc

    def _load_performance(self, path: Path) -> PerformanceRecord:
        payload = self._read_payload(path, "Performance record was not found.")
        try:
            return PerformanceRecord.from_dict(payload)
        except ValueError as exc:
            raise PersistenceError(f"Could not load performance record: {path}") from exc

    def _read_payload(self, path: Path, missing_message: str) -> dict[str, object]:
        if not path.exists():
            raise UserInputError(missing_message)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PersistenceError(f"Could not read analytics artifact: {path}") from exc
        if not isinstance(payload, dict):
            raise PersistenceError(f"Analytics artifact must be an object: {path}")
        return payload

    def _save(self, path: Path, record: _RecordT, error_message: str) -> _RecordT:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_json(path, record.to_dict())
        except OSError as exc:
            raise PersistenceError(error_message) from exc
        return record


def utc_timestamp() -> str:
    """Return a UTC timestamp for analytics artifacts."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    """Create a compact local analytics identifier."""
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)
