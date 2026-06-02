# P8 Decision Outcome Review Runbook

Date: 2026-05-31

## Purpose

P8 reviews what happened after P7 operator decisions by comparing those
decision events with later market bars.

This runbook is review-only. It does not create orders, connect to brokers,
write account/cash/position state, send execution instructions, or feed outcome
metrics back into scoring.

## Inputs

Required P7 decision event fields:

- `event_id`
- `review_session_id`
- `review_date`
- `asset_id`
- `decision_label`
- `manual_review_required`
- `auto_trade_enabled`
- `source_artifact_path`

Required market bar fields:

- `asset_id`
- `trade_date`
- `close`
- `high`
- `low`

Safety fields:

- `manual_review_required` must be `True`.
- `auto_trade_enabled` must be `False`.
- Outcome review artifacts preserve P7 evidence and source artifact paths.

Default horizons:

- 1D
- 3D
- 5D
- 10D
- 20D
- 60D

## Daily Flow

1. Complete the normal daily research review and P7 decision journal flow.
2. Import P7 decision journals if the database is available.
3. Generate P8 outcome review artifacts for the review window.
4. Import P8 outcome artifacts into the read model.
5. Use the dashboard outcome panel as a read-only review aid.
6. Do not use P8 outcomes as scoring inputs or trading instructions.

## Generate Outcome Artifacts

From database read models:

```bash
.venv/bin/stock-research p8-decision-outcome-review \
  --start-date 2026-05-01 \
  --end-date 2026-05-30 \
  --review-session-id morning-review \
  --output-dir outputs/p8/2026-05-30 \
  --service stock_research \
  --adjust-type qfq
```

From local CSV inputs:

```bash
.venv/bin/stock-research p8-decision-outcome-review \
  --start-date 2026-05-01 \
  --end-date 2026-05-30 \
  --decision-events-csv outputs/p8/input/decision_events.csv \
  --bars-csv outputs/p8/input/market_bars.csv \
  --output-dir outputs/p8/2026-05-30 \
  --horizon 1 \
  --horizon 5 \
  --horizon 20
```

Expected lines:

```text
p8_decision_outcome_review|status|review_ready
p8_decision_outcome_review|outcomes|...
p8_decision_outcome_review|json|...
p8_decision_outcome_review|details_csv|...
p8_decision_outcome_review|summary_csv|...
p8_decision_outcome_review|markdown|...
```

## Import Outcome Read Model

Single artifact:

```bash
.venv/bin/stock-research p8-import-decision-outcome-review \
  --path outputs/p8/2026-05-30/operator_decision_outcome_review_2026-05-01_2026-05-30.json \
  --service stock_research
```

Directory:

```bash
.venv/bin/stock-research p8-import-decision-outcome-review \
  --path outputs/p8/2026-05-30 \
  --service stock_research
```

Expected lines:

```text
p8_decision_outcome_review_import|imported|1
p8_decision_outcome_review_import|events|...
p8_decision_outcome_review_import|run_id|...
```

The import path upserts:

- `ops.operator_decision_outcome_run`
- `ops.operator_decision_outcome_event`

Re-running the import is intended to be idempotent.

## Dashboard Read-Only Outcome View

Start the dashboard API:

```bash
.venv/bin/stock-research dashboard-api --host 127.0.0.1 --port 8765
```

Start the frontend:

```bash
cd dashboard
pnpm dev
```

The dashboard reads outcomes through:

```text
GET /api/assets/{asset_id}/outcomes?start_date=<YYYY-MM-DD>&end_date=<YYYY-MM-DD>&limit=20
```

Optional session filter:

```text
review_session_id=<session>
```

The UI shows `Outcome History` in the inspector. It has no editing controls,
order buttons, broker widgets, or execution controls.

## P8 Smoke

Run the synthetic smoke fixture:

```bash
rm -rf /tmp/stock_research_p8_smoke
.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p8_smoke import build_p8_decision_outcome_smoke
out = Path('/tmp/stock_research_p8_smoke')
result = build_p8_decision_outcome_smoke(out)
print(f"p8_smoke|p7_journal|{result['p7_journal_json_path']}")
print(f"p8_smoke|p8_outcome|{result['p8_outcome_json_path']}")
print(f"p8_smoke|journal_decisions|{result['journal_decision_count']}")
print(f"p8_smoke|outcomes|{result['outcome_count']}")
print(f"p8_smoke|read_model_events|{result['read_model_event_count']}")
print(f"p8_smoke|labels|{','.join(result['decision_labels'])}")
print(f"p8_smoke|manual_review_required|{result['manual_review_required']}")
print(f"p8_smoke|auto_trade_enabled|{result['auto_trade_enabled']}")
PY
```

Expected:

```text
p8_smoke|p7_journal|/tmp/stock_research_p8_smoke/p7/operator_decision_journal_2026-05-30_p8-smoke.json
p8_smoke|p8_outcome|/tmp/stock_research_p8_smoke/p8/operator_decision_outcome_review_2026-05-30_2026-06-30.json
p8_smoke|journal_decisions|2
p8_smoke|outcomes|2
p8_smoke|read_model_events|2
p8_smoke|labels|candidate,caution
p8_smoke|manual_review_required|True
p8_smoke|auto_trade_enabled|False
```

## Weekly Review

1. Review grouped outcome summaries by decision label and source context.
2. Identify decision labels with frequent `insufficient_data` outcomes.
3. Check whether evidence paths and source artifact paths remain complete.
4. Review dashboard outcome history for representative assets.
5. Record observations as human review notes outside P8.

Do not convert P8 outcome metrics into automatic score changes or trading
instructions.

## Verification

Python:

```bash
.venv/bin/pytest tests/test_operator_decision_journal.py tests/test_operator_decision_read_model.py tests/test_operator_decision_outcome.py tests/test_operator_decision_outcome_read_model.py tests/test_p8_decision_outcome_smoke.py tests/test_dashboard_app.py tests/test_dashboard_outcomes.py tests/test_dashboard_decisions.py tests/test_schema.py tests/test_factor_cli.py -k 'operator_decision or p7_decision_journal or p8_decision_outcome or dashboard_api' -q
```

Frontend:

```bash
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```
