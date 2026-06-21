# Tech Bottleneck Discovery v0.1 Experiment Conclusion

## Verdict

The v0.1 baseline is temporarily usable for research and paper trading style observation. It should not be treated as final production allocation logic yet.

## Accepted Baseline

`strict pool + ST-only exclusion + weekly Top5 + tight3b_bt100 market exposure + rank_exit_top10_1d`

## Why This Baseline

- Weekly Top5 produced the best balance among the tested top-N/rebalance variants.
- Weekly trading did not turn into excessive daily churn in this implementation; average daily turnover is 8.48%.
- ST-only exclusion is a reasonable minimum risk control for a non-ultrashort strategy.
- Additional industry or financial hard filters reduced return without improving drawdown enough to justify v0.1 adoption.

## Main Backtest Result

- Window: `2025-01-01` to `2026-06-05`
- Total return: 214.36%
- Annualized return: 132.55%
- Annualized volatility: 28.44%
- Sharpe: 3.11
- Max drawdown: -17.85%
- Calmar: 7.43
- Transaction cost sum: 5.80%

## What It Proves

- The bottleneck pool plus trend/rank portfolio construction can concentrate into strong technology momentum names.
- The method is usable as a candidate/ranking overlay, not just a static theme label.
- Source evidence quality is now adequate for rolling review instead of more broad data completion.

## What It Does Not Prove

- Long-cycle robustness across bear markets.
- Whether partial evidence fields are alpha-positive or just neutral audit metadata.
- Whether Top5 concentration is capacity-safe for larger capital.
- Whether the baseline remains optimal beyond the 2025-01-01 to 2026-06-05 sample.

## Next Phase

Run rolling review from 2025-01-01 to the latest available backtest date, with emphasis on monthly/quarterly behavior, rolling 63d/126d windows, drawdown episodes, turnover, and holdings attribution.
