# P12 Shadow Watchlist Experiment Runbook

Date: 2026-06-01

## Scope

P12 records review-only shadow watchlist candidates from passed P11 offline
replay results. It does not write production watchlist signals, mutate factor
scores, schedule jobs, promote experiments, place orders, or create
broker/account/execution state.

## Review Flow

1. Review P11 replay results with `passed_offline_replay`.
2. Prepare shadow candidate rows with explicit P11, P10, and P9 source
   references.
3. Generate P12 JSON, CSV, and Markdown artifacts.
4. Import P12 artifacts into the `ops.operator_shadow_watchlist_*` read model.
5. Review the read-only dashboard Shadow Watchlist panel.
6. Use shadow observations only as input to a later scoped phase.

## Candidate CSV Columns

Required columns:

- `shadow_candidate_id`
- `replay_result_id`
- `source_p11_replay_run_id`
- `source_p10_proposal_run_id`
- `source_p9_analytics_run_id`
- `candidate_date`
- `asset_id`
- `shadow_layer`
- `candidate_reason`
- `evidence_artifact_paths`
- `reviewer_id`
- `status`

Recommended columns:

- `stock_code`
- `stock_name`
- `metric_summary`
- `review_notes`
- `manual_review_required`
- `auto_trade_enabled`
- `production_watchlist_enabled`
- `production_write_enabled`

Allowed statuses:

- `shadow_ready`
- `shadow_observe`
- `shadow_rejected`
- `needs_more_data`
- `blocked`

`evidence_artifact_paths` must be non-empty. Every candidate row must match a
P11 replay result whose status is `passed_offline_replay`, and must preserve
the source P10 proposal run and P9 analytics run IDs.

## Generate Shadow Watchlist Artifacts

```bash
stock-research p12-shadow-watchlist \
  --replay-json outputs/p11/2026-06-30/operator_experiment_replay_2026-01-01_2026-06-30.json \
  --candidates-csv inputs/p12/shadow_candidates_2026-06-30.csv \
  --run-id p12-shadow-watchlist-2026-06-30 \
  --review-date 2026-06-30 \
  --output-dir outputs/p12/2026-06-30
```

Expected output lines:

```text
p12_shadow_watchlist|status|shadow_watchlist_review_ready
p12_shadow_watchlist|candidates|...
p12_shadow_watchlist|json|...
p12_shadow_watchlist|candidates_csv|...
p12_shadow_watchlist|markdown|...
```

## Import Shadow Watchlist Read Model

Import one artifact:

```bash
stock-research p12-import-shadow-watchlist \
  --path outputs/p12/2026-06-30/operator_shadow_watchlist_2026-06-30.json
```

Import a directory:

```bash
stock-research p12-import-shadow-watchlist \
  --path outputs/p12/2026-06-30
```

Expected output lines:

```text
p12_shadow_watchlist_import|imported|1
p12_shadow_watchlist_import|candidates|...
p12_shadow_watchlist_import|run_id|...
```

The importer uses idempotent upserts. Re-importing the same artifact updates
the same run and shadow candidate rows.

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

Open the dashboard and inspect the read-only Shadow Watchlist panel.

The panel has no promotion buttons, watchlist write buttons, score mutation
buttons, trade buttons, broker controls, order UI, or scheduler automation
controls.

## Synthetic Smoke

Run:

```bash
rm -rf /tmp/stock_research_p12_smoke
.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p12_smoke import build_p12_shadow_watchlist_smoke

result = build_p12_shadow_watchlist_smoke(Path('/tmp/stock_research_p12_smoke'))
print(f"p12_smoke|p11_replay|{result['p11_replay_json_path']}")
print(f"p12_smoke|p12_shadow|{result['p12_shadow_json_path']}")
print(f"p12_smoke|candidates_csv|{result['p12_shadow_candidates_csv_path']}")
print(f"p12_smoke|markdown|{result['p12_shadow_markdown_path']}")
print(f"p12_smoke|candidate_count|{result['candidate_count']}")
print(f"p12_smoke|read_model_candidates|{result['read_model_candidate_count']}")
print(f"p12_smoke|source_p11_runs|{','.join(result['source_p11_replay_run_ids'])}")
print(f"p12_smoke|source_p10_runs|{','.join(result['source_p10_proposal_run_ids'])}")
print(f"p12_smoke|source_p9_runs|{','.join(result['source_p9_analytics_run_ids'])}")
print(f"p12_smoke|manual_review_required|{result['manual_review_required']}")
print(f"p12_smoke|auto_trade_enabled|{result['auto_trade_enabled']}")
print(f"p12_smoke|production_watchlist_enabled|{result['production_watchlist_enabled']}")
print(f"p12_smoke|production_write_enabled|{result['production_write_enabled']}")
PY
```

Observed smoke output:

```text
p12_smoke|p11_replay|/tmp/stock_research_p12_smoke/p11/operator_experiment_replay_2026-01-01_2026-06-30.json
p12_smoke|p12_shadow|/tmp/stock_research_p12_smoke/p12/operator_shadow_watchlist_2026-06-30.json
p12_smoke|candidates_csv|/tmp/stock_research_p12_smoke/p12/operator_shadow_watchlist_2026-06-30_candidates.csv
p12_smoke|markdown|/tmp/stock_research_p12_smoke/p12/operator_shadow_watchlist_2026-06-30.md
p12_smoke|candidate_count|1
p12_smoke|read_model_candidates|1
p12_smoke|source_p11_runs|p11-smoke-replay-2026-06-30
p12_smoke|source_p10_runs|p10-smoke-proposals-2026-06-30
p12_smoke|source_p9_runs|p9-smoke-analytics-2026-05-30-2026-06-30
p12_smoke|manual_review_required|True
p12_smoke|auto_trade_enabled|False
p12_smoke|production_watchlist_enabled|False
p12_smoke|production_write_enabled|False
```

## Verification

Python:

```bash
.venv/bin/pytest tests/test_operator_shadow_watchlist.py tests/test_operator_shadow_watchlist_read_model.py tests/test_p12_shadow_watchlist_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_shadow_watchlist.py tests/test_dashboard_app.py -k 'shadow_watchlist or p12_shadow_watchlist or p12_import_shadow_watchlist or dashboard' -q
```

Dashboard:

```bash
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```
