# Dashboard Display Date Gate Runbook

## Purpose

The dashboard should show the latest completed and contract-valid strategy trading day, not the newest partially loaded data date.

This matters for backtests and review queues: before a trading day is fully published, the UI must not mix today's market data with stale strategy returns, positions, or review artifacts.

## Daily Schedule

| Time | Job | Expected Result |
| --- | --- | --- |
| 20:00 Asia/Shanghai | Complete base data and dependencies | Daily bars, factors, scores, LHB data, market emotion, news/research/report links are available for the latest trading day. |
| 20:30 Asia/Shanghai | Run official strategy EOD publish | LHB Shortline, Mid Trend, and Tech Bottleneck write contract-valid strategy summaries and review artifacts into `ops.data_run_manifest`. |
| After 20:30 | Dashboard may switch display date | Only if the latest trading day has all required modules and strategy contracts validate. |

If today is not a trading day, the dashboard keeps the latest display-ready trading day.

## Required Manifest Modules

The display date gate requires these modules for a date/run to be considered ready:

- `daily_bars`
- `technical_features`
- `score_topn`
- `lhb_features`
- `review_queue_strategy_manifest`
- `strategy_lhb_shortline`
- `strategy_mid_trend`
- `strategy_tech_bottleneck`

Strategy modules must be `success` and their `metadata.summary` must match the balanced strategy contract.

## How The Gate Works

1. Group manifest rows by `trade_date`.
2. Evaluate each `(trade_date, run_id)` independently so partial same-day runs do not get mixed.
3. Validate required base, strategy, and review modules.
4. Validate strategy summaries against the balanced contract.
5. Before 20:30, if the latest candidate date is local today, publish the prior ready trading date.
6. After 20:30, publish the candidate date only if it is ready.
7. If the candidate is incomplete or contract-mismatched, fall back to the newest prior ready date.

## Operator Checks

Use:

```bash
curl -s http://127.0.0.1:8765/api/platform/display-date | jq
curl -s http://127.0.0.1:8765/api/platform/readiness | jq '.display_trade_date, .candidate_trade_date, .display_gate, .missing_data, .warnings'
```

Healthy post-publish result:

- `display_trade_date` equals the latest trading day.
- `display_gate.display_status` is `ready`.
- `display_gate.strategy_ready` is `3/3`.
- `display_gate.contract_valid` is `3/3`.
- `missing_data` does not include `display_trade_date`.

Expected pre-20:30 trading-day result:

- `candidate_trade_date` may be today.
- `display_trade_date` remains the prior ready trading day.
- `display_gate.candidate_status` is `before_cutoff`.

## Troubleshooting

If the dashboard is still showing the prior date after 20:30:

1. Check `display_gate.blocking_reasons`.
2. Confirm all required modules exist for the candidate date and have `status = success`.
3. Confirm all three strategy summaries match the balanced strategy contracts.
4. Confirm `review_queue_strategy_manifest` exists for the same run/date as the strategy modules.
5. Confirm the backend process has been restarted if the code or scheduler changed.
6. Clear dashboard EOD cache or restart the backend if stale cached responses persist.

If strategy cards show no metrics:

- Check whether the strategy artifact is contract-mismatched.
- Contract-mismatched metrics are intentionally hidden so old return/drawdown figures do not appear as current.

If Review Queue or Market Monitor default to the wrong day:

- Call `/api/platform/display-date`.
- Then call `/api/review-queue` and `/api/market-monitor/eod` without `trade_date`.
- All three should agree on the default display date unless an explicit historical date was requested.
