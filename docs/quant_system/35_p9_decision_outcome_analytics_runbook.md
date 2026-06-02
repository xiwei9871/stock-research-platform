# P9 Decision Outcome Analytics Runbook

Date: 2026-05-31

## Scope

This runbook covers the review-only P9 decision outcome analytics loop.

P9 reads P8 outcome rows, builds grouped analytics, imports compact read-model
rows, and shows summaries in the dashboard. It does not modify factor scores,
watchlist signals, scheduler state, orders, positions, accounts, cash, broker
state, or trading execution paths.

## Daily Or Weekly Flow

1. Make sure P8 outcome artifacts and read-model rows exist for the review
   window.
2. Generate P9 analytics artifacts.
3. Import P9 analytics artifacts into the compact read model.
4. Open the dashboard and inspect the read-only Outcome Analytics panel.
5. Record human review notes outside P9. Experiment promotion is P10 scope.

## Generate Analytics Artifacts

From read-model rows:

```bash
stock-research p9-outcome-analytics \
  --start-date 2026-05-01 \
  --end-date 2026-06-30 \
  --output-dir outputs/p9/2026-06-30
```

From a local P8 outcome events CSV:

```bash
stock-research p9-outcome-analytics \
  --start-date 2026-05-01 \
  --end-date 2026-06-30 \
  --outcome-events-csv outputs/p8/outcome_events.csv \
  --output-dir outputs/p9/2026-06-30
```

Expected output lines:

```text
p9_outcome_analytics|status|analytics_ready
p9_outcome_analytics|groups|...
p9_outcome_analytics|json|...
p9_outcome_analytics|groups_csv|...
p9_outcome_analytics|diagnostics_csv|...
p9_outcome_analytics|markdown|...
```

## Import Analytics Read Model

Import one artifact:

```bash
stock-research p9-import-outcome-analytics \
  --path outputs/p9/2026-06-30/operator_decision_outcome_analytics_2026-05-01_2026-06-30.json
```

Import a directory:

```bash
stock-research p9-import-outcome-analytics \
  --path outputs/p9/2026-06-30
```

Expected output lines:

```text
p9_outcome_analytics_import|imported|1
p9_outcome_analytics_import|groups|...
p9_outcome_analytics_import|run_id|...
```

The importer uses idempotent upserts. Re-importing the same artifact updates the
same run and analytics group rows.

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

Open the dashboard and inspect:

- Outcome History for selected asset-level P8 rows.
- Outcome Analytics for grouped `decision_label` and `source_context` rows.

The dashboard panel is read-only. It has no edit controls, promotion buttons,
trade recommendation buttons, broker controls, or order UI.

## Synthetic Smoke

Run:

```bash
rm -rf /tmp/stock_research_p9_smoke
.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p9_smoke import build_p9_decision_outcome_analytics_smoke

result = build_p9_decision_outcome_analytics_smoke(Path('/tmp/stock_research_p9_smoke'))
print(f"p9_smoke|p8_outcome|{result['p8_outcome_json_path']}")
print(f"p9_smoke|p9_analytics|{result['p9_analytics_json_path']}")
print(f"p9_smoke|source_outcomes|{result['source_outcome_count']}")
print(f"p9_smoke|analytics_groups|{result['analytics_group_count']}")
print(f"p9_smoke|read_model_groups|{result['read_model_group_count']}")
print(f"p9_smoke|levels|{','.join(result['analytics_levels'])}")
print(f"p9_smoke|diagnostics|{result['diagnostic_count']}")
print(f"p9_smoke|manual_review_required|{result['manual_review_required']}")
print(f"p9_smoke|auto_trade_enabled|{result['auto_trade_enabled']}")
PY
```

Observed smoke output:

```text
p9_smoke|p8_outcome|/tmp/stock_research_p9_smoke/p8/operator_decision_outcome_review_2026-05-30_2026-06-30.json
p9_smoke|p9_analytics|/tmp/stock_research_p9_smoke/p9/operator_decision_outcome_analytics_2026-05-30_2026-06-30.json
p9_smoke|source_outcomes|2
p9_smoke|analytics_groups|7
p9_smoke|read_model_groups|7
p9_smoke|levels|asset_id,decision_label,review_session_id,source_context
p9_smoke|diagnostics|9
p9_smoke|manual_review_required|True
p9_smoke|auto_trade_enabled|False
```

## Verification

Python:

```bash
.venv/bin/pytest tests/test_operator_decision_outcome.py tests/test_operator_decision_outcome_read_model.py tests/test_operator_decision_outcome_analytics.py tests/test_operator_decision_outcome_analytics_read_model.py tests/test_p8_decision_outcome_smoke.py tests/test_p9_decision_outcome_analytics_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_outcome_analytics.py tests/test_dashboard_app.py tests/test_dashboard_outcomes.py -k 'operator_decision_outcome or p8_decision_outcome or p9_outcome_analytics or p9_import_outcome_analytics or outcome_analytics or dashboard' -q
```

Dashboard:

```bash
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```
