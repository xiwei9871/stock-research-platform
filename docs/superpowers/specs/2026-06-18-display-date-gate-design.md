# Display Date Gate Design

## Goal

Keep the dashboard on the latest trustworthy strategy trading day, not merely the latest database date. The page should show the current trading day's strategy, review, and market state only after the 20:30 strategy EOD run finishes and all required strategy contracts pass validation.

## Business Rule

The platform has two daily milestones in Asia/Shanghai time:

- 20:00: data completion window. Base market data, factors, LHB features, scores, market monitor inputs, news, and report sync should be complete or explicitly marked partial.
- 20:30: strategy publication window. The three official strategies run from the accepted balanced contracts and write EOD artifacts plus manifest entries.

Before 20:30, the dashboard keeps showing the most recent `display_ready` trading day. After 20:30, if today is a trading day and all required modules for today are complete and contract-valid, the dashboard switches to today. If today is not a trading day, or if any required module fails, the dashboard remains on the most recent `display_ready` trading day and surfaces the blocking reason in readiness.

## Display Readiness Definition

A trade date is `display_ready=true` only when these checks pass for one manifest run:

- Base data: `daily_bars`, `technical_features`, `score_topn`, and `lhb_features` are successful for that trade date.
- Strategy execution: `strategy_lhb_shortline`, `strategy_mid_trend`, and `strategy_tech_bottleneck` are successful for that trade date.
- Strategy contracts: each strategy summary passes the accepted balanced identity contract.
- Review chain: `review_queue_strategy_manifest` is successful and tied to the same trade date.

Content modules such as news, research reports, generated reports, and snapshots should be reported in health checks but should not block strategy display readiness in v1.

## Architecture

Add a focused dashboard backend module, `display_date_gate`, that reads `ops.data_run_manifest`, validates strategy contract identity, and selects the authoritative display date. Frontend workspaces should not infer the date themselves; they should use the backend's `display_trade_date` as the default date for Home, Review Queue, Market Monitor, Evidence Digest, and Stock Workspace.

Existing manifest writes stay intact. The new module acts as a read-side gate. Future scheduled jobs can add an explicit `display_ready` manifest module, but v1 can compute readiness from existing module rows and strategy contract validation.

## API Shape

Expose display gate information in `/api/platform/readiness` and `/api/platform/summary`, and add a small dedicated endpoint at `/api/platform/display-date`:

```json
{
  "display_trade_date": "2026-06-17",
  "candidate_trade_date": "2026-06-18",
  "latest_market_date": "2026-06-18",
  "cutoff_time": "20:30",
  "timezone": "Asia/Shanghai",
  "display_status": "ready",
  "candidate_status": "before_cutoff",
  "strategy_ready": "3/3",
  "contract_valid": "3/3",
  "blocking_reasons": []
}
```

Status values:

- `ready`: selected date is publishable.
- `before_cutoff`: today's data may exist, but strategy publication window has not opened.
- `not_trading_day`: today's date is not a market trading date in available data.
- `incomplete`: candidate date is missing required modules.
- `contract_mismatch`: one or more strategy artifacts failed contract validation.
- `missing`: no display-ready date exists.

## Page Behavior

All default dashboard reads should use `display_trade_date`. Historical selectors may still request older dates explicitly. If a workspace is opened without a date, it should use `display_trade_date`.

Home strategy cards must not show performance metrics from contract-failed artifacts. If the selected date has no contract-valid strategy result, the card should display a clear unavailable state such as `正式策略产物待生成` rather than stale return/drawdown numbers.

## Scheduled Operation

The repo should provide operator-safe commands and docs for two local schedules:

- 20:00 data completion command.
- 20:30 strategy EOD command that runs official balanced contracts, writes manifests, and emits display gate status.

Installing launchd/cron entries should remain explicit operator action. The code should generate or document the commands rather than silently modifying the host scheduler.

## Testing

Backend tests should cover:

- before 20:30 keeps the prior ready date.
- after 20:30 switches to today when all required modules and contracts pass.
- after 20:30 keeps the prior ready date when strategy modules fail.
- after 20:30 keeps the prior ready date when any strategy contract mismatches.
- non-trading day keeps the most recent ready date.
- strategy cards hide metrics for contract-failed artifacts.

Frontend tests should cover:

- Home uses `display_trade_date` from platform readiness/summary.
- Review Queue and Market Monitor default to `display_trade_date`.
- Strategy cards render a blocked state instead of stale metrics when contract validation fails.
