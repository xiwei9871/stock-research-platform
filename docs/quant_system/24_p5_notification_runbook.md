# P5 Notification Runbook

Date: 2026-05-29

## Purpose

This runbook covers the P5 notification hardening flow for P4 scheduled
operations:

1. Read `p4-read-model-smoke` machine-readable output.
2. Convert `pass`, `warning`, and `blocked` into operational notification
   severity.
3. Write dry-run local notification preview/log artifacts.
4. Optionally write a Feishu text payload preview.
5. Optionally enable the P4 scheduler wrapper hook.

The P5 notification path is operational only. It does not place orders, connect
to brokers, install schedulers, or store secrets.

## Severity Mapping

| P4 smoke status | P5 operational severity | Operator meaning |
| --- | --- | --- |
| `pass` | `ok` | No immediate action |
| `warning` | `warning` | Review warning checks before trusting the scheduled run |
| `blocked` | `critical` | Rerun P4 orchestration and investigate blocked checks |

## Prerequisites

- Run from `/Users/xiwei/stock_research`.
- P4 smoke output exists in a local log file.
- For scheduler wrapper usage, P4 wrapper remains:
  - `scripts/run_p4_scheduler_daily.sh`
- P5 script entrypoint:
  - `scripts/run_p5_notify_p4_smoke.py`

The central `stock-research` CLI command is intentionally not added in this P5
slice because `src/stock_research/cli.py` currently contains unrelated Alpha191
work from another development line.

## Manual Dry Run From Smoke Log

Create notification artifacts from a saved P4 smoke log:

```bash
.venv/bin/python scripts/run_p5_notify_p4_smoke.py \
  --smoke-log logs/p4_scheduler_daily.log \
  --output-dir outputs/p5/notifications/2026-05-29 \
  --source-command "stock-research p4-read-model-smoke --trade-date 2026-05-29"
```

Expected output shape:

```text
p5_p4_smoke_notification|status|dry_run|trade_date|2026-05-29|severity|critical|preview|...|delivery_log|...
```

Generated files:

- `outputs/p5/notifications/2026-05-29/p5_p4_smoke_notification_preview.json`
- `outputs/p5/notifications/2026-05-29/p5_p4_smoke_notification_delivery_log.jsonl`

## Manual Feishu Preview

Add `--feishu-preview` to write a Feishu text payload preview:

```bash
.venv/bin/python scripts/run_p5_notify_p4_smoke.py \
  --smoke-log logs/p4_scheduler_daily.log \
  --output-dir outputs/p5/notifications/2026-05-29 \
  --source-command "stock-research p4-read-model-smoke --trade-date 2026-05-29" \
  --feishu-preview
```

Expected additional output:

```text
p5_p4_smoke_feishu_preview|status|dry_run|trade_date|2026-05-29|items|1|preview|...|delivery_log|...
```

Generated Feishu preview files:

- `outputs/p5/notifications/2026-05-29/feishu/p5_p4_smoke_feishu_preview.json`
- `outputs/p5/notifications/2026-05-29/feishu/p5_p4_smoke_feishu_delivery_log.jsonl`

## Scheduler Wrapper Hook

By default, P5 notification is disabled in the P4 wrapper:

```bash
TRADE_DATE=2026-05-29 \
PORTFOLIO_ID=p2_smoke_demo \
SERVICE=stock_research \
scripts/run_p4_scheduler_daily.sh
```

Default wrapper output includes:

```text
p4_scheduler_wrapper|p5_notify|disabled
```

Enable dry-run notification artifacts after P4 smoke:

```bash
TRADE_DATE=2026-05-29 \
PORTFOLIO_ID=p2_smoke_demo \
SERVICE=stock_research \
P5_NOTIFY=1 \
scripts/run_p4_scheduler_daily.sh
```

Enable dry-run notification plus Feishu preview:

```bash
TRADE_DATE=2026-05-29 \
PORTFOLIO_ID=p2_smoke_demo \
SERVICE=stock_research \
P5_NOTIFY=1 \
P5_NOTIFY_FEISHU_PREVIEW=1 \
scripts/run_p4_scheduler_daily.sh
```

Override output paths when needed:

```bash
P5_OUTPUT_DIR=outputs/p5/notifications/2026-05-29 \
P5_SMOKE_LOG=outputs/p5/notifications/2026-05-29/p4_read_model_smoke.log \
P5_NOTIFY=1 \
scripts/run_p4_scheduler_daily.sh
```

## Live Feishu Send Safety

The module-level P5 Feishu sender supports live sending only behind explicit
safety gates:

- `dry_run=False`
- non-empty `webhook_url`
- `allow_live_send=True`
- `limit=1`
- `test_mode=True`

The runbook does not recommend enabling live send from the scheduler yet. Use
dry-run artifacts first, review payload shape, then add live wiring only after a
separate operator approval step.

## Triage

For `ok`:

1. Confirm `blockers: 0` and `warnings: 0`.
2. Archive the preview/log with the scheduler log if needed.

For `warning`:

1. Open `p5_p4_smoke_notification_preview.json`.
2. Review `failed_checks`.
3. Check whether zero-row or warning datasets are expected for the trade date.
4. Rerun `p4-read-model-smoke` after correction.

For `critical`:

1. Open the preview and identify blocked checks.
2. Rerun P4 orchestration for the same trade date.
3. Confirm P2/P3 source artifacts and read models.
4. Rerun `p4-read-model-smoke`.
5. Regenerate P5 notification artifacts from the new smoke log.

## Safety Notes

- P5 notification artifacts must not include webhook URLs, tokens, credentials,
  broker data, or order payloads.
- `critical` is an operational alert severity, not a trading instruction.
- Scheduler notification remains opt-in through `P5_NOTIFY=1`.
- Feishu preview is still dry-run and local.
- Live Feishu sending is not enabled by the wrapper.
