# P11 Experiment Execution Sandbox Runbook

Date: 2026-05-31

## Scope

P11 records offline replay results for P10 proposals. It is an execution
sandbox for research review only. It does not mutate scores, write watchlist
signals, promote experiments, schedule replay jobs, place orders, or create
broker/account/execution state.

## Daily Or Weekly Flow

1. Review approved P10 experiment proposals.
2. Prepare offline replay metrics with explicit P10 proposal and P9 analytics
   references.
3. Generate P11 replay artifacts.
4. Import replay artifacts into the compact read model.
5. Review the dashboard Experiment Replay panel.
6. Use replay evidence only as input to a later scoped phase.

## Replay Metrics Columns

Required columns:

- `replay_result_id`
- `proposal_id`
- `source_p10_proposal_run_id`
- `source_p9_analytics_run_id`
- `replay_start_date`
- `replay_end_date`
- `replay_input_artifact_paths`
- `validation_method`
- `replay_status`

Recommended metric columns:

- `sample_count`
- `passed_count`
- `failed_count`
- `metric_summary`
- `failure_reason`
- `defer_reason`
- `manual_review_required`
- `auto_trade_enabled`
- `production_write_enabled`

Allowed replay statuses:

- `replay_ready`
- `passed_offline_replay`
- `failed_offline_replay`
- `needs_more_data`
- `blocked`

`replay_input_artifact_paths` must be non-empty. Every replay row must match an
approved P10 proposal and preserve the source P9 analytics run ID.

## Generate Replay Artifacts

```bash
stock-research p11-experiment-replay \
  --proposals-json outputs/p10/2026-06-30/operator_experiment_proposals_2026-06-30.json \
  --metrics-csv inputs/p11/replay_metrics_2026-06-30.csv \
  --run-id p11-replay-2026-06-30 \
  --replay-start-date 2026-01-01 \
  --replay-end-date 2026-06-30 \
  --output-dir outputs/p11/2026-06-30
```

Expected output lines:

```text
p11_experiment_replay|status|replay_review_ready
p11_experiment_replay|results|...
p11_experiment_replay|json|...
p11_experiment_replay|results_csv|...
p11_experiment_replay|markdown|...
```

## Import Replay Read Model

Import one artifact:

```bash
stock-research p11-import-experiment-replay \
  --path outputs/p11/2026-06-30/operator_experiment_replay_2026-01-01_2026-06-30.json
```

Import a directory:

```bash
stock-research p11-import-experiment-replay \
  --path outputs/p11/2026-06-30
```

Expected output lines:

```text
p11_experiment_replay_import|imported|1
p11_experiment_replay_import|results|...
p11_experiment_replay_import|run_id|...
```

The importer uses idempotent upserts. Re-importing the same artifact updates the
same replay run and replay result rows.

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

Open the dashboard and inspect the read-only Experiment Replay panel.

The panel has no pass/fail editing buttons, promotion buttons, score or
watchlist action buttons, trade buttons, broker controls, order UI, or scheduler
automation controls.

## Synthetic Smoke

Run:

```bash
rm -rf /tmp/stock_research_p11_smoke
.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p11_smoke import build_p11_experiment_replay_smoke

result = build_p11_experiment_replay_smoke(Path('/tmp/stock_research_p11_smoke'))
print(f"p11_smoke|p10_proposals|{result['p10_proposals_json_path']}")
print(f"p11_smoke|replay_input_metrics|{result['p11_replay_input_metrics_csv_path']}")
print(f"p11_smoke|p11_replay|{result['p11_replay_json_path']}")
print(f"p11_smoke|results_csv|{result['p11_replay_results_csv_path']}")
print(f"p11_smoke|markdown|{result['p11_replay_markdown_path']}")
print(f"p11_smoke|result_count|{result['result_count']}")
print(f"p11_smoke|read_model_results|{result['read_model_result_count']}")
print(f"p11_smoke|source_p10_runs|{','.join(result['source_p10_proposal_run_ids'])}")
print(f"p11_smoke|source_p9_runs|{','.join(result['source_p9_analytics_run_ids'])}")
print(f"p11_smoke|manual_review_required|{result['manual_review_required']}")
print(f"p11_smoke|auto_trade_enabled|{result['auto_trade_enabled']}")
print(f"p11_smoke|production_write_enabled|{result['production_write_enabled']}")
PY
```

Observed smoke output:

```text
p11_smoke|p10_proposals|/tmp/stock_research_p11_smoke/p10/operator_experiment_proposals_2026-06-30.json
p11_smoke|replay_input_metrics|/tmp/stock_research_p11_smoke/p11/replay_metrics_2026-06-30.csv
p11_smoke|p11_replay|/tmp/stock_research_p11_smoke/p11/operator_experiment_replay_2026-01-01_2026-06-30.json
p11_smoke|results_csv|/tmp/stock_research_p11_smoke/p11/operator_experiment_replay_2026-01-01_2026-06-30_results.csv
p11_smoke|markdown|/tmp/stock_research_p11_smoke/p11/operator_experiment_replay_2026-01-01_2026-06-30.md
p11_smoke|result_count|1
p11_smoke|read_model_results|1
p11_smoke|source_p10_runs|p10-smoke-proposals-2026-06-30
p11_smoke|source_p9_runs|p9-smoke-analytics-2026-05-30-2026-06-30
p11_smoke|manual_review_required|True
p11_smoke|auto_trade_enabled|False
p11_smoke|production_write_enabled|False
```

## Verification

Python:

```bash
.venv/bin/pytest tests/test_operator_experiment_replay.py tests/test_operator_experiment_replay_read_model.py tests/test_p11_experiment_replay_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_experiment_replay.py tests/test_dashboard_app.py -k 'experiment_replay or p11_experiment_replay or p11_import_experiment_replay or dashboard' -q
```

Dashboard:

```bash
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```
