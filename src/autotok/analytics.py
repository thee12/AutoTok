"""Local analytics feedback workflows for Phase 13."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autotok.analytics_models import (
    AnalyticsRecommendation,
    AnalyticsSource,
    ExperimentAssignment,
    ExperimentDefinition,
    ExperimentStatus,
    PerformanceRecord,
    RecommendationConfidence,
    TemplateVariant,
)
from autotok.analytics_storage import AnalyticsStore, new_id, utc_timestamp
from autotok.errors import UserInputError
from autotok.render_storage import RenderStore


@dataclass(frozen=True, slots=True)
class AnalyticsReport:
    """A computed local analytics report."""

    generated_at: str
    performance_count: int
    experiment_count: int
    template_count: int
    metric_totals: Mapping[str, float]
    metric_averages: Mapping[str, float]
    experiment_summaries: tuple[Mapping[str, Any], ...]
    recommendations: tuple[AnalyticsRecommendation, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "performance_count": self.performance_count,
            "experiment_count": self.experiment_count,
            "template_count": self.template_count,
            "metric_totals": dict(self.metric_totals),
            "metric_averages": dict(self.metric_averages),
            "experiment_summaries": [dict(summary) for summary in self.experiment_summaries],
            "recommendations": [
                recommendation.to_dict() for recommendation in self.recommendations
            ],
        }


def create_template_variant(
    store: AnalyticsStore,
    *,
    name: str,
    description: str = "",
    hook: str = "",
    outro: str = "",
    caption_template: str = "",
    hashtags: Sequence[str] = (),
    subtitle_theme: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> TemplateVariant:
    """Create and store a reusable template variant."""
    cleaned_name = name.strip()
    if not cleaned_name:
        raise UserInputError("Template name must not be empty.")
    if (
        not any(
            value.strip() for value in (description, hook, outro, caption_template, subtitle_theme)
        )
        and not hashtags
    ):
        raise UserInputError("Template variant must define at least one reusable element.")
    template = TemplateVariant(
        template_id=new_id("template"),
        name=cleaned_name,
        description=description.strip(),
        created_at=utc_timestamp(),
        hook=hook.strip(),
        outro=outro.strip(),
        caption_template=caption_template.strip(),
        hashtags=tuple(_clean_hashtag(item) for item in hashtags if item.strip()),
        subtitle_theme=subtitle_theme.strip(),
        metadata={} if metadata is None else dict(metadata),
    )
    return store.save_template(template)


def create_experiment(
    store: AnalyticsStore,
    *,
    name: str,
    hypothesis: str,
    primary_metric: str,
    variant_ids: Sequence[str],
    notes: str = "",
) -> ExperimentDefinition:
    """Create and store a local experiment definition."""
    cleaned_name = name.strip()
    cleaned_hypothesis = hypothesis.strip()
    cleaned_metric = _clean_metric_name(primary_metric)
    variants = tuple(dict.fromkeys(item.strip() for item in variant_ids if item.strip()))
    if not cleaned_name:
        raise UserInputError("Experiment name must not be empty.")
    if not cleaned_hypothesis:
        raise UserInputError("Experiment hypothesis must not be empty.")
    if len(variants) < 2:
        raise UserInputError("Experiment must include at least two template variants.")
    for variant_id in variants:
        store.load_template(variant_id)
    timestamp = utc_timestamp()
    experiment = ExperimentDefinition(
        experiment_id=new_id("experiment"),
        name=cleaned_name,
        hypothesis=cleaned_hypothesis,
        primary_metric=cleaned_metric,
        variant_ids=variants,
        created_at=timestamp,
        updated_at=timestamp,
        status=ExperimentStatus.RUNNING,
        notes=notes.strip(),
    )
    return store.save_experiment(experiment)


def assign_experiment_variant(
    store: AnalyticsStore,
    *,
    data_dir: Path,
    experiment_id: str,
    template_id: str,
    render_id: str,
    notes: str = "",
) -> ExperimentAssignment:
    """Assign a render to one experiment template variant."""
    RenderStore(data_dir).load(render_id)
    experiment = store.load_experiment(experiment_id)
    store.load_template(template_id)
    if template_id not in experiment.variant_ids:
        raise UserInputError("Template variant is not part of this experiment.")
    existing = store.assignment_for_render(render_id, experiment_id=experiment_id)
    if existing is not None:
        if existing.template_id != template_id:
            raise UserInputError("Render is already assigned to a different variant.")
        return existing
    assignment = ExperimentAssignment(
        assignment_id=new_id("assignment"),
        experiment_id=experiment_id,
        template_id=template_id,
        render_id=render_id,
        assigned_at=utc_timestamp(),
        notes=notes.strip(),
    )
    return store.save_assignment(assignment)


def import_performance_record(
    store: AnalyticsStore,
    *,
    data_dir: Path,
    render_id: str,
    provider: str,
    metrics: Mapping[str, float],
    source: AnalyticsSource = AnalyticsSource.MANUAL,
    captured_at: str | None = None,
    experiment_id: str | None = None,
    template_id: str | None = None,
    publication_id: str | None = None,
    notes: str = "",
) -> PerformanceRecord:
    """Import manually supplied or officially exported performance metrics."""
    RenderStore(data_dir).load(render_id)
    cleaned_provider = provider.strip()
    if not cleaned_provider:
        raise UserInputError("Performance provider must not be empty.")
    cleaned_metrics = _validate_metrics(metrics)
    assignment = None
    if experiment_id is not None:
        assignment = store.assignment_for_render(render_id, experiment_id=experiment_id)
        store.load_experiment(experiment_id)
    else:
        assignment = store.assignment_for_render(render_id)
    resolved_experiment_id = experiment_id
    resolved_template_id = template_id
    if assignment is not None:
        if template_id is not None and template_id != assignment.template_id:
            raise UserInputError("Render is already assigned to a different variant.")
        resolved_experiment_id = assignment.experiment_id
        resolved_template_id = assignment.template_id
    if resolved_template_id is not None:
        store.load_template(resolved_template_id)
    if resolved_experiment_id is not None:
        experiment = store.load_experiment(resolved_experiment_id)
        if resolved_template_id is not None and resolved_template_id not in experiment.variant_ids:
            raise UserInputError("Template variant is not part of the experiment.")
    timestamp = utc_timestamp()
    record = PerformanceRecord(
        performance_id=new_id("performance"),
        render_id=render_id,
        provider=cleaned_provider,
        source=source,
        captured_at=timestamp if captured_at is None else captured_at,
        metrics=cleaned_metrics,
        imported_at=timestamp,
        experiment_id=resolved_experiment_id,
        template_id=resolved_template_id,
        publication_id=publication_id,
        notes=notes.strip(),
    )
    return store.save_performance(record)


def build_analytics_report(store: AnalyticsStore) -> AnalyticsReport:
    """Build a report from local performance, experiment, and template records."""
    performance = store.list_performance()
    experiments = store.list_experiments()
    templates = store.list_templates()
    totals = _metric_totals(performance)
    averages = (
        {key: value / len(performance) for key, value in totals.items()} if performance else {}
    )
    experiment_summaries = tuple(
        _experiment_summary(experiment, performance) for experiment in experiments
    )
    recommendations = tuple(
        _recommendations_from_summary(summary) for summary in experiment_summaries
    )
    flattened = tuple(item for group in recommendations for item in group)
    return AnalyticsReport(
        generated_at=utc_timestamp(),
        performance_count=len(performance),
        experiment_count=len(experiments),
        template_count=len(templates),
        metric_totals=totals,
        metric_averages=averages,
        experiment_summaries=experiment_summaries,
        recommendations=flattened,
    )


def parse_metric_pairs(values: Sequence[str]) -> dict[str, float]:
    """Parse CLI metric pairs formatted as name=value."""
    metrics: dict[str, float] = {}
    for value in values:
        if "=" not in value:
            raise UserInputError("Metrics must be formatted as name=value.")
        key, raw = value.split("=", 1)
        metric_name = _clean_metric_name(key)
        try:
            metric_value = float(raw)
        except ValueError as exc:
            raise UserInputError(f"Metric value must be numeric: {metric_name}") from exc
        metrics[metric_name] = metric_value
    return _validate_metrics(metrics)


def _validate_metrics(metrics: Mapping[str, float]) -> dict[str, float]:
    if not metrics:
        raise UserInputError("At least one performance metric is required.")
    cleaned: dict[str, float] = {}
    for key, value in metrics.items():
        metric_name = _clean_metric_name(key)
        metric_value = float(value)
        if metric_value < 0:
            raise UserInputError("Performance metrics must not be negative.")
        cleaned[metric_name] = metric_value
    return cleaned


def _clean_metric_name(value: str) -> str:
    cleaned = value.strip().lower().replace("-", "_").replace(" ", "_")
    if not cleaned:
        raise UserInputError("Metric name must not be empty.")
    if not all(char.isalnum() or char == "_" for char in cleaned):
        raise UserInputError("Metric names may contain only letters, numbers, and underscores.")
    return cleaned


def _clean_hashtag(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    return cleaned if cleaned.startswith("#") else f"#{cleaned}"


def _metric_totals(records: Sequence[PerformanceRecord]) -> dict[str, float]:
    totals: defaultdict[str, float] = defaultdict(float)
    for record in records:
        for key, value in record.metrics.items():
            totals[key] += value
    return dict(sorted(totals.items()))


def _experiment_summary(
    experiment: ExperimentDefinition,
    performance: Sequence[PerformanceRecord],
) -> dict[str, Any]:
    by_variant: dict[str, list[float]] = {variant_id: [] for variant_id in experiment.variant_ids}
    for record in performance:
        if record.experiment_id != experiment.experiment_id or record.template_id is None:
            continue
        metric_value = record.metrics.get(experiment.primary_metric)
        if metric_value is None:
            continue
        by_variant.setdefault(record.template_id, []).append(metric_value)
    variants: list[dict[str, object]] = []
    for variant_id, values in sorted(by_variant.items()):
        variants.append(
            {
                "template_id": variant_id,
                "sample_count": len(values),
                "average": (sum(values) / len(values)) if values else None,
                "total": sum(values),
            }
        )
    best = _best_variant(variants)
    return {
        "experiment_id": experiment.experiment_id,
        "name": experiment.name,
        "status": experiment.status.value,
        "primary_metric": experiment.primary_metric,
        "variants": variants,
        "best_template_id": best,
    }


def _best_variant(variants: Sequence[Mapping[str, object]]) -> str | None:
    best_id: str | None = None
    best_average = -1.0
    for variant in variants:
        average = variant.get("average")
        sample_count = variant.get("sample_count")
        if not isinstance(average, int | float) or not isinstance(sample_count, int):
            continue
        if sample_count <= 0:
            continue
        if float(average) > best_average:
            best_average = float(average)
            best_id = str(variant["template_id"])
    return best_id


def _recommendations_from_summary(
    summary: Mapping[str, Any],
) -> tuple[AnalyticsRecommendation, ...]:
    best_template_id = summary.get("best_template_id")
    variants = summary.get("variants", [])
    if not isinstance(best_template_id, str) or not isinstance(variants, Sequence):
        return (
            AnalyticsRecommendation(
                recommendation_id=new_id("recommendation"),
                title="Collect more experiment data",
                rationale="No variant has enough recorded performance data yet.",
                suggested_action="Keep assigning reviewed renders and importing official metrics.",
                confidence=RecommendationConfidence.LOW,
                created_at=utc_timestamp(),
                experiment_id=str(summary.get("experiment_id")),
            ),
        )
    total_samples = sum(
        int(item.get("sample_count", 0)) for item in variants if isinstance(item, Mapping)
    )
    confidence = (
        RecommendationConfidence.MEDIUM if total_samples >= 4 else RecommendationConfidence.LOW
    )
    return (
        AnalyticsRecommendation(
            recommendation_id=new_id("recommendation"),
            title="Review leading template variant",
            rationale=(
                f"Template {best_template_id} currently leads on "
                f"{summary.get('primary_metric')} across {total_samples} samples."
            ),
            suggested_action=(
                "Human-review the leading variant before reusing it; do not change "
                "publishing behavior automatically."
            ),
            confidence=confidence,
            created_at=utc_timestamp(),
            experiment_id=str(summary.get("experiment_id")),
            template_id=best_template_id,
        ),
    )
