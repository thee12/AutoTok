# Analytics Feedback

Phase 13 adds local analytics feedback, experiment tracking, and reusable content template variants. It is designed to help an operator compare recorded outcomes without changing AutoTok's human-review and platform-compliance boundaries.

## Scope

In scope:

- local template variants for hooks, outros, captions, hashtags, and subtitle-theme labels
- local experiment definitions with at least two template variants and one primary metric
- render-to-variant assignments for completed render packages
- manually supplied or officially exported performance records
- local reports with metric totals, averages, experiment summaries, and recommendations
- human-reviewed recommendations only

Out of scope:

- fake engagement, engagement manipulation, comments, messages, follows, or likes
- scraping analytics dashboards or bypassing official platform controls
- automatic publication changes based on metrics
- guaranteed-growth claims
- automatic content rewriting or template application
- real analytics-provider API integrations

`--source official_export` means the operator supplied an export obtained through an approved official surface. AutoTok does not fetch that export in Phase 13.

## Commands

Create template variants:

```bash
autotok analytics template create --name "Fast hook" --hook "Wait until you hear this" --hashtag storytime --json
autotok analytics template list
autotok analytics template inspect template_0123456789abcdef
```

Create an experiment from existing template variants:

```bash
autotok analytics experiment create --name "Hook test" --hypothesis "A direct hook improves completion" --primary-metric completions --variant-id template_a --variant-id template_b
```

Assign a completed render to a variant:

```bash
autotok analytics experiment assign experiment_0123456789abcdef template_0123456789abcdef render_0123456789abcdef
```

Import local metrics for a render:

```bash
autotok analytics import render_0123456789abcdef --provider tiktok --source manual --metric views=1200 --metric completions=430
```

Build a report:

```bash
autotok analytics report --json
```

## Runtime Data

Analytics artifacts are stored under:

```text
data/analytics/
```

The directory contains:

- `templates/template_<id>/template.json`
- `experiments/experiment_<id>/experiment.json`
- `assignments/assignment_<id>/assignment.json`
- `performance/performance_<id>/performance.json`

These files are local runtime data and are included in backup, restore, and metrics snapshots when they live under the configured data directory.

## Recommendations

Recommendations are report output, not automation. They identify a leading variant when recorded samples exist or ask the operator to collect more data. The suggested action always requires human review before reuse and does not alter rendering, review, publishing, or scheduling behavior.