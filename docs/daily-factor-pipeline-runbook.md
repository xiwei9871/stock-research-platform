# Daily Factor Pipeline Runbook

## Purpose

Run the local A-share factor scoring pipeline after market data is updated.

## Commands

Apply schema:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research apply-research-schema
```

Refresh forward return labels:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research labels --end-date YYYY-MM-DD
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

Evaluate a candidate factor before scoring promotion:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research evaluate-factor-gate --factor-name FACTOR_NAME --start-date YYYY-MM-DD --end-date YYYY-MM-DD --horizons 5,10,20,60 --primary-horizon 5 --score-version manual_v1
```

Run full daily pipeline:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research run-daily-factor-pipeline --trade-date YYYY-MM-DD --score-version manual_v1 --top-n 30 --lookback-bars 130
```

Run TopN research workflow and write performance tear sheet:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python -m stock_research.research_workflow_cli --start-date YYYY-MM-DD --end-date YYYY-MM-DD --score-version manual_v1 --top-n 20 --rebalance-frequency weekly --transaction-cost-bps 10 --max-positions 20 --strategy-id topn_weekly_v1
```

This module entrypoint is intentionally separate from the main `stock-research` CLI until the current unrelated `cli.py` work is merged or cleaned up.

Build sector strength report:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python -c "from stock_research.reports.sector_strength_report import load_sector_strength_bars, calc_sector_strength, write_sector_strength_report; bars = load_sector_strength_bars('YYYY-MM-DD', 'YYYY-MM-DD', industry_system='csrc'); strength = calc_sector_strength(bars, trade_date='YYYY-MM-DD', top_n=20); print(write_sector_strength_report(strength, trade_date='YYYY-MM-DD', industry_system='csrc'))"
```

Build market state report:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python -c "from stock_research.reports.market_state_report import load_market_state_bars, calc_market_state, write_market_state_report; bars = load_market_state_bars('YYYY-MM-DD', 'YYYY-MM-DD', index_id='CSI300'); state = calc_market_state(bars, trade_date='YYYY-MM-DD', index_id='CSI300'); print(write_market_state_report(state))"
```

Build risk alert report from in-memory research outputs:

```python
from stock_research.reports.risk_alert_report import generate_risk_alerts, write_risk_alert_report

alerts = generate_risk_alerts(
    trade_date="YYYY-MM-DD",
    top_scores=top_scores,
    market_state=market_state,
    sector_strength=sector_strength,
    feature_snapshot=feature_snapshot,
)
print(write_risk_alert_report(alerts, trade_date="YYYY-MM-DD"))
```

## Expected Outputs

- `factor.factor_daily` has rows for the trade date.
- `label_snapshot` has 5d, 10d, 20d, and 60d forward return labels.
- `factor.factor_approval` records candidate factor gate status before scoring promotion.
- `factor.stock_score_daily` has ranked rows for the trade date.
- TopN command prints ranked candidates.
- Daily TopN report writes markdown and CSV files with rank, asset, total score, score version, score components, and a candidate-pool guardrail.
- TopN research workflow prints `topn_research_workflow|...` paths and writes a markdown tear sheet plus metrics/equity/positions CSV files.
- Sector strength report writes markdown and CSV files under `reports/sector_strength/`.
- Market state report writes markdown and CSV files under `reports/market_state/`.
- Risk alert report writes markdown and CSV files under `reports/risk_alerts/`.
- Reports are written under `reports/`, which is ignored by Git.

## Guardrails

- Do not use finance factors unless `announcement_date <= trade_date`.
- Do not treat TopN as a buy signal.
- Do not change V3 strategy thresholds in this pipeline.
- Alpha101 / GTJA191 / Qlib-style factors are research candidates until factor evaluation approves them for scoring.
- Code-level scoring can enforce the factor gate with `score_stored_factor_daily(..., approved_only=True)`, which loads only factors marked `approved` in `factor.factor_approval` for the requested `score_version`. The main CLI keeps its current compatible default until unrelated `cli.py` changes are resolved.
