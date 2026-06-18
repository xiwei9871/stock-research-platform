# Intraday Pipeline Runbook

The intraday pipeline prepares the T+1 short-line decision universe and polls
only those symbols for 5-minute bars.

## Commands

```bash
.venv/bin/python -m scripts.intraday_signal_pipeline --date 20260618 --previous-date 20260617 --stage universe --top-n 20 --score-version manual_v1
.venv/bin/python -m scripts.intraday_signal_pipeline --date 20260618 --stage minute5
.venv/bin/python -m scripts.intraday_signal_pipeline --date 20260618 --stage sentiment
.venv/bin/python -m scripts.intraday_signal_pipeline --date 20260618 --stage status
```

The project CLI exposes the same stages:

```bash
.venv/bin/stock-research intraday-pipeline --date 20260618 --stage status
```

## Universe

`ops.intraday_universe_member` combines:

- previous trading day's topN scores;
- previous trading day's watchlist signals;
- latest current positions from `simulation.virtual_portfolio_position_daily`.

Current positions are included for sell and forced-exit checks. The 5-minute
poller reads this table and does not request all-market minute bars.

## Market Sentiment

`sentiment` uses AkShare Eastmoney all-A snapshot and limit pool endpoints to
capture breadth, limit-up, limit-down, and break-limit counts. If the source is
temporarily unavailable, the job is recorded as failed in `ops.intraday_job`
without blocking minute-bar polling.

## Dashboard

```bash
curl 'http://127.0.0.1:8765/api/intraday/status?date=20260618'
```
