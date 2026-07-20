# Daily Close Heartbeat Notification Design

## Goal

Keep long-running daily-close diagnostics available to operators without sending machine-oriented heartbeat lines to the Feishu group. Preserve one concise human-readable final notification for success or failure, then use auto EOD repair to restore the 2026-07-20 platform state.

## Root Cause

`scripts/run_daily_close_pipeline_cron.sh` writes a heartbeat to stdout every five minutes. The OpenClaw `stock-daily-close-minute5-baostock` cron uses Feishu `announce` delivery and stores command stdout as its diagnostic summary. When the command fails, the failure alert therefore contains the accumulated heartbeat stream.

The 2026-07-20 minute5 run also overlapped the 2022 historical BaoStock backfill. Both processes used BaoStock concurrently, contributing to the incomplete minute5 result.

## Selected Design

1. Keep heartbeat generation, but append heartbeat lines only to the per-run detail log.
2. Keep stdout limited to the final Chinese success or failure summary. The initial machine-oriented `started` line will also move to the detail log so Feishu receives only the final summary.
3. Increase the OpenClaw minute5 cron `noOutputTimeoutSeconds` to the command timeout boundary so the lack of stdout heartbeat does not terminate a healthy long-running job.
4. Preserve final Feishu delivery and failure alerts. Do not disable useful human-facing completion or failure notifications.
5. Before repair, pause the 2022 historical backfill and restore its unprocessed claimed jobs to `pending`, ensuring auto EOD repair has exclusive BaoStock access.
6. Stop the currently overlapping daily-close finalize retry, then run `scripts/run_eod_auto_repair_cron.sh 2026-07-20` as the single repair owner.

## Error Handling

- Heartbeats remain available in `logs/cron/daily_close_pipeline_*.log` for diagnosis.
- The wrapper still returns the underlying pipeline exit code.
- Failure stdout contains only the compact Chinese summary and log path.
- Auto EOD repair remains guarded by its existing lock and action timeout.
- If repair cannot reach READY, report the precise remaining failed actions and artifacts rather than claiming completion.

## Tests

1. Update the wrapper test to assert heartbeat is absent from stdout and present in the detail log.
2. Assert the final human-readable summary remains in stdout.
3. Run the focused daily-close script tests.
4. Verify the OpenClaw cron configuration has the updated no-output timeout and still uses Feishu final delivery.
5. Run auto EOD repair and inspect `run_summary.json`, `run_report.md`, the platform-ready result, and the final minute5 coverage.

## Scope

This change affects only daily-close wrapper output routing and the minute5 cron timeout configuration. It does not remove diagnostic heartbeats, change data ingestion logic, alter Feishu targets, or modify unrelated pipeline behavior.
