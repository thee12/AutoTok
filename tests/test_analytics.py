from __future__ import annotations

import json
from pathlib import Path

import pytest

from autotok.analytics import (
    assign_experiment_variant,
    build_analytics_report,
    create_experiment,
    create_template_variant,
    import_performance_record,
    parse_metric_pairs,
)
from autotok.analytics_storage import AnalyticsStore
from autotok.cli import main
from autotok.errors import UserInputError
from tests.test_review import _create_render


def test_analytics_records_experiment_metrics_and_recommendations(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    store = AnalyticsStore(data_dir)
    render_id = _create_render(tmp_path)
    variant_a = create_template_variant(
        store,
        name="Question hook",
        hook="What would you do next?",
        hashtags=("#story",),
    )
    variant_b = create_template_variant(
        store,
        name="Direct hook",
        hook="This changed everything.",
        subtitle_theme="bold",
    )
    experiment = create_experiment(
        store,
        name="Hook comparison",
        hypothesis="A direct hook improves completion rate.",
        primary_metric="completion_rate",
        variant_ids=(variant_a.template_id, variant_b.template_id),
    )
    assignment = assign_experiment_variant(
        store,
        data_dir=data_dir,
        experiment_id=experiment.experiment_id,
        template_id=variant_b.template_id,
        render_id=render_id,
    )
    record = import_performance_record(
        store,
        data_dir=data_dir,
        render_id=render_id,
        provider="manual_export",
        metrics={"views": 1200, "completion_rate": 0.74, "cost_usd": 1.25},
    )
    report = build_analytics_report(store)

    assert assignment.template_id == variant_b.template_id
    assert record.experiment_id == experiment.experiment_id
    assert record.template_id == variant_b.template_id
    assert report.metric_totals["views"] == 1200
    assert report.metric_totals["cost_usd"] == 1.25
    assert report.experiment_summaries[0]["best_template_id"] == variant_b.template_id
    assert report.recommendations[0].template_id == variant_b.template_id
    assert "Human-review" in report.recommendations[0].suggested_action


def test_assignment_is_idempotent_and_rejects_variant_mismatch(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    store = AnalyticsStore(data_dir)
    render_id = _create_render(tmp_path)
    first = create_template_variant(store, name="First", hook="First hook")
    second = create_template_variant(store, name="Second", hook="Second hook")
    experiment = create_experiment(
        store,
        name="Hook test",
        hypothesis="Different hooks produce different outcomes.",
        primary_metric="views",
        variant_ids=(first.template_id, second.template_id),
    )

    assignment = assign_experiment_variant(
        store,
        data_dir=data_dir,
        experiment_id=experiment.experiment_id,
        template_id=first.template_id,
        render_id=render_id,
    )
    repeated = assign_experiment_variant(
        store,
        data_dir=data_dir,
        experiment_id=experiment.experiment_id,
        template_id=first.template_id,
        render_id=render_id,
    )

    assert repeated.assignment_id == assignment.assignment_id
    with pytest.raises(UserInputError, match="different variant"):
        assign_experiment_variant(
            store,
            data_dir=data_dir,
            experiment_id=experiment.experiment_id,
            template_id=second.template_id,
            render_id=render_id,
        )
    with pytest.raises(UserInputError, match="different variant"):
        import_performance_record(
            store,
            data_dir=data_dir,
            render_id=render_id,
            provider="manual",
            metrics={"views": 10},
            experiment_id=experiment.experiment_id,
            template_id=second.template_id,
        )


def test_metric_pair_validation_rejects_invalid_input() -> None:
    assert parse_metric_pairs(("views=10", "completion-rate=0.5")) == {
        "views": 10.0,
        "completion_rate": 0.5,
    }
    with pytest.raises(Exception, match="name=value"):
        parse_metric_pairs(("views",))
    with pytest.raises(Exception, match="must not be negative"):
        parse_metric_pairs(("views=-1",))


def test_analytics_cli_smoke_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_dir = tmp_path / "data"
    render_id = _create_render(tmp_path)

    main(
        [
            "--data-dir",
            str(data_dir),
            "analytics",
            "template",
            "create",
            "--name",
            "A",
            "--hook",
            "Hook A",
            "--json",
        ]
    )
    variant_a = json.loads(capsys.readouterr().out)
    main(
        [
            "--data-dir",
            str(data_dir),
            "analytics",
            "template",
            "create",
            "--name",
            "B",
            "--hook",
            "Hook B",
            "--json",
        ]
    )
    variant_b = json.loads(capsys.readouterr().out)
    main(
        [
            "--data-dir",
            str(data_dir),
            "analytics",
            "experiment",
            "create",
            "--name",
            "CLI test",
            "--hypothesis",
            "B improves views.",
            "--primary-metric",
            "views",
            "--variant-id",
            variant_a["template_id"],
            "--variant-id",
            variant_b["template_id"],
            "--json",
        ]
    )
    experiment = json.loads(capsys.readouterr().out)
    main(
        [
            "--data-dir",
            str(data_dir),
            "analytics",
            "experiment",
            "assign",
            experiment["experiment_id"],
            variant_b["template_id"],
            render_id,
            "--json",
        ]
    )
    assignment = json.loads(capsys.readouterr().out)
    import_exit = main(
        [
            "--data-dir",
            str(data_dir),
            "analytics",
            "import",
            render_id,
            "--provider",
            "manual",
            "--metric",
            "views=42",
            "--metric",
            "cost_usd=0.5",
            "--json",
        ]
    )
    performance = json.loads(capsys.readouterr().out)
    report_exit = main(["--data-dir", str(data_dir), "analytics", "report", "--json"])
    report = json.loads(capsys.readouterr().out)

    assert assignment["template_id"] == variant_b["template_id"]
    assert import_exit == 0
    assert performance["experiment_id"] == experiment["experiment_id"]
    assert performance["template_id"] == variant_b["template_id"]
    assert report_exit == 0
    assert report["performance_count"] == 1
    assert report["metric_totals"]["views"] == 42
