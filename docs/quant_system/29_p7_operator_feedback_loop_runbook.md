# P7 Operator Feedback Loop Runbook

Date: 2026-05-30

## Purpose

P7 records operator review decisions after dashboard and artifact review.

This runbook is review-only. It does not place orders, connect to a broker, send
live notifications, or mutate factor/watchlist/scoring/scheduler state.

## Inputs

Required CSV columns:

- `review_date`
- `review_session_id`
- `reviewer_id`
- `asset_id`
- `decision_label`
- `evidence_artifact_id`
- `evidence_path`
- `requires_follow_up`
- `manual_review_required`
- `auto_trade_enabled`

Optional columns:

- `stock_code`
- `stock_name`
- `source_context`
- `follow_up_note`
- `notes`

Allowed decision labels:

- `observe`
- `candidate`
- `caution`
- `remove`
- `no_action`

Safety fields:

- `manual_review_required` must be `True`.
- `auto_trade_enabled` must be `False`.
- Execution-like fields such as `order_id`, `execution_status`, `broker`,
  `account_id`, and `cash` are rejected.

## Daily Operator Flow

1. Run the normal P4/P5/P6 daily review flow.
2. Open the dashboard workbench and inspect TopN, watchlist, scores, reports, and
   charts.
3. Prepare a decision input CSV for reviewed assets.
4. Generate local decision journal artifacts.
5. Import the decision journal into the P7 read model when the database is
   available.
6. Use the dashboard read-only decision history panel during later asset review.

## Generate Decision Journal Artifacts

Example:

```bash
.venv/bin/stock-research p7-decision-journal \
  --review-date 2026-05-30 \
  --review-session-id morning-review \
  --reviewer-id operator \
  --source-artifact-root outputs \
  --input-csv outputs/p7/decision_input.csv \
  --output-dir outputs/p7/2026-05-30
```

Expected lines:

```text
p7_decision_journal|status|review_recorded
p7_decision_journal|json|...
p7_decision_journal|csv|...
p7_decision_journal|markdown|...
```

Empty review sessions are allowed. Their status is `no_decisions_recorded`.

## Import Decision Journal Read Model

Single file:

```bash
.venv/bin/stock-research p7-import-decision-journal \
  --path outputs/p7/2026-05-30/operator_decision_journal_2026-05-30_morning-review.json \
  --service stock_research
```

Directory:

```bash
.venv/bin/stock-research p7-import-decision-journal \
  --path outputs/p7/2026-05-30 \
  --service stock_research
```

Expected lines:

```text
p7_decision_journal_import|imported|1
p7_decision_journal_import|events|2
p7_decision_journal_import|session_id|morning-review
```

The import path upserts:

- `ops.operator_review_session`
- `ops.operator_decision_event`

Re-running the import is intended to be idempotent.

## Dashboard Read-Only Review

Start the dashboard API:

```bash
.venv/bin/stock-research dashboard-api --host 127.0.0.1 --port 8765
```

Start the frontend:

```bash
cd dashboard
pnpm dev
```

The dashboard reads decision history through:

```text
GET /api/assets/{asset_id}/decisions?start_date=<YYYY-MM-DD>&end_date=<YYYY-MM-DD>&limit=20
```

The UI shows decision history in the inspector. It does not provide a decision
editing form.

## P7 Smoke

Artifact smoke:

```bash
rm -rf /tmp/stock_research_p7_smoke
mkdir -p /tmp/stock_research_p7_smoke/input /tmp/stock_research_p7_smoke/output
printf 'review_date,review_session_id,reviewer_id,asset_id,stock_code,stock_name,decision_label,evidence_artifact_id,evidence_path,source_context,requires_follow_up,follow_up_note,manual_review_required,auto_trade_enabled,notes\n2026-05-30,p7-smoke,operator,CN:SH:600001,600001.SH,Alpha,candidate,dashboard:topn:2026-05-30,outputs/p6/topn.json,dashboard_topn,True,check next close strength,True,False,strong score\n2026-05-30,p7-smoke,operator,CN:SZ:000001,000001.SZ,Beta,caution,watchlist:2026-05-30,outputs/p5/watchlist.json,watchlist,False,,True,False,risk active\n' > /tmp/stock_research_p7_smoke/input/decision_input.csv
.venv/bin/stock-research p7-decision-journal \
  --review-date 2026-05-30 \
  --review-session-id p7-smoke \
  --reviewer-id operator \
  --source-artifact-root outputs \
  --input-csv /tmp/stock_research_p7_smoke/input/decision_input.csv \
  --output-dir /tmp/stock_research_p7_smoke/output
```

Read-model loader smoke:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.read_model import load_decision_journal_read_model_rows
path = Path('/tmp/stock_research_p7_smoke/output/operator_decision_journal_2026-05-30_p7-smoke.json')
rows = load_decision_journal_read_model_rows(path)
print(f"p7_smoke_read_model|session|{rows['session']['review_session_id']}|decisions|{rows['session']['decision_count']}")
print(f"p7_smoke_read_model|events|{len(rows['events'])}")
print(f"p7_smoke_read_model|labels|{','.join(row['decision_label'] for row in rows['events'])}")
PY
```

Expected:

```text
p7_smoke_read_model|session|p7-smoke|decisions|2
p7_smoke_read_model|events|2
p7_smoke_read_model|labels|candidate,caution
```

## Verification

Python:

```bash
.venv/bin/pytest tests/test_operator_decision_journal.py tests/test_operator_decision_read_model.py tests/test_dashboard_decisions.py tests/test_dashboard_app.py tests/test_factor_cli.py tests/test_schema.py -q
```

Frontend:

```bash
cd dashboard
pnpm test
pnpm build
pnpm test:e2e
```
