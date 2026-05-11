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

Evaluate multiple candidate factors before scoring promotion:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research evaluate-factor-gate-batch --factor-names alpha101_delta_close_1_rank,gtja191_amount_momentum_5_10,qlib_ret_5 --start-date YYYY-MM-DD --end-date YYYY-MM-DD --horizons 5,10,20,60 --primary-horizon 5 --score-version manual_v1
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

Build daily report bundle from generated report paths:

```python
from stock_research.reports.daily_report_bundle import write_daily_report_bundle

print(write_daily_report_bundle(
    trade_date="YYYY-MM-DD",
    report_paths={
        "topn": "reports/daily_topn_YYYY-MM-DD_manual_v1.md",
        "market_state": "reports/market_state/market_state_YYYY-MM-DD_CSI300.md",
        "sector_strength": "reports/sector_strength/sector_strength_YYYY-MM-DD_csrc.md",
        "risk_alerts": "reports/risk_alerts/risk_alerts_YYYY-MM-DD.md",
        "position_review": "reports/position_review/position_review_YYYY-MM-DD.md",
    },
))
```

Write the full daily research report set from in-memory research outputs:

```python
from stock_research.reports.daily_research_report_workflow import write_daily_research_reports

result = write_daily_research_reports(
    trade_date="YYYY-MM-DD",
    score_version="manual_v1",
    top_scores=top_scores,
    market_state=market_state,
    sector_strength=sector_strength,
    positions=positions,
    feature_snapshot=feature_snapshot,
)
print(result["report_paths"]["bundle"]["markdown_path"])
```

Run the daily research report module CLI:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python -m stock_research.reports.daily_research_report_cli --trade-date YYYY-MM-DD --score-version manual_v1 --top-n 30 --index-id CSI300 --industry-system csrc --reports-dir reports
```

Run the same report through the main `stock-research` CLI:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research run-daily-research-report --trade-date YYYY-MM-DD --score-version manual_v1 --top-n 30 --index-id CSI300 --industry-system csrc --reports-dir reports
```

The module enriches TopN candidates from `core.industry_membership` before risk alert generation, so sector weakness checks use point-in-time industry context.
Use `--apply-report-run-schema --record-run` to initialize `report.report_run` and persist the generated report paths.

Generate a cron entry for review:

```python
from stock_research.reports.daily_research_cron import build_daily_research_cron_entry

print(build_daily_research_cron_entry())
```

## Historical Approved-Factor Research Loop

Use this flow when testing factor effectiveness. `factor.factor_daily` stores candidate factors. A stored factor is not effective until `factor.factor_approval` records `status='approved'` for the target score version.

The current 2024-2026 data range is a smoke-test slice, not a research-grade full-history base.
For full-history A-share buildout, run Phase 0 safety checks before starting any long mutation job:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research data-audit --expected-start-date 1990-12-01
/Users/xiwei/stock_research/.venv/bin/stock-research reset-stale-ingest-jobs --dataset baostock-finance --older-than-minutes 60
/Users/xiwei/stock_research/.venv/bin/stock-research research-preflight --start-date 1990-12-01 --horizons 5,10,20,60 --min-label-dates 20
```

Use the Phase 1 backfill control plane to create and supervise long historical jobs before a dataset-specific worker is attached:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research create-backfill-run --run-id daily-bars-1990-current-v1 --dataset daily-bars --source baostock --source-version v1 --start-date 1990-12-01 --end-date YYYY-MM-DD --months-per-partition 1
/Users/xiwei/stock_research/.venv/bin/stock-research backfill-status --run-id daily-bars-1990-current-v1
/Users/xiwei/stock_research/.venv/bin/stock-research claim-backfill-tasks --run-id daily-bars-1990-current-v1 --limit 10
/Users/xiwei/stock_research/.venv/bin/stock-research mark-backfill-task-success --task-id TASK_ID --rows-read 0 --rows-written 0
/Users/xiwei/stock_research/.venv/bin/stock-research mark-backfill-task-failed --task-id TASK_ID --error-message ERROR
/Users/xiwei/stock_research/.venv/bin/stock-research reset-stale-backfill-tasks --dataset daily-bars --older-than-minutes 60
```

Seed Phase 2 dimensions before full-history dataset loaders depend on them:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research seed-trading-calendar --start-date 1990-12-01 --end-date YYYY-MM-DD --exchanges SH,SZ --source-version derived_market_daily_bar_v1
/Users/xiwei/stock_research/.venv/bin/stock-research sync-asset-lifecycle --source-version core_asset_master_v1
/Users/xiwei/stock_research/.venv/bin/stock-research data-audit --expected-start-date 1990-12-01
```

Archive Phase 3 raw Baostock daily bars while loading normalized market bars:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research load-bars --start-date 1990-12-19 --end-date YYYY-MM-DD --archive-raw
/Users/xiwei/stock_research/.venv/bin/stock-research data-audit --expected-start-date 1990-12-01
```

Build Phase 4 tradability, adjustment factors, and derived corporate action events:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research build-asset-status --start-date 1990-12-19 --end-date YYYY-MM-DD --adjust-type hfq
/Users/xiwei/stock_research/.venv/bin/stock-research build-adjustment-factors --start-date 1990-12-19 --end-date YYYY-MM-DD --source-version derived_market_daily_bar_v1
/Users/xiwei/stock_research/.venv/bin/stock-research build-corporate-actions --start-date 1990-12-19 --end-date YYYY-MM-DD --source-version derived_market_daily_bar_v1
/Users/xiwei/stock_research/.venv/bin/stock-research data-audit --expected-start-date 1990-12-01
```

Build Phase 5 benchmark bars and point-in-time index constituent snapshots:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research sync-index-bars --start-date 1990-12-19 --end-date YYYY-MM-DD
/Users/xiwei/stock_research/.venv/bin/stock-research sync-index-constituents --trade-date YYYY-MM-DD --index-ids SSE_50,CSI_300,CSI_500 --source-version baostock_snapshot_v1
/Users/xiwei/stock_research/.venv/bin/stock-research data-audit --expected-start-date 1990-12-01
```

Run a Phase 6 single-day benchmark before any industry-history range job:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research benchmark-industry-day --trade-date YYYY-MM-DD --industry-system csrc --adjust-type hfq --no-cache
/Users/xiwei/stock_research/.venv/bin/stock-research benchmark-industry-day --trade-date YYYY-MM-DD --industry-system csrc --adjust-type hfq
/Users/xiwei/stock_research/.venv/bin/stock-research backfill-industry-history --start-date YYYY-MM-DD --end-date YYYY-MM-DD --max-dates N --frequency monthly --industry-system csrc --adjust-type hfq
/Users/xiwei/stock_research/.venv/bin/stock-research research-preflight --start-date YYYY-MM-DD --end-date YYYY-MM-DD --require-industry-membership
```

For a quick optimization comparison, run the same date twice: the first pass warms the raw industry snapshot cache, the second pass should be much faster. Use `--frequency monthly` to probe a longer window with far fewer remote calls before choosing a daily range.

Build Phase 7 point-in-time finance statements from AKShare after the finance schema is applied:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research apply-research-schema
/Users/xiwei/stock_research/.venv/bin/stock-research create-ingest-jobs --dataset akshare-finance-statements --start-year 1990 --end-year 2026 --batch-size 5
/Users/xiwei/stock_research/.venv/bin/stock-research run-ingest-jobs --dataset akshare-finance-statements --limit-jobs 1
/Users/xiwei/stock_research/.venv/bin/stock-research finance-audit
```

After the smoke job writes balance-sheet and cash-flow rows without source errors, continue with conservative single-worker batches:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research run-ingest-loop --dataset akshare-finance-statements --jobs-per-round 5 --sleep-seconds 10 --report-target CHAT_OR_GROUP_ID
/Users/xiwei/stock_research/.venv/bin/stock-research finance-audit
/Users/xiwei/stock_research/.venv/bin/stock-research data-audit --expected-start-date 1990-12-01
```

Phase 7 finance factors must use only rows with `announcement_date <= trade_date`; use the TTM helpers in `stock_research.services.finance_ttm` for cumulative income-statement fields.

1. Refresh full-history forward-return labels from the derived market window:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research backfill-labels --horizons 5,10,20,60
```

2. Find the latest label-covered end date. When `--start-date` is omitted, preflight derives the start from `market_daily_bar` coverage rather than the old 2024 smoke-test slice:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research research-preflight --horizons 5,10,20,60 --min-label-dates 20
```

Before candidate factors are backfilled, this command may print `research_preflight|coverage|blocked|factor_dates|0`.
That is expected for a fresh historical range. In this step, use only `research_preflight|latest_common_label_date|...` to choose `END_DATE`.

3. Capture the label-covered end date and backfill all current candidate factors:

```bash
END_DATE=$(/Users/xiwei/stock_research/.venv/bin/stock-research research-preflight --horizons 5,10,20,60 --min-label-dates 20 | awk -F'|' '/latest_common_label_date/ {print $3}')
/Users/xiwei/stock_research/.venv/bin/stock-research backfill-factor-daily --end-date "$END_DATE" --lookback-bars 130 --industry-system csrc --skip-complete --workers 4
```

4. Re-run preflight with the same end date and require candidate-factor coverage:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research research-preflight --end-date "$END_DATE" --horizons 5,10,20,60 --min-label-dates 20
/Users/xiwei/stock_research/.venv/bin/stock-research data-audit --expected-start-date 1990-12-01
```

At this point, `research_preflight|coverage|ok|...` is required before factor-gate evaluation.

5. Batch evaluate default candidate factors:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research evaluate-factor-gate-batch --start-date 1990-12-01 --end-date "$END_DATE" --horizons 5,10,20,60 --primary-horizon 5 --score-version manual_v1
```

6. Score the historical range with approved factors only from Python until a dedicated CLI command is added:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python -c "from stock_research.approved_scoring_workflow import score_approved_factors_range; result = score_approved_factors_range('1990-12-01', '$END_DATE', score_version='manual_v1'); print(result.to_string(index=False)); print('approved_score_rows|' + str(int(result['score_rows'].sum()) if not result.empty else 0))"
```

7. Run TopN research workflow on approved-only scores:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python -m stock_research.research_workflow_cli --start-date 2024-01-01 --end-date "$END_DATE" --score-version manual_v1 --top-n 20 --rebalance-frequency weekly --transaction-cost-bps 10 --max-positions 20 --strategy-id approved_topn_weekly_v1
```

## Expected Outputs

- `factor.factor_daily` has rows for the trade date.
- `label_snapshot` has 5d, 10d, 20d, and 60d forward return labels.
- `factor.factor_approval` records candidate factor gate status before scoring promotion.
- Batch factor gate command can evaluate and persist approvals for multiple external reference factors.
- `factor.stock_score_daily` has ranked rows for the trade date.
- TopN command prints ranked candidates.
- Daily TopN report writes markdown and CSV files with rank, asset, total score, score version, score components, and a candidate-pool guardrail.
- TopN research workflow prints `topn_research_workflow|...` paths and writes a markdown tear sheet plus metrics/equity/positions CSV files.
- Sector strength report writes markdown and CSV files under `reports/sector_strength/`.
- Market state report writes markdown and CSV files under `reports/market_state/`.
- Risk alert report writes markdown and CSV files under `reports/risk_alerts/`.
- Position review report writes markdown and CSV files under `reports/position_review/`.
- Daily report bundle writes an index markdown file under `reports/daily/`.
- Daily research report workflow writes TopN, market state, sector strength, risk alerts, position review, and bundle reports in one call.
- Daily research report module CLI prints stable `daily_research_report|...` report paths.
- Main `stock-research run-daily-research-report` prints the same stable report paths.
- Cron helper can generate a weekday report command for manual installation.
- Optional report run recording writes generated report paths to `report.report_run`.
- Reports are written under `reports/`, which is ignored by Git.

## Guardrails

- Do not use finance factors unless `announcement_date <= trade_date`.
- Do not treat TopN as a buy signal.
- Do not change V3 strategy thresholds in this pipeline.
- Alpha101 / GTJA191 / Qlib-style factors are research candidates until factor evaluation approves them for scoring.
- Code-level scoring can enforce the factor gate with `score_stored_factor_daily(..., approved_only=True)`, which loads only factors marked `approved` in `factor.factor_approval` for the requested `score_version`. The main CLI keeps its current compatible default until unrelated `cli.py` changes are resolved.
