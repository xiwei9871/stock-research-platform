# P3–P5 current-branch verification — 2026-08-04

## Scope

This verification covers the quant-platform P3–P5 line:

- P3: durable read models and operator export;
- P4: daily orchestration, freshness smoke, run recording, and scheduler wrapper;
- P5: dry-run notification artifacts and Feishu preview safety.

It does not change strategy ranking, broker integration, order execution, or the
rolling-sector P2 scope.

## P3 real smoke

Input artifacts were the existing P2 smoke package for 2026-05-29.

| Operation | Result |
|---|---:|
| Aggregate review imports | 1 run |
| Virtual portfolio imports | 1 review, 2 states, 1 position |
| Operator export `review_runs` | 1 row |
| Operator export `review_sections` | 6 rows |
| Operator export `portfolio_risk` | 1 row |
| Operator export `latest_status_by_trade_date` | 1 row |

Output: `/tmp/p3_operator_export_20260529/`.

## P4 real smoke

`p4-daily-orchestration` was run with `--apply-daily-run-schema --record-run`.

- status: `ok`;
- blockers: `0`;
- daily run record: `daily_job:2026-05-29:p4_daily_orchestration:40efa83e65bc`;
- output: `/tmp/p4_orchestration_20260529/`.

`p4-read-model-smoke` result:

- status: `pass`;
- blockers: `0`;
- warnings: `0`;
- operator export files: pass;
- operator export row counts: pass;
- P2 review run freshness: pass;
- virtual portfolio freshness: pass.

The generated scheduler line was printed for manual review only:

```text
15 19 * * 1-5 cd /Users/xiwei/stock_research && TRADE_DATE=$(date +%F) PORTFOLIO_ID=p2_smoke_demo SERVICE=stock_research scripts/run_p4_scheduler_daily.sh >> /tmp/p4_scheduler_daily.log 2>&1
```

The wrapper dry-run confirmed that P5 notification remains disabled by default.

## P5 real dry-run

The P4 smoke log was converted into a P5 notification without network access.

| Check | Result |
|---|---|
| Notification status | `dry_run` |
| Severity | `ok` |
| Trade date | `2026-05-29` |
| Blockers / warnings | `0 / 0` |
| Feishu preview | generated |
| Live transport | not called |

Outputs:

- `/tmp/p5_notifications_20260529/p5_p4_smoke_notification_preview.json`;
- `/tmp/p5_notifications_20260529/p5_p4_smoke_notification_delivery_log.jsonl`;
- `/tmp/p5_feishu_preview_20260529/p5_p4_smoke_feishu_preview.json`.

## Tests

Focused P3–P5 suite:

```text
24 passed, 208 deselected, 2 warnings in 1.30s
```

The rolling-sector suite remains green independently:

```text
309 passed, 2 warnings in 38.63s
```

## Decision

P3, P4, and P5 are verified on the current branch. The next platform phase is
P6 dashboard workbench; P5 live notification remains opt-in and the scheduler
wrapper does not auto-install or auto-send anything.
