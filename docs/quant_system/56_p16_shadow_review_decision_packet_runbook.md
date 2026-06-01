# P16 Shadow Review Decision Packet Runbook

Date: 2026-06-02

## Purpose

P16 turns P15 shadow analytics operational reviews into review-only decision
packets. It records the next operator workflow step for each reviewed shadow
group: continue observation, request more data, open a research follow-up, or
deprioritize the group.

P16 is not a promotion, scoring, scheduler, watchlist, or trading workflow. The
decision packet is manual research workflow evidence only and must not be
interpreted as production approval.

## Generate Decision Artifacts

```bash
stock-research p16-shadow-review-decisions \
  --p15-review-json outputs/p15/operator_shadow_analytics_review_2026-06-30_2026-08-29.json \
  --run-id p16-shadow-review-decisions-2026-08-29 \
  --decision-date 2026-08-29 \
  --operator-id operator \
  --output-dir outputs/p16
```

Expected output lines:

```text
p16_shadow_review_decisions|status|...
p16_shadow_review_decisions|groups|...
p16_shadow_review_decisions|json|...
p16_shadow_review_decisions|groups_csv|...
p16_shadow_review_decisions|markdown|...
```

## Import Decision Read Model

Import one artifact or a directory:

```bash
stock-research p16-import-shadow-review-decisions \
  --path outputs/p16 \
  --service stock_research
```

Expected output lines:

```text
p16_import_shadow_review_decisions|imported|...
p16_import_shadow_review_decisions|groups|...
p16_import_shadow_review_decisions|runs|...
```

The importer uses idempotent upserts into
`ops.operator_shadow_review_decision_run` and
`ops.operator_shadow_review_decision_group`.

## Dashboard Endpoint

Start the API:

```bash
stock-research dashboard-api --host 127.0.0.1 --port 8765
```

Read-only endpoint:

```text
GET /api/shadow-review-decisions?start_date=2026-06-30&end_date=2026-08-29&limit=20
```

The dashboard surface is read-only. It must not add promotion buttons,
watchlist write buttons, score mutation controls, trade controls, broker
controls, order UI, or scheduler automation controls.

## Synthetic Smoke

Run from a source checkout:

```bash
rm -rf /tmp/stock_research_p16_smoke
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p16_smoke import build_p16_shadow_review_decisions_smoke
result = build_p16_shadow_review_decisions_smoke(Path('/tmp/stock_research_p16_smoke'))
print(f"p16_smoke|p15_shadow_analytics_review|{result['p15_shadow_analytics_review_json_path']}")
print(f"p16_smoke|p16_shadow_review_decisions|{result['p16_shadow_review_decisions_json_path']}")
print(f"p16_smoke|groups_csv|{result['p16_shadow_review_decisions_groups_csv_path']}")
print(f"p16_smoke|markdown|{result['p16_shadow_review_decisions_markdown_path']}")
print(f"p16_smoke|source_group_count|{result['source_group_count']}")
print(f"p16_smoke|decision_group_count|{result['decision_group_count']}")
print(f"p16_smoke|read_model_groups|{result['read_model_group_count']}")
print(f"p16_smoke|decision_statuses|{','.join(result['decision_statuses'])}")
print(f"p16_smoke|decision_buckets|{','.join(result['decision_buckets'])}")
print(f"p16_smoke|source_p15_review_runs|{','.join(result['source_p15_review_run_ids'])}")
print(f"p16_smoke|group_keys|{','.join(result['group_keys'])}")
print(f"p16_smoke|manual_review_required|{result['manual_review_required']}")
print(f"p16_smoke|auto_trade_enabled|{result['auto_trade_enabled']}")
print(f"p16_smoke|production_watchlist_enabled|{result['production_watchlist_enabled']}")
print(f"p16_smoke|production_write_enabled|{result['production_write_enabled']}")
PY
```

Observed smoke output:

```text
p16_smoke|p15_shadow_analytics_review|/tmp/stock_research_p16_smoke/p15/operator_shadow_analytics_review_2026-06-30_2026-08-29.json
p16_smoke|p16_shadow_review_decisions|/tmp/stock_research_p16_smoke/p16/operator_shadow_review_decisions_2026-08-29.json
p16_smoke|groups_csv|/tmp/stock_research_p16_smoke/p16/operator_shadow_review_decisions_2026-08-29_groups.csv
p16_smoke|markdown|/tmp/stock_research_p16_smoke/p16/operator_shadow_review_decisions_2026-08-29.md
p16_smoke|source_group_count|1
p16_smoke|decision_group_count|1
p16_smoke|read_model_groups|1
p16_smoke|decision_statuses|request_more_data
p16_smoke|decision_buckets|data_needed
p16_smoke|source_p15_review_runs|p15-smoke-shadow-analytics-review-2026-06-30-2026-08-29
p16_smoke|group_keys|trend_shadow|shadow_ready
p16_smoke|manual_review_required|True
p16_smoke|auto_trade_enabled|False
p16_smoke|production_watchlist_enabled|False
p16_smoke|production_write_enabled|False
```

## Safety Notes

- `manual_review_required` must remain `true`.
- `auto_trade_enabled` must remain `false`.
- `production_watchlist_enabled` must remain `false`.
- `production_write_enabled` must remain `false`.
- P16 must not write production watchlist, scoring, scheduler, broker, order,
  account, execution, cash, position, or trading state.
- P16 decision statuses are manual workflow notes only and are not production
  approval.
