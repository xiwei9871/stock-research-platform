# Mid Trend Round 2 Optimization Runbook

## Command

```bash
cd /Users/xiwei/stock_research
.venv/bin/python -m stock_research.cli mid-trend-round2-optimize \
  --start-date 2025-01-01 \
  --train-end-date 2026-02-01 \
  --end-date 2026-06-02 \
  --output-dir outputs/research/mid_trend_round2
```

## Outputs

- `mid_trend_round2_baseline_train_summary.csv`
- `mid_trend_round2_baseline_test_summary.csv`
- `mid_trend_round2_failure_mode_summary.csv`
- `mid_trend_round2_candidate_audit.csv`
- `mid_trend_round2_report.md`
