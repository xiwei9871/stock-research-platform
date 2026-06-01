# P14 Shadow Outcome Analytics Runbook

Date: 2026-06-01

## Purpose

P14 summarizes P13 shadow watchlist outcomes by `shadow_layer` and
`shadow_status`. It produces review-only JSON, CSV, and Markdown artifacts,
imports those artifacts into independent `ops` read-model tables, and exposes a
read-only dashboard summary.

P14 does not rank individual candidates, recommend promotion, write production
watchlist signals, mutate factor scores, schedule jobs, place orders, or create
broker/account/execution state.

## Generate Analytics Artifacts

```bash
stock-research p14-shadow-outcome-analytics \
  --shadow-outcomes-json outputs/p13/2026-08-29/operator_shadow_outcomes_2026-08-29.json \
  --run-id p14-shadow-outcome-analytics-2026-06-30-2026-08-29 \
  --review-start-date 2026-06-30 \
  --review-end-date 2026-08-29 \
  --output-dir outputs/p14/2026-08-29
```

Expected output lines:

```text
p14_shadow_outcome_analytics|status|...
p14_shadow_outcome_analytics|source_outcomes|...
p14_shadow_outcome_analytics|groups|...
p14_shadow_outcome_analytics|json|...
p14_shadow_outcome_analytics|groups_csv|...
p14_shadow_outcome_analytics|markdown|...
```

## Import Analytics Read Model

Import one artifact:

```bash
stock-research p14-import-shadow-outcome-analytics \
  --path outputs/p14/2026-08-29/operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json
```

Import a directory:

```bash
stock-research p14-import-shadow-outcome-analytics \
  --path outputs/p14/2026-08-29
```

Expected output lines:

```text
p14_shadow_outcome_analytics_import|imported|...
p14_shadow_outcome_analytics_import|groups|...
p14_shadow_outcome_analytics_import|run_id|...
```

The importer uses idempotent upserts into
`ops.operator_shadow_watchlist_outcome_analytics_run` and
`ops.operator_shadow_watchlist_outcome_analytics_group`.

## Dashboard Endpoint

Start the API:

```bash
stock-research dashboard-api --host 127.0.0.1 --port 8765
```

Read-only endpoint:

```text
GET /api/shadow-outcome-analytics
```

Start the frontend:

```bash
cd dashboard
pnpm dev
```

Review the Shadow Outcome Analytics panel. It has no promotion buttons,
watchlist write buttons, score mutation buttons, trade buttons, broker controls,
order UI, or scheduler automation controls.

## Synthetic Smoke

Run:

```bash
rm -rf /tmp/stock_research_p14_smoke
.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p14_smoke import build_p14_shadow_outcome_analytics_smoke
result = build_p14_shadow_outcome_analytics_smoke(Path('/tmp/stock_research_p14_smoke'))
print(f"p14_smoke|p13_shadow_outcome|{result['p13_shadow_outcome_json_path']}")
print(f"p14_smoke|p14_shadow_outcome_analytics|{result['p14_shadow_outcome_analytics_json_path']}")
print(f"p14_smoke|groups_csv|{result['p14_shadow_outcome_analytics_groups_csv_path']}")
print(f"p14_smoke|markdown|{result['p14_shadow_outcome_analytics_markdown_path']}")
print(f"p14_smoke|source_outcome_count|{result['source_outcome_count']}")
print(f"p14_smoke|group_count|{result['group_count']}")
print(f"p14_smoke|read_model_groups|{result['read_model_group_count']}")
print(f"p14_smoke|group_keys|{','.join(result['group_keys'])}")
print(f"p14_smoke|sample_counts|{','.join(str(value) for value in result['sample_counts'])}")
print(f"p14_smoke|complete_counts|{','.join(str(value) for value in result['complete_counts'])}")
print(f"p14_smoke|insufficient_data_counts|{','.join(str(value) for value in result['insufficient_data_counts'])}")
print(f"p14_smoke|manual_review_required|{result['manual_review_required']}")
print(f"p14_smoke|auto_trade_enabled|{result['auto_trade_enabled']}")
print(f"p14_smoke|production_watchlist_enabled|{result['production_watchlist_enabled']}")
print(f"p14_smoke|production_write_enabled|{result['production_write_enabled']}")
PY
```

Observed smoke output:

```text
p14_smoke|p13_shadow_outcome|/tmp/stock_research_p14_smoke/p13/operator_shadow_outcomes_2026-08-29.json
p14_smoke|p14_shadow_outcome_analytics|/tmp/stock_research_p14_smoke/p14/operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json
p14_smoke|groups_csv|/tmp/stock_research_p14_smoke/p14/operator_shadow_outcome_analytics_2026-06-30_2026-08-29_groups.csv
p14_smoke|markdown|/tmp/stock_research_p14_smoke/p14/operator_shadow_outcome_analytics_2026-06-30_2026-08-29.md
p14_smoke|source_outcome_count|1
p14_smoke|group_count|1
p14_smoke|read_model_groups|1
p14_smoke|group_keys|trend_shadow|shadow_ready
p14_smoke|sample_counts|1
p14_smoke|complete_counts|1
p14_smoke|insufficient_data_counts|0
p14_smoke|manual_review_required|True
p14_smoke|auto_trade_enabled|False
p14_smoke|production_watchlist_enabled|False
p14_smoke|production_write_enabled|False
```

## Safety Notes

- `manual_review_required` must remain `true`.
- `auto_trade_enabled` must remain `false`.
- `production_watchlist_enabled` must remain `false`.
- `production_write_enabled` must remain `false`.
- P14 artifacts are review evidence only and are not production approval.
