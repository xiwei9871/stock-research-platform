# P18 Shadow Follow-up Resolution Review Runbook

## Purpose

P18 turns P17 shadow follow-up queue artifacts into a review-only resolution
review. It records whether each P17 follow-up item should remain unresolved,
continue observing, be tracked in a research ticket, or be closed as
deprioritized.

P18 is review-only.

- No production watchlist writes.
- No score, factor, scheduler, broker, order, account, cash, or position writes.
- No mutation of P17 follow-up queue rows.
- All rows remain manual-review required.

Internal risk or position review skills may summarize P18 resolution evidence only when they follow `docs/llmquant-fusion/internal-skill-template.md`, cite local artifacts, and pass the existing review boundary. They cannot change resolution labels, close items, promote candidates, mutate P17 rows, or create production state.

## Build Artifact

Use a P17 follow-up queue JSON artifact:

```bash
stock-research p18-shadow-follow-up-resolution \
  --p17-follow-up-json outputs/p17/operator_shadow_follow_up_queue_2026-08-29.json \
  --run-id p18-shadow-follow-up-resolution-2026-08-29 \
  --resolution-date 2026-08-29 \
  --operator-id operator \
  --output-dir outputs/p18
```

Expected output:

```text
p18_shadow_follow_up_resolution|status|shadow_follow_up_resolution_ready
p18_shadow_follow_up_resolution|items|<count>
p18_shadow_follow_up_resolution|json|outputs/p18/operator_shadow_follow_up_resolution_2026-08-29.json
p18_shadow_follow_up_resolution|items_csv|outputs/p18/operator_shadow_follow_up_resolution_2026-08-29_items.csv
p18_shadow_follow_up_resolution|markdown|outputs/p18/operator_shadow_follow_up_resolution_2026-08-29.md
```

## Import Read Model

Apply schema first if the P18 ops tables do not exist:

```bash
stock-research apply-schema
```

Import one artifact or a directory:

```bash
stock-research p18-import-shadow-follow-up-resolution \
  --path outputs/p18 \
  --service stock_research
```

Expected output:

```text
p18_import_shadow_follow_up_resolution|imported|<artifact-count>
p18_import_shadow_follow_up_resolution|items|<item-count>
p18_import_shadow_follow_up_resolution|runs|<comma-separated-run-ids>
```

The import upserts into:

- `ops.operator_shadow_follow_up_resolution_run`
- `ops.operator_shadow_follow_up_resolution_item`

## Dashboard

Run the dashboard API:

```bash
stock-research dashboard-api --host 127.0.0.1 --port 8765
```

P18 dashboard endpoint:

```text
/api/shadow-follow-up-resolution?start_date=2026-06-01&end_date=2026-08-31&limit=20
```

Missing P18 tables return an empty item list. The dashboard panel is read-only
and exposes no promote, trade, write, scheduler, broker, order, account, cash,
or position controls.

## Synthetic Smoke

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python - <<'PY'
from pathlib import Path
from stock_research.operator_decision.p18_smoke import build_p18_shadow_follow_up_resolution_smoke

result = build_p18_shadow_follow_up_resolution_smoke(Path('/tmp/stock_research_p18_smoke'))
for key in sorted(result):
    print(f"p18_smoke|{key}|{result[key]}")
PY
```

Known smoke output from 2026-06-03:

```text
p18_smoke|p17_shadow_follow_up_queue_json_path|/tmp/stock_research_p18_smoke/p17/operator_shadow_follow_up_queue_2026-08-29.json
p18_smoke|p18_shadow_follow_up_resolution_json_path|/tmp/stock_research_p18_smoke/p18/operator_shadow_follow_up_resolution_2026-08-29.json
p18_smoke|p18_shadow_follow_up_resolution_items_csv_path|/tmp/stock_research_p18_smoke/p18/operator_shadow_follow_up_resolution_2026-08-29_items.csv
p18_smoke|p18_shadow_follow_up_resolution_markdown_path|/tmp/stock_research_p18_smoke/p18/operator_shadow_follow_up_resolution_2026-08-29.md
p18_smoke|source_follow_up_item_count|1
p18_smoke|resolution_item_count|1
p18_smoke|read_model_item_count|1
p18_smoke|follow_up_statuses|['collect_more_evidence']
p18_smoke|resolution_statuses|['stale_unresolved']
p18_smoke|resolution_buckets|['needs_operator_review']
p18_smoke|source_p17_follow_up_run_ids|['p17-smoke-shadow-follow-up-queue-2026-08-29']
p18_smoke|manual_review_required|True
p18_smoke|auto_trade_enabled|False
p18_smoke|production_watchlist_enabled|False
p18_smoke|production_write_enabled|False
```

## Operator Review

Review the Markdown artifact first. Treat P18 statuses as review disposition
labels only:

- `stale_unresolved`: P17 requested evidence is still not confirmed.
- `research_ticket_opened`: external research tracking exists.
- `continue_observing`: keep observing the shadow group.
- `deprioritized_closed`: closed as low-priority unless new evidence arrives.
- `evidence_collected`: evidence is ready for a separately scoped research task.

Any next production step requires a separately scoped phase and explicit review.
