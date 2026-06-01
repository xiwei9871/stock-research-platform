# P13 Shadow Watchlist Outcome Tracking Runbook

Date: 2026-06-01

## Scope

P13 measures later market outcomes for P12 review-only shadow watchlist
candidates. It writes local JSON, CSV, and Markdown review artifacts and can
import those artifacts into independent `ops` read-model tables.

P13 does not write production watchlist signals, mutate factor scores, schedule
jobs, promote experiments, place orders, or create broker/account/execution
state.

## Review Flow

1. Generate or receive a P12 shadow watchlist artifact.
2. Prepare daily bar data covering each candidate date and the required forward
   horizons.
3. Generate P13 shadow outcome artifacts.
4. Import P13 artifacts into the `ops.operator_shadow_watchlist_outcome_*` read
   model.
5. Review the read-only dashboard Shadow Outcomes panel.
6. Treat P13 output as review evidence only.

## Daily Bar Input

Required columns:

- `asset_id`
- `trade_date`
- `close`
- `high`
- `low`

The base bar must exist on the candidate date. Outcome status is `complete`
only when enough future bars exist for the configured horizons; otherwise it is
`insufficient_data` and missing horizon metrics remain empty rather than being
zero-filled.

## Generate Shadow Outcome Artifacts

```bash
stock-research p13-shadow-outcome-review \
  --shadow-json outputs/p12/2026-06-30/operator_shadow_watchlist_2026-06-30.json \
  --bars-csv inputs/p13/daily_bars_2026-06-30_forward.csv \
  --run-id p13-shadow-outcomes-2026-07-31 \
  --review-date 2026-07-31 \
  --output-dir outputs/p13/2026-07-31
```

Expected output lines:

```text
p13_shadow_outcome|status|shadow_outcome_review_ready
p13_shadow_outcome|outcomes|...
p13_shadow_outcome|json|...
p13_shadow_outcome|details_csv|...
p13_shadow_outcome|markdown|...
```

## Import Shadow Outcome Read Model

Import one artifact:

```bash
stock-research p13-import-shadow-outcomes \
  --path outputs/p13/2026-07-31/operator_shadow_outcomes_2026-07-31.json
```

Import a directory:

```bash
stock-research p13-import-shadow-outcomes \
  --path outputs/p13/2026-07-31
```

Expected output lines:

```text
p13_shadow_outcome_import|imported|1
p13_shadow_outcome_import|candidates|...
p13_shadow_outcome_import|run_id|...
```

The importer uses idempotent upserts. Re-importing the same artifact updates
the same run and shadow outcome candidate rows.

## Dashboard Review

Start the API:

```bash
stock-research dashboard-api --host 127.0.0.1 --port 8765
```

Start the frontend:

```bash
cd dashboard
pnpm dev
```

Open the dashboard and inspect the read-only Shadow Outcomes panel.

The panel has no promotion buttons, watchlist write buttons, score mutation
buttons, trade buttons, broker controls, order UI, or scheduler automation
controls.

## Synthetic Smoke

Run:

```bash
rm -rf /tmp/stock_research_p13_smoke
.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p13_smoke import build_p13_shadow_outcome_smoke
result = build_p13_shadow_outcome_smoke(Path('/tmp/stock_research_p13_smoke'))
print(f"p13_smoke|p12_shadow|{result['p12_shadow_json_path']}")
print(f"p13_smoke|p13_shadow_outcome|{result['p13_shadow_outcome_json_path']}")
print(f"p13_smoke|details_csv|{result['p13_shadow_outcome_details_csv_path']}")
print(f"p13_smoke|markdown|{result['p13_shadow_outcome_markdown_path']}")
print(f"p13_smoke|outcome_count|{result['outcome_count']}")
print(f"p13_smoke|read_model_candidates|{result['read_model_candidate_count']}")
print(f"p13_smoke|outcome_statuses|{','.join(result['outcome_statuses'])}")
print(f"p13_smoke|source_p12_runs|{','.join(result['source_p12_shadow_run_ids'])}")
print(f"p13_smoke|source_p11_runs|{','.join(result['source_p11_replay_run_ids'])}")
print(f"p13_smoke|source_p10_runs|{','.join(result['source_p10_proposal_run_ids'])}")
print(f"p13_smoke|source_p9_runs|{','.join(result['source_p9_analytics_run_ids'])}")
print(f"p13_smoke|manual_review_required|{result['manual_review_required']}")
print(f"p13_smoke|auto_trade_enabled|{result['auto_trade_enabled']}")
print(f"p13_smoke|production_watchlist_enabled|{result['production_watchlist_enabled']}")
print(f"p13_smoke|production_write_enabled|{result['production_write_enabled']}")
PY
```

Observed smoke output:

```text
p13_smoke|p12_shadow|/tmp/stock_research_p13_smoke/p12/operator_shadow_watchlist_2026-06-30.json
p13_smoke|p13_shadow_outcome|/tmp/stock_research_p13_smoke/p13/operator_shadow_outcomes_2026-08-29.json
p13_smoke|details_csv|/tmp/stock_research_p13_smoke/p13/operator_shadow_outcomes_2026-08-29_details.csv
p13_smoke|markdown|/tmp/stock_research_p13_smoke/p13/operator_shadow_outcomes_2026-08-29.md
p13_smoke|outcome_count|1
p13_smoke|read_model_candidates|1
p13_smoke|outcome_statuses|complete
p13_smoke|source_p12_runs|p12-smoke-shadow-watchlist-2026-06-30
p13_smoke|source_p11_runs|p11-smoke-replay-2026-06-30
p13_smoke|source_p10_runs|p10-smoke-proposals-2026-06-30
p13_smoke|source_p9_runs|p9-smoke-analytics-2026-05-30-2026-06-30
p13_smoke|manual_review_required|True
p13_smoke|auto_trade_enabled|False
p13_smoke|production_watchlist_enabled|False
p13_smoke|production_write_enabled|False
```

## Verification

Python:

```bash
.venv/bin/pytest tests/test_operator_shadow_outcomes.py tests/test_operator_shadow_outcomes_read_model.py tests/test_p13_shadow_outcomes_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_outcomes.py tests/test_dashboard_app.py -k 'shadow_outcome or p13_shadow_outcome or p13_import_shadow_outcomes or dashboard' -q
```

Dashboard:

```bash
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```
