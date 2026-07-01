"""Analytics feedback and experiment models for Phase 13."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

ANALYTICS_SCHEMA_VERSION = 1


class AnalyticsSource(StrEnum):
    """Where a content performance record came from."""

    MANUAL = "manual"
    OFFICIAL_EXPORT = "official_export"


class ExperimentStatus(StrEnum):
    """Experiment lifecycle states."""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class RecommendationConfidence(StrEnum):
    """Coarse confidence for human-reviewed recommendations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class TemplateVariant:
    """Reusable local content template variant."""

    template_id: str
    name: str
    description: str
    created_at: str
    hook: str = ""
    outro: str = ""
    caption_template: str = ""
    hashtags: tuple[str, ...] = ()
    subtitle_theme: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = ANALYTICS_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "template_id": self.template_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "hook": self.hook,
            "outro": self.outro,
            "caption_template": self.caption_template,
            "hashtags": list(self.hashtags),
            "subtitle_theme": self.subtitle_theme,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> TemplateVariant:
        schema_version = _required_int(data, "schema_version")
        if schema_version != ANALYTICS_SCHEMA_VERSION:
            raise ValueError(f"Unsupported analytics schema_version: {schema_version}")
        hashtags = data.get("hashtags", [])
        metadata = data.get("metadata", {})
        if not isinstance(hashtags, Sequence) or isinstance(hashtags, str):
            raise ValueError("hashtags must be a list.")
        if not isinstance(metadata, Mapping):
            raise ValueError("metadata must be an object.")
        return cls(
            schema_version=schema_version,
            template_id=_required_str(data, "template_id"),
            name=_required_str(data, "name"),
            description=_optional_str(data, "description") or "",
            created_at=_required_str(data, "created_at"),
            hook=_optional_str(data, "hook") or "",
            outro=_optional_str(data, "outro") or "",
            caption_template=_optional_str(data, "caption_template") or "",
            hashtags=tuple(str(item) for item in hashtags if str(item).strip()),
            subtitle_theme=_optional_str(data, "subtitle_theme") or "",
            metadata=dict(metadata),
        )


@dataclass(frozen=True, slots=True)
class ExperimentDefinition:
    """A local experiment definition for comparing template variants."""

    experiment_id: str
    name: str
    hypothesis: str
    primary_metric: str
    variant_ids: tuple[str, ...]
    created_at: str
    updated_at: str
    status: ExperimentStatus = ExperimentStatus.DRAFT
    notes: str = ""
    schema_version: int = ANALYTICS_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "name": self.name,
            "hypothesis": self.hypothesis,
            "primary_metric": self.primary_metric,
            "variant_ids": list(self.variant_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status.value,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ExperimentDefinition:
        schema_version = _required_int(data, "schema_version")
        if schema_version != ANALYTICS_SCHEMA_VERSION:
            raise ValueError(f"Unsupported analytics schema_version: {schema_version}")
        variant_ids = data.get("variant_ids", [])
        if not isinstance(variant_ids, Sequence) or isinstance(variant_ids, str):
            raise ValueError("variant_ids must be a list.")
        try:
            status = ExperimentStatus(_required_str(data, "status"))
        except ValueError as exc:
            raise ValueError("experiment status is unsupported.") from exc
        return cls(
            schema_version=schema_version,
            experiment_id=_required_str(data, "experiment_id"),
            name=_required_str(data, "name"),
            hypothesis=_required_str(data, "hypothesis"),
            primary_metric=_required_str(data, "primary_metric"),
            variant_ids=tuple(str(item) for item in variant_ids if str(item).strip()),
            created_at=_required_str(data, "created_at"),
            updated_at=_required_str(data, "updated_at"),
            status=status,
            notes=_optional_str(data, "notes") or "",
        )


@dataclass(frozen=True, slots=True)
class ExperimentAssignment:
    """Assignment of one render to one experiment variant."""

    assignment_id: str
    experiment_id: str
    template_id: str
    render_id: str
    assigned_at: str
    notes: str = ""
    schema_version: int = ANALYTICS_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "assignment_id": self.assignment_id,
            "experiment_id": self.experiment_id,
            "template_id": self.template_id,
            "render_id": self.render_id,
            "assigned_at": self.assigned_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ExperimentAssignment:
        schema_version = _required_int(data, "schema_version")
        if schema_version != ANALYTICS_SCHEMA_VERSION:
            raise ValueError(f"Unsupported analytics schema_version: {schema_version}")
        return cls(
            schema_version=schema_version,
            assignment_id=_required_str(data, "assignment_id"),
            experiment_id=_required_str(data, "experiment_id"),
            template_id=_required_str(data, "template_id"),
            render_id=_required_str(data, "render_id"),
            assigned_at=_required_str(data, "assigned_at"),
            notes=_optional_str(data, "notes") or "",
        )


@dataclass(frozen=True, slots=True)
class PerformanceRecord:
    """Imported content performance metrics for one render."""

    performance_id: str
    render_id: str
    provider: str
    source: AnalyticsSource
    captured_at: str
    metrics: Mapping[str, float]
    imported_at: str
    experiment_id: str | None = None
    template_id: str | None = None
    publication_id: str | None = None
    notes: str = ""
    schema_version: int = ANALYTICS_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "performance_id": self.performance_id,
            "render_id": self.render_id,
            "provider": self.provider,
            "source": self.source.value,
            "captured_at": self.captured_at,
            "metrics": dict(self.metrics),
            "imported_at": self.imported_at,
            "experiment_id": self.experiment_id,
            "template_id": self.template_id,
            "publication_id": self.publication_id,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> PerformanceRecord:
        schema_version = _required_int(data, "schema_version")
        if schema_version != ANALYTICS_SCHEMA_VERSION:
            raise ValueError(f"Unsupported analytics schema_version: {schema_version}")
        metrics = data.get("metrics")
        if not isinstance(metrics, Mapping):
            raise ValueError("metrics must be an object.")
        try:
            source = AnalyticsSource(_required_str(data, "source"))
        except ValueError as exc:
            raise ValueError("analytics source is unsupported.") from exc
        return cls(
            schema_version=schema_version,
            performance_id=_required_str(data, "performance_id"),
            render_id=_required_str(data, "render_id"),
            provider=_required_str(data, "provider"),
            source=source,
            captured_at=_required_str(data, "captured_at"),
            metrics={str(key): _coerce_float(value, str(key)) for key, value in metrics.items()},
            imported_at=_required_str(data, "imported_at"),
            experiment_id=_optional_str(data, "experiment_id"),
            template_id=_optional_str(data, "template_id"),
            publication_id=_optional_str(data, "publication_id"),
            notes=_optional_str(data, "notes") or "",
        )


@dataclass(frozen=True, slots=True)
class AnalyticsRecommendation:
    """A human-reviewed recommendation derived from local measurements."""

    recommendation_id: str
    title: str
    rationale: str
    suggested_action: str
    confidence: RecommendationConfidence
    created_at: str
    experiment_id: str | None = None
    template_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "recommendation_id": self.recommendation_id,
            "title": self.title,
            "rationale": self.rationale,
            "suggested_action": self.suggested_action,
            "confidence": self.confidence.value,
            "created_at": self.created_at,
            "experiment_id": self.experiment_id,
            "template_id": self.template_id,
        }


def _required_str(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string.")
    return value


def _optional_str(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null.")
    return value or None


def _required_int(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer.")
    return value


def _coerce_float(value: object, key: str) -> float:
    if isinstance(value, int | float):
        return float(value)
    raise ValueError(f"metric {key} must be numeric.")
