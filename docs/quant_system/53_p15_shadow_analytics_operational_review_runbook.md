# P15 Shadow Analytics Operational Review Runbook

Date: 2026-06-02

## Purpose

P15 turns P14 shadow outcome analytics into a review-only operational packet.
It records conservative group-level review status, evidence notes, risk notes,
and next research questions for `shadow_layer` and `shadow_status` groups.

P15 is not a promotion, scoring, scheduler, watchlist, or trading workflow. The
review packet is manual research evidence only and must not be interpreted as
production approval.

## Generate Review Artifacts

```bash
stock-research p15-shadow-analytics-review \
  --p14-analytics-json outputs/p14/operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json \
  --run-id p15-shadow-analytics-review-2026-06-30-2026-08-29 \
  --review-start-date 2026-06-30 \
  --review-end-date 2026-08-29 \
  --reviewer-id operator \
  --output-dir outputs/p15
```

Expected output lines:

```text
p15_shadow_analytics_review|status|...
p15_shadow_analytics_review|groups|...
p15_shadow_analytics_review|json|...
p15_shadow_analytics_review|groups_csv|...
p15_shadow_analytics_review|markdown|...
```

## Import Review Read Model

Import one artifact or a directory:

```bash
stock-research p15-import-shadow-analytics-review \
  --path outputs/p15 \
  --service stock_research
```

Expected output lines:

```text
p15_import_shadow_analytics_review|imported|...
p15_import_shadow_analytics_review|groups|...
p15_import_shadow_analytics_review|runs|...
```

The importer uses idempotent upserts into
`ops.operator_shadow_analytics_review_run` and
`ops.operator_shadow_analytics_review_group`.

## Dashboard Endpoint

Start the API:

```bash
stock-research dashboard-api --host 127.0.0.1 --port 8765
```

Read-only endpoint:

```text
GET /api/shadow-analytics-review?start_date=2026-06-30&end_date=2026-08-29&limit=20
```

The dashboard surface is read-only. It must not add promotion buttons,
watchlist write buttons, score mutation controls, trade controls, broker
controls, order UI, or scheduler automation controls.

## Synthetic Smoke

Run:

```bash
rm -rf /tmp/stock_research_p15_smoke
/Users/xiwei/stock_research/.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p15_smoke import build_p15_shadow_analytics_review_smoke
result = build_p15_shadow_analytics_review_smoke(Path('/tmp/stock_research_p15_smoke'))
print(f"p15_smoke|p14_shadow_outcome_analytics|{result['p14_shadow_outcome_analytics_json_path']}")
print(f"p15_smoke|p15_shadow_analytics_review|{result['p15_shadow_analytics_review_json_path']}")
print(f"p15_smoke|groups_csv|{result['p15_shadow_analytics_review_groups_csv_path']}")
print(f"p15_smoke|markdown|{result['p15_shadow_analytics_review_markdown_path']}")
print(f"p15_smoke|source_group_count|{result['source_group_count']}")
print(f"p15_smoke|review_group_count|{result['review_group_count']}")
print(f"p15_smoke|read_model_groups|{result['read_model_group_count']}")
print(f"p15_smoke|review_statuses|{','.join(result['review_statuses'])}")
print(f"p15_smoke|review_buckets|{','.join(result['review_buckets'])}")
print(f"p15_smoke|group_keys|{','.join(result['group_keys'])}")
print(f"p15_smoke|manual_review_required|{result['manual_review_required']}")
print(f"p15_smoke|auto_trade_enabled|{result['auto_trade_enabled']}")
print(f"p15_smoke|production_watchlist_enabled|{result['production_watchlist_enabled']}")
print(f"p15_smoke|production_write_enabled|{result['production_write_enabled']}")
PY
```

Observed smoke output:

```text
p15_smoke|p14_shadow_outcome_analytics|/tmp/stock_research_p15_smoke/p14/operator_shadow_outcome_analytics_2026-06-30_2026-08-29.json
p15_smoke|p15_shadow_analytics_review|/tmp/stock_research_p15_smoke/p15/operator_shadow_analytics_review_2026-06-30_2026-08-29.json
p15_smoke|groups_csv|/tmp/stock_research_p15_smoke/p15/operator_shadow_analytics_review_2026-06-30_2026-08-29_groups.csv
p15_smoke|markdown|/tmp/stock_research_p15_smoke/p15/operator_shadow_analytics_review_2026-06-30_2026-08-29.md
p15_smoke|source_group_count|1
p15_smoke|review_group_count|1
p15_smoke|read_model_groups|1
p15_smoke|review_statuses|needs_more_data
p15_smoke|review_buckets|data_needed
p15_smoke|group_keys|trend_shadow|shadow_ready
p15_smoke|manual_review_required|True
p15_smoke|auto_trade_enabled|False
p15_smoke|production_watchlist_enabled|False
p15_smoke|production_write_enabled|False
```

## Safety Notes

- `manual_review_required` must remain `true`.
- `auto_trade_enabled` must remain `false`.
- `production_watchlist_enabled` must remain `false`.
- `production_write_enabled` must remain `false`.
- P15 must not write production watchlist, scoring, scheduler, broker, order,
  account, execution, cash, position, or trading state.
- P15 review statuses are manual research notes only and are not production
  approval.
