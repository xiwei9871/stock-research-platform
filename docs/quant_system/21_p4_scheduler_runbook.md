# P4 Scheduler Runbook

Date: 2026-05-29

## Purpose

This runbook covers the local scheduler-safe P4 flow:

1. Import P3 read models from generated P2 artifacts.
2. Export operator-ready P3 review files.
3. Verify read-model freshness and export files.
4. Optionally generate a cron line for manual installation.

This runbook does not install a scheduler automatically.

## Prerequisites

- Run from `/Users/xiwei/stock_research`.
- PostgreSQL service is available through `service=stock_research`.
- P2 aggregate review artifact exists:
  - `outputs/p2/aggregate/p2_aggregate_review_<trade_date>.json`
- P2 virtual portfolio review artifact exists:
  - `outputs/p2/simulation/virtual_portfolio_review_<trade_date>_<portfolio_id>.json`
- The virtual portfolio id is known. The current smoke/default value is:
  - `p2_smoke_demo`

## Manual Dry Run

Use `DRY_RUN=1` to print the wrapper commands without executing imports, exports, or
database checks:

```bash
TRADE_DATE=2026-05-29 \
PORTFOLIO_ID=p2_smoke_demo \
SERVICE=stock_research \
DRY_RUN=1 \
scripts/run_p4_scheduler_daily.sh
```

Expected output shape:

```text
p4_scheduler_wrapper|dry_run|...
p4_scheduler_wrapper|dry_run|...
```

The first dry-run line is the orchestration command. The second dry-run line is
the read-model smoke command.

## Manual Run

Run the wrapper for one trade date:

```bash
TRADE_DATE=2026-05-29 \
PORTFOLIO_ID=p2_smoke_demo \
SERVICE=stock_research \
scripts/run_p4_scheduler_daily.sh
```

The wrapper runs:

```bash
.venv/bin/stock-research p4-daily-orchestration \
  --trade-date 2026-05-29 \
  --aggregate-review outputs/p2/aggregate/p2_aggregate_review_2026-05-29.json \
  --virtual-portfolio outputs/p2/simulation/virtual_portfolio_review_2026-05-29_p2_smoke_demo.json \
  --output-dir outputs/p4/operator/2026-05-29 \
  --portfolio-id p2_smoke_demo \
  --apply-daily-run-schema \
  --record-run \
  --service stock_research
```

Then it runs:

```bash
.venv/bin/stock-research p4-read-model-smoke \
  --trade-date 2026-05-29 \
  --operator-manifest outputs/p4/operator/2026-05-29/manifest.json \
  --portfolio-id p2_smoke_demo \
  --service stock_research
```

## Success Output

Successful orchestration starts with:

```text
p4_daily_orchestration|status|ok|trade_date|2026-05-29|blockers|0
```

Successful smoke starts with:

```text
p4_read_model_smoke|status|pass|trade_date|2026-05-29|blockers|0|warnings|0
```

The wrapper writes operator output under:

```text
outputs/p4/operator/2026-05-29/
```

Expected files include:

- `manifest.json`
- `review_runs.csv`
- `review_runs.json`
- `review_sections.csv`
- `review_sections.json`
- `portfolio_risk.csv`
- `portfolio_risk.json`
- `latest_status_by_trade_date.csv`
- `latest_status_by_trade_date.json`

## Warning Output

Smoke can return warning status when read models are fresh but one or more export
datasets have zero rows:

```text
p4_read_model_smoke|status|warning|trade_date|2026-05-29|blockers|0|warnings|1
p4_read_model_smoke_check|operator_export_row_counts|warning|zero_count_datasets|review_runs
```

Treat warnings as operator-review items. Check whether the empty dataset is
expected for that trade date before installing or trusting a recurring scheduler.

## Failure Triage

Missing artifacts produce blocked orchestration:

```text
p4_daily_orchestration|status|blocked|trade_date|2026-05-29|blockers|2
p4_daily_orchestration|missing_artifact|...
```

Actions:

1. Regenerate the missing P2 artifact.
2. Rerun `scripts/run_p4_scheduler_daily.sh` for the same `TRADE_DATE`.
3. Check `ops.daily_job_run` for the `p4_daily_orchestration` record.

Stale read models produce blocked smoke:

```text
p4_read_model_smoke|status|blocked|trade_date|2026-05-29|blockers|1|warnings|0
p4_read_model_smoke_check|p2_review_run|blocked|latest_trade_date|2026-05-28
```

Actions:

1. Rerun `p4-daily-orchestration` for the target date.
2. Confirm the P3 import paths point to the intended artifacts.
3. Rerun `p4-read-model-smoke`.

## Rollback And Rerun

The P3 imports are idempotent upserts. To rerun:

```bash
TRADE_DATE=2026-05-29 \
PORTFOLIO_ID=p2_smoke_demo \
SERVICE=stock_research \
scripts/run_p4_scheduler_daily.sh
```

To isolate an export issue without reimporting artifacts, run:

```bash
.venv/bin/stock-research p3-export-operator-review \
  --start-date 2026-05-29 \
  --end-date 2026-05-29 \
  --output-dir outputs/p4/operator/2026-05-29 \
  --portfolio-id p2_smoke_demo \
  --service stock_research
```

Then rerun smoke:

```bash
.venv/bin/stock-research p4-read-model-smoke \
  --trade-date 2026-05-29 \
  --operator-manifest outputs/p4/operator/2026-05-29/manifest.json \
  --portfolio-id p2_smoke_demo \
  --service stock_research
```

## Manual Cron Entry

Generate a cron line for review:

```bash
.venv/bin/stock-research p4-scheduler-cron-entry \
  --project-dir /Users/xiwei/stock_research \
  --trade-date-expr '$(date +%F)' \
  --hour 19 \
  --minute 15 \
  --weekdays 1-5 \
  --portfolio-id p2_smoke_demo \
  --service stock_research \
  --log-path logs/p4_scheduler_daily.log
```

Example output:

```text
15 19 * * 1-5 cd /Users/xiwei/stock_research && TRADE_DATE=$(date +%F) PORTFOLIO_ID=p2_smoke_demo SERVICE=stock_research scripts/run_p4_scheduler_daily.sh >> logs/p4_scheduler_daily.log 2>&1
```

Installation remains manual. Review the line, then install it with the operator's
preferred cron workflow.

## Safety Notes

- The wrapper does not place orders.
- The wrapper does not connect to brokers.
- The wrapper does not install cron or launchd jobs.
- Generated outputs remain review-only.
- The dashboard workbench remains out of P4 scope until scheduler freshness is
  repeatable.
