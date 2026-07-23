# LHB Rule Governance Phase A Completion — 2026-07-15

## Outcome

Phase A replaced the fragmented LHB safety rules with the versioned `lhb_eligibility_v2` contract and enforced that decision from the full-market candidate pool through lifecycle, account entry, EOD publication, score audit, and Dashboard review inputs.

The implementation also fixed two adjacent execution/scoring defects discovered during regression:

- positive `high_to_close_drawdown` had not been penalized because the scorer clipped the wrong sign;
- a next-bar locked-limit-up execution helper returned the bar without checking whether it was tradable.

## Verification

Focused regression command:

```bash
rtk .venv/bin/pytest -q \
  tests/test_lhb_eligibility.py \
  tests/test_core_data.py \
  tests/test_lhb_data.py \
  tests/test_lhb_shortline_v1.py \
  tests/test_lhb_review_policy.py \
  tests/test_strategy_eod_publish.py \
  tests/test_strategy_score_audit.py \
  tests/test_dashboard_review_queue.py
```

Result: **161 passed**, with two third-party Python 3.14 deprecation warnings.

Asset status was rebuilt for `2026-01-05` through `2026-07-14` using same-day LHB names as the first point-in-time ST-status source.

Comparable replay configuration:

- start: `2026-01-01` (first effective signal date `2026-01-05`)
- end: `2026-07-14`
- Top-N: 5
- risk profile: `balanced`
- adjustment: `hfq`
- transaction cost: 10 bps per side
- max position weight: 20%
- output: `outputs/research/lhb_rule_governance_phase_a_20260105_20260714`

Safety assertions:

- rejected-event / filled-trade overlap: **0**
- parity mismatches: **0**
- missing or wrong contract versions: **0**
- parity rows: **1,260**, all `match`
- rejected events: **356**
  - delisting-period: **117**
  - near-limit-down: **239**

## Comparable Performance

| Metric | Previous run | Phase A | Change |
|---|---:|---:|---:|
| Final equity | 2.839346 | 1.913312 | -0.926034 |
| Total return | 183.93% | 91.33% | -92.60 pp |
| Maximum drawdown | -8.42% | -5.12% | +3.31 pp improvement |
| Filled trades | 245 | 192 | -53 |

The return difference is not attributable only to two hard gates. Correcting the drawdown sign changed rankings broadly, and the locked-limit-up execution fix removed fills that were not executable.

Among the previous final-account trades, ten are explicitly rejected by the new contract:

- six delisting-period fills contributed `+0.125319` account PnL;
- four near-limit-down fills contributed `+0.051690` account PnL;
- three of those four near-limit-down trades lost money; one large winner made the average positive, so the sample does not support treating limit-down entry as a reliable next-day rebound strategy.

## 2026-07-14 EOD Republish

Command:

```bash
rtk .venv/bin/python -m stock_research.strategy_eod_publish \
  --trade-date 2026-07-14 \
  --output-root outputs
```

Result:

- LHB review rows: **9**
- confirmed Top5 focus: **5**
- risk-watch rows: **4**
- LHB score-audit anomalies: **0**
- all rows carry `lhb_eligibility_v2`
- 惠科股份 `001399.SZ`: score `69.36979856319499`, `risk_watch`, not Top5 eligible, not account-entry eligible, reason `near_limit_down_followthrough_risk`

Primary artifacts:

- `outputs/research/lhb_rule_governance_phase_a_20260105_20260714/lhb_full_market_pool_rejected_events_v2.csv`
- `outputs/research/lhb_rule_governance_phase_a_20260105_20260714/lhb_eligibility_parity_audit_v2.csv`
- `outputs/research/lhb_rule_governance_phase_a_20260105_20260714/lhb_shortline_v1_summary.json`
- `outputs/research/strategy_daily_eod/2026-07-14/strategy_lhb_shortline_review.csv`
- `outputs/research/strategy_daily_eod/2026-07-14/strategy_score_audit_detail.csv`

The three pre-existing `tech_bottleneck_review_universe_frontend_*` worktree modifications were left untouched and uncommitted.
