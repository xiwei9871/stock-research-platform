# Mid Trend Soft Ownership Runbook

## Purpose

This command runs the baseline-safe `mid_trend_soft_ownership` experiment on the fixed main window:

- `start_date=2025-01-01`
- `end_date=2026-06-12`

The current implementation keeps baseline and variants in a separate experimental layer and writes standalone outputs.

## Command

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/stock-research mid-trend-soft-ownership-optimize \
  --output-dir outputs/research/mid_trend_soft_ownership_optimization_manual
```

## Variants

Default variants:

- `baseline`
- `entry_soft_weight_v1`
- `ownership_hold_v1`
- `partial_exit_v1`
- `combined_soft_ownership_v1`

## Outputs

The command writes:

- `code_audit.md`
- `baseline_vs_variants.csv`
- `baseline_vs_variants.md`
- `trade_level_diagnostics.csv`
- `ownership_event_diagnostics.csv`
- `exit_event_diagnostics.csv`
- `bucket_contribution_entry_weight.csv`
- `suppressed_exit_analysis.csv`
- `final_interpretation.md`

## Interpretation Rules

- Released weight must stay in cash.
- Baseline and all variants must use the same main window.
- PnL is the primary evaluation target.
- `bad_buy` and `bad_sell` are secondary diagnostics only.
