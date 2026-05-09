# Daily Factor Pipeline Runbook

## Purpose

Run the local A-share factor scoring pipeline after market data is updated.

## Commands

Apply schema:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research apply-research-schema
```

Build factor daily:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research build-factor-daily --trade-date YYYY-MM-DD --lookback-bars 130
```

Score factor daily:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research score-factor-daily --trade-date YYYY-MM-DD --score-version manual_v1
```

Show Top30:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research show-top-scores --trade-date YYYY-MM-DD --score-version manual_v1 --top-n 30
```

Run full daily pipeline:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research run-daily-factor-pipeline --trade-date YYYY-MM-DD --score-version manual_v1 --top-n 30 --lookback-bars 130
```

## Expected Outputs

- `factor.factor_daily` has rows for the trade date.
- `factor.stock_score_daily` has ranked rows for the trade date.
- TopN command prints ranked candidates.
- Reports are written under `reports/`, which is ignored by Git.

## Guardrails

- Do not use finance factors unless `announcement_date <= trade_date`.
- Do not treat TopN as a buy signal.
- Do not change V3 strategy thresholds in this pipeline.
- Alpha101 / GTJA191 / Qlib-style factors are research candidates until factor evaluation approves them for scoring.
