# P10 Experiment Promotion Governance Runbook

Date: 2026-05-31

## Scope

P10 records experiment proposals from P9 outcome analytics. It is governance-only.
It does not implement experiments, mutate scores, write watchlist signals, place
orders, or add scheduler promotion automation.

## Daily Or Weekly Flow

1. Review P9 outcome analytics artifacts or dashboard summaries.
2. Draft proposal rows in CSV with explicit P9 evidence references.
3. Generate P10 proposal artifacts.
4. Import proposal artifacts into the compact read model.
5. Review the dashboard Experiment Proposals panel.
6. Use approved proposals only as inputs to a later scoped implementation phase.

## Proposal CSV Columns

Required columns:

- `proposal_id`
- `proposal_title`
- `hypothesis`
- `source_p9_analytics_run_id`
- `source_analytics_group_ids`
- `source_diagnostic_refs`
- `source_artifact_paths`
- `expected_validation_method`
- `risk_notes`
- `reviewer_id`
- `status`
- `manual_review_required`
- `auto_trade_enabled`

Allowed statuses:

- `draft`
- `needs_more_data`
- `approved_for_experiment`
- `rejected`
- `deferred`

At least one of `source_analytics_group_ids` or `source_diagnostic_refs` must be
present. `source_artifact_paths` must point back to source P9 evidence.

## Generate Proposal Artifacts

```bash
stock-research p10-experiment-proposals \
  --input-csv inputs/p10/proposals_2026-06-30.csv \
  --review-date 2026-06-30 \
  --run-id p10-proposals-2026-06-30 \
  --output-dir outputs/p10/2026-06-30
```

Expected output lines:

```text
p10_experiment_proposals|status|proposal_review_ready
p10_experiment_proposals|proposals|...
p10_experiment_proposals|json|...
p10_experiment_proposals|proposals_csv|...
p10_experiment_proposals|markdown|...
```

## Import Proposal Read Model

Import one artifact:

```bash
stock-research p10-import-experiment-proposals \
  --path outputs/p10/2026-06-30/operator_experiment_proposals_2026-06-30.json
```

Import a directory:

```bash
stock-research p10-import-experiment-proposals \
  --path outputs/p10/2026-06-30
```

Expected output lines:

```text
p10_experiment_proposals_import|imported|1
p10_experiment_proposals_import|proposals|...
p10_experiment_proposals_import|run_id|...
```

The importer uses idempotent upserts. Re-importing the same artifact updates the
same proposal run and proposal rows.

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

Open the dashboard and inspect the read-only Experiment Proposals panel.

The panel has no approve/reject controls, promotion buttons, trade buttons,
broker controls, order UI, or score/watchlist mutation controls.

## Synthetic Smoke

Run:

```bash
rm -rf /tmp/stock_research_p10_smoke
.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p10_smoke import build_p10_experiment_proposals_smoke

result = build_p10_experiment_proposals_smoke(Path('/tmp/stock_research_p10_smoke'))
print(f"p10_smoke|p9_analytics|{result['p9_analytics_json_path']}")
print(f"p10_smoke|p10_proposals|{result['p10_proposals_json_path']}")
print(f"p10_smoke|proposals_csv|{result['p10_proposals_csv_path']}")
print(f"p10_smoke|markdown|{result['p10_proposals_markdown_path']}")
print(f"p10_smoke|proposal_count|{result['proposal_count']}")
print(f"p10_smoke|read_model_proposals|{result['read_model_proposal_count']}")
print(f"p10_smoke|source_p9_runs|{','.join(result['source_p9_analytics_run_ids'])}")
print(f"p10_smoke|manual_review_required|{result['manual_review_required']}")
print(f"p10_smoke|auto_trade_enabled|{result['auto_trade_enabled']}")
print(f"p10_smoke|promotion_enabled|{result['promotion_enabled']}")
PY
```

Observed smoke output:

```text
p10_smoke|p9_analytics|/tmp/stock_research_p10_smoke/p9/operator_decision_outcome_analytics_2026-05-30_2026-06-30.json
p10_smoke|p10_proposals|/tmp/stock_research_p10_smoke/p10/operator_experiment_proposals_2026-06-30.json
p10_smoke|proposals_csv|/tmp/stock_research_p10_smoke/p10/operator_experiment_proposals_2026-06-30_proposals.csv
p10_smoke|markdown|/tmp/stock_research_p10_smoke/p10/operator_experiment_proposals_2026-06-30.md
p10_smoke|proposal_count|2
p10_smoke|read_model_proposals|2
p10_smoke|source_p9_runs|p9-smoke-analytics-2026-05-30-2026-06-30
p10_smoke|manual_review_required|True
p10_smoke|auto_trade_enabled|False
p10_smoke|promotion_enabled|False
```

## Verification

Python:

```bash
.venv/bin/pytest tests/test_operator_experiment_proposals.py tests/test_operator_experiment_proposals_read_model.py tests/test_p10_experiment_proposals_smoke.py tests/test_schema.py tests/test_factor_cli.py tests/test_dashboard_experiment_proposals.py tests/test_dashboard_app.py -k 'experiment_proposal or p10_experiment_proposals or p10_import_experiment_proposals or operator_experiment_proposal or dashboard' -q
```

Dashboard:

```bash
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```
