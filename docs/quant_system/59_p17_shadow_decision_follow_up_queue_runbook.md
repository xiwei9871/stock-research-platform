# P17 Shadow Decision Follow-up Queue Runbook

Date: 2026-06-02

## Purpose

P17 turns P16 shadow review decisions into a review-only follow-up queue. It is
used to track which shadow groups need continued observation, more evidence, a
separately scoped research ticket, or lower review priority.

## Safety Boundary

P17 is review-only.

- It does not write production watchlists.
- It does not mutate factor scores.
- It does not write factor approvals.
- It does not schedule jobs.
- It does not create broker, order, execution, account, cash, or position state.
- It does not treat follow-up status as production approval.

Required safety fields:

- `manual_review_required = true`
- `auto_trade_enabled = false`
- `production_watchlist_enabled = false`
- `production_write_enabled = false`

Internal watchlist memo skills may propose follow-up questions for P17 only when they follow `docs/llmquant-fusion/internal-skill-template.md`, cite local artifacts, and keep conclusions review-only. They cannot promote candidates, alter follow-up status, write production watchlists, or bypass operator review.

## Build Artifact

```bash
stock-research p17-shadow-follow-up-queue \
  --p16-decisions-json outputs/p16/operator_shadow_review_decisions_2026-08-29.json \
  --run-id p17-shadow-follow-up-queue-2026-08-29 \
  --follow-up-date 2026-08-29 \
  --operator-id operator-a \
  --output-dir outputs/p17
```

Expected output lines:

```text
p17_shadow_follow_up_queue|status|shadow_follow_up_queue_ready
p17_shadow_follow_up_queue|items|<count>
p17_shadow_follow_up_queue|json|outputs/p17/operator_shadow_follow_up_queue_2026-08-29.json
p17_shadow_follow_up_queue|items_csv|outputs/p17/operator_shadow_follow_up_queue_2026-08-29_items.csv
p17_shadow_follow_up_queue|markdown|outputs/p17/operator_shadow_follow_up_queue_2026-08-29.md
```

## Import Read Model

```bash
stock-research p17-import-shadow-follow-up-queue \
  --path outputs/p17 \
  --service stock_research
```

Expected output lines:

```text
p17_import_shadow_follow_up_queue|imported|<artifact-count>
p17_import_shadow_follow_up_queue|items|<item-count>
p17_import_shadow_follow_up_queue|runs|<comma-separated-run-ids>
```

## Dashboard

Start the dashboard API:

```bash
stock-research dashboard-api --host 127.0.0.1 --port 8765
```

The dashboard reads:

```text
GET /api/shadow-follow-up-queue?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&limit=20
```

Missing P17 tables return an empty item list.

## Smoke

```bash
rm -rf /tmp/stock_research_p17_smoke
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p17_smoke import build_p17_shadow_follow_up_queue_smoke

result = build_p17_shadow_follow_up_queue_smoke(Path('/tmp/stock_research_p17_smoke'))
print(f"p17_smoke|p16_shadow_review_decisions|{result['p16_shadow_review_decisions_json_path']}")
print(f"p17_smoke|p17_shadow_follow_up_queue|{result['p17_shadow_follow_up_queue_json_path']}")
print(f"p17_smoke|items_csv|{result['p17_shadow_follow_up_queue_items_csv_path']}")
print(f"p17_smoke|markdown|{result['p17_shadow_follow_up_queue_markdown_path']}")
print(f"p17_smoke|source_decision_group_count|{result['source_decision_group_count']}")
print(f"p17_smoke|follow_up_item_count|{result['follow_up_item_count']}")
print(f"p17_smoke|read_model_items|{result['read_model_item_count']}")
print(f"p17_smoke|follow_up_statuses|{','.join(result['follow_up_statuses'])}")
print(f"p17_smoke|priority_buckets|{','.join(result['priority_buckets'])}")
print(f"p17_smoke|source_p16_decision_runs|{','.join(result['source_p16_decision_run_ids'])}")
print(f"p17_smoke|manual_review_required|{result['manual_review_required']}")
print(f"p17_smoke|auto_trade_enabled|{result['auto_trade_enabled']}")
print(f"p17_smoke|production_watchlist_enabled|{result['production_watchlist_enabled']}")
print(f"p17_smoke|production_write_enabled|{result['production_write_enabled']}")
PY
```
