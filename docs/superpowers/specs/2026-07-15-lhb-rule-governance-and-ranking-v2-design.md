# LHB Rule Governance and Ranking v2 Design

## 1. Purpose

This design removes the remaining rule inconsistencies in the LHB Shortline strategy and then recalibrates its Top5 ranking. The work follows this fixed order:

1. Reject delisting-period securities before candidate selection and backtesting.
2. Apply the near-limit-down gate in backtests as well as EOD publication.
3. Correct the high-to-close drawdown sign error.
4. Replace divergent eligibility rules with one shared contract.
5. Use point-in-time ST and price-limit state.
6. Distinguish pending confirmation from confirmed follow candidates in the Dashboard.
7. Recalibrate the Top5 score against point-in-time outcomes.

The objective is not to preserve the current headline return. If removing invalid trades lowers historical performance, the lower result is the correct result.

## 2. Evidence motivating the change

The latest full run from 2026-01-05 through 2026-07-14 contains 630 final candidates over 126 signal dates.

- Seventeen candidates were in a delisting period. Seven reached lifecycle fills and six entered the official auction-enhanced account.
- Those official delisting trades contributed about 7.26% of cumulative account PnL, so the current performance record is contaminated.
- Three official account trades started from near-limit-down signal days. All three lost money, averaging about -3.99%.
- The near-limit-down gate is currently called only by `strategy_eod_publish.py`, not by the candidate, lifecycle, or account engines.
- `high_to_close_drawdown` is stored as a positive ratio, but one LHB scorer clips it to `[-1, 0]`, eliminating the penalty. Correcting the sign changes Top10 membership on 15 of 126 dates and removes score overstatements as large as 32.35 points.
- Candidate paths use both `pump_risk < 0.75` and `pump_risk < 0.90`.
- Current ST status columns contain zero ST rows across the full market for 2026-07-01 through 2026-07-14, while LHB names contain ST-prefixed securities. The status source is therefore not reliable enough for price-limit decisions.
- Pre-confirmation ranks 1-5 did not outperform ranks 6-10. Five-day average returns were about 1.30% versus 1.92%, respectively.
- The strong historical metrics for `follow_pool` are post-confirmation metrics that use T+1 intraday data. They cannot validate the probability of a T-close pending candidate rising on T+1.

## 3. Scope decomposition

The program is implemented and accepted in three independently testable phases.

### Phase A: safety and rule consistency

Implements items 1-5. This phase introduces the shared eligibility contract and makes candidate selection, lifecycle simulation, account simulation, EOD publication, and score audit agree.

### Phase B: Dashboard state semantics

Implements item 6. This phase changes labels and review tiers without changing the Phase A eligibility decision.

### Phase C: point-in-time ranking calibration

Implements item 7. This is a research-and-promotion phase. A new score runs in shadow until it passes holdout acceptance gates.

Each phase receives its own implementation plan and verification checkpoint. Phase B cannot start until Phase A's parity tests pass. Phase C uses Phase A's filtered universe and cannot compensate for rejected delisting or limit-down records.

## 4. Shared eligibility contract

### 4.1 Component boundary

Create a focused module, `stock_research.lhb_eligibility`, which owns all security-level eligibility and risk classification. Existing candidate and publication code may calculate scores, but it may not implement independent hard thresholds.

The contract accepts a point-in-time candidate context and returns a decision object.

Required inputs:

- `trade_date`
- `asset_id` and `ts_code`
- point-in-time `stock_name`
- `stock_name_source`
- `lhb_reason`
- `close`, `preclose`, and `pct_chg`
- board and exchange
- point-in-time ST state and its source
- resolved price-limit regime and threshold
- `lhb_one_day_pump_risk`
- `high_to_close_drawdown`
- required-field availability flags

Required outputs:

- `eligibility_status`: `eligible`, `risk_watch`, or `hard_reject`
- `top5_eligible`
- `backtest_entry_eligible`
- `reason_codes`
- `reason_texts`
- `warning_codes`
- `price_limit_regime`
- `near_limit_down_threshold`
- `data_quality_status`
- `contract_version`

The first production version is `lhb_eligibility_v2`.

### 4.2 Decision precedence

Rules run in this order so one component cannot override a more serious decision:

1. Delisting and delisting-period rules.
2. Missing point-in-time price-limit data.
3. Near-limit-down rules.
4. Pump-risk rules.
5. Drawdown and other warning-only rules.

`hard_reject` always wins over `risk_watch`, which wins over `eligible`.

### 4.3 Delisting rule

A candidate is `hard_reject` when any point-in-time reason or security state contains a delisting-period marker, including `退市整理`, `退市整理期`, or an equivalent normalized code.

Consequences:

- It is removed before daily candidate ranking.
- It cannot enter intraday confirmation, lifecycle simulation, or the cash account.
- It remains in a rejected-event audit artifact with the original raw score and reason.
- EOD publication does not need a separate delisting implementation; it consumes the same decision.

Backtests are regenerated from the filtered candidate source. Historical summaries must disclose the number of removed trades and the removed PnL contribution.

### 4.4 Near-limit-down rule

A candidate at or below its resolved near-limit-down threshold is `risk_watch` for research output and is not eligible for Top5 or backtest entry.

The event remains in audit data with its raw score. It does not disappear from research history.

This decision applies before lifecycle entry selection and before account simulation. Publication and Dashboard consume the stored decision instead of recalculating it.

### 4.5 Pump-risk rule

The single contract is:

- `< 0.75`: normal eligibility.
- `>= 0.75 and < 0.90`: still eligible, with warning `high_elasticity_pump_risk`.
- `>= 0.90`: `hard_reject` with reason `extreme_one_day_pump_risk`.
- missing value: `risk_watch` with `pump_risk_missing`; it cannot enter Top5 or a backtest trade until resolved.

The 0.75 threshold is a warning boundary, not a second hidden eligibility boundary. This preserves historically useful high-elasticity samples while removing rule drift.

### 4.6 Drawdown rule

`high_to_close_drawdown` has one canonical definition:

```text
(high - close) / high
```

It is non-negative. Every LHB score path uses the same continuous penalty. The existing `clip(-1, 0).abs()` interpretation is removed.

Drawdown does not become a hard rejection by itself in Phase A. Values at or above 8% receive warning `large_high_to_close_drawdown`. Ranking calibration may change the penalty weight in Phase C, but it may not change the field definition.

### 4.7 Missing-data semantics

Missing information is never silently converted into evidence of safety.

- Missing institution activity remains a neutral score contribution but is marked `institution_activity_unknown`.
- Missing pump risk, price change, point-in-time name, or price-limit regime makes the candidate `risk_watch` and blocks Top5/backtest entry.
- A batch where every candidate lacks price-limit data is published as degraded and emits a high-priority warning.
- Missing data cannot be repaired using future information.

## 5. Point-in-time ST and price-limit state

### 5.1 Name precedence

For historical and same-day LHB decisions, name resolution uses:

1. Same-day `market.lhb_top_list_daily.name`.
2. A point-in-time security-status source, when available.
3. Current `core.asset_master.name` only as a display fallback.
4. Code fallback.

The current master name must not determine historical ST or delisting state.

### 5.2 Price-limit resolver

Create one point-in-time resolver used by the eligibility contract. It returns both the regime and source quality.

Resolution inputs include:

- same-day LHB name
- exchange and board
- same-day ST status
- listing and delisting dates
- same-day close/preclose/pct change
- stored limit-up/limit-down prices when trustworthy

The standard near-limit-down boundaries remain:

- ordinary Shanghai/Shenzhen main board: -9.5%
- ST: -4.8%
- ChiNext/STAR: -19.0%
- Beijing: -29.0%

Listing-day or other no-limit regimes are classified explicitly and are not forced into an ordinary threshold.

### 5.3 Status data repair

The existing all-false ST series is treated as failed data quality, not authoritative `false`.

For LHB candidates, same-day LHB names provide the immediate point-in-time fallback. The status build records the chosen source and a quality state. A global `false` value is accepted only when the upstream status dataset passes a non-zero and continuity sanity check.

The implementation must add a daily quality assertion that flags an all-market ST count of zero when same-day source names contain ST-prefixed securities.

## 6. Pipeline integration

The unified data flow is:

```text
LHB features + same-day security state + daily bar
        -> point-in-time price-limit resolver
        -> shared eligibility contract
        -> candidate audit
        -> eligible ranking pool
        -> intraday confirmation
        -> lifecycle simulation
        -> account simulation
        -> EOD review and Dashboard
```

Every downstream artifact carries the contract version and decision fields. Downstream stages may make a candidate more restrictive, but may not turn `hard_reject` or `risk_watch` into an eligible trade.

Required parity invariant:

```text
candidate decision == backtest decision == account decision == published decision
```

The invariant is checked by `trade_date + ts_code + contract_version`.

## 7. Dashboard confirmation semantics

The Dashboard exposes five states:

- `pending_confirmation`: T-close ranked candidate awaiting T+1 evidence.
- `confirmed_follow`: T+1 evidence has satisfied a follow rule.
- `watch_only`: mixed evidence; no follow permission.
- `risk_watch`: safety or data-quality restriction.
- `retreat`: explicit rejection or withdrawal signal.

Display rules:

- Pending candidates are labeled `Top5 次日确认待定`, not ordinary `Top5 重点复盘`.
- Confirmed candidates are labeled `已确认可跟踪`; this is still not an automated buy instruction.
- Risk-watch candidates retain raw scores but do not occupy confirmed Top5 positions.
- The card displays eligibility reason, confirmation state, point-in-time price regime, and contract version.
- A pending candidate cannot display language implying that post-confirmation historical performance applies to it.

The review artifact therefore carries:

- `confirmation_state`
- `phase12a_rule_layer`
- `phase12a_rule_action`
- `fill_status`
- `eligibility_status`
- `eligibility_reason_codes`
- `contract_version`

## 8. Top5 ranking calibration

### 8.1 Point-in-time dataset

The calibration dataset contains only information observable at T close. T+1 auction, minute bars, confirmation actions, entries, and realized returns are outcome columns and cannot be score features.

The filtered universe is produced by Phase A's eligibility contract. Rejected delisting and near-limit-down records are not reintroduced for optimization.

### 8.2 Objective and constraints

The primary objective is mean future 5-day return for the daily Top5.

Constraints:

- T+1 close-up rate may not be more than 2 percentage points below the baseline on holdout data.
- Mean future 5-day maximum drawdown may not be worse than baseline by more than 0.5 percentage points.
- Top1-5 must not underperform ranks 6-10 on both mean 5-day return and T+1 up rate.
- No single month may contribute more than 40% of the total excess return.
- Sample size and missing-data coverage must be reported for every candidate formula.

### 8.3 Validation protocol

Use chronological walk-forward validation, followed by a final untouched holdout period. Random train/test splitting is prohibited.

The first calibration favors a transparent monotonic score or small grid search over complex machine learning. Candidate weights must have stable signs and a documented economic interpretation.

The output is versioned as `lhb_selection_score_v2` and runs in shadow beside the current score. Production promotion requires all holdout gates to pass. If no candidate passes, the current ranking remains in production and the result is reported as a failed calibration, not relaxed after the fact.

## 9. Error handling and observability

Daily metrics include:

- candidate count before and after the contract
- hard rejects by reason
- risk-watch counts by reason
- unknown-data counts
- delisting rejects
- near-limit-down rejects
- pump warning/reject counts
- status-source coverage
- parity mismatches across pipeline stages
- pending/confirmed/watch/retreat Dashboard counts

Any parity mismatch, a non-zero filled hard-reject count, or an all-candidate price-limit-data failure makes the run degraded or failed. It cannot publish a normal ready state.

## 10. Testing strategy

### 10.1 Contract tests

Table-driven tests cover:

- delisting reason variants
- main-board, ST, STAR, ChiNext, and Beijing boundaries
- no-limit listing regimes
- pump boundaries at 0.75 and 0.90
- positive drawdown calculation and penalties
- missing critical fields
- decision precedence

### 10.2 Pipeline tests

- A hard-rejected candidate never appears in ranked candidates, lifecycle fills, or account fills.
- A risk-watch near-limit-down event remains auditable but cannot become a trade.
- Candidate, backtest, account, review, score audit, and Dashboard decisions match.
- Historical renamed/ST/delisting examples use same-day names rather than current master names.
- Existing non-LHB strategies remain unchanged.

### 10.3 Dashboard tests

- Pending, confirmed, watch, risk, and retreat labels are distinct.
- Pending rows do not inherit confirmed-follow language.
- Reason codes and contract version survive CSV and read-model serialization.

### 10.4 Calibration tests

- Future columns are rejected as input features.
- Walk-forward splits are chronological and non-overlapping.
- Baseline and candidate formulas use the identical eligible universe.
- Acceptance gates are computed from the untouched holdout only.
- A failed gate prevents production promotion.

## 11. Rollout and historical replay

### Phase A checkpoint

Re-run the 2026-01-05 through 2026-07-14 strategy history.

Required evidence:

- zero delisting-period account fills
- zero near-limit-down account fills
- corrected drawdown scores
- zero eligibility parity mismatches
- explicit performance delta versus the contaminated baseline

### Phase B checkpoint

Re-publish 2026-07-14 and a historical confirmed date. Verify that the first displays pending confirmation and the second displays confirmed/watch/retreat states from its actual rule layer.

### Phase C checkpoint

Generate the shadow comparison and holdout report. Promote only if every acceptance gate passes.

## 12. Rollback

The shared contract is versioned. A runtime rollback can select the previous contract version for diagnosis, but rejected delisting trades cannot be restored to production or used to claim official performance.

Dashboard wording can roll back independently without changing decisions. Ranking v2 can remain shadow-only indefinitely if calibration gates fail.

## 13. Completion criteria

The seven-item program is complete only when all of the following are proven:

1. Delisting-period records are rejected before ranking and cannot enter lifecycle or account fills.
2. Near-limit-down decisions are identical in backtest, account, EOD publication, score audit, and Dashboard.
3. Every LHB scorer uses the positive drawdown definition and tests prove the old sign error is gone.
4. All candidate paths use `lhb_eligibility_v2`; no independent 0.75/0.90 hard threshold remains.
5. ST and price-limit decisions are point-in-time, source-audited, and protected by daily quality checks.
6. Dashboard pending and confirmed states are visibly distinct and traceable to rule-layer data.
7. Ranking v2 has a chronological shadow/holdout report and is promoted only if all gates pass; otherwise its non-promotion is the correct completed outcome.
8. The historical replay reports the honest performance change after invalid trades are removed.
9. Relevant tests pass, parity mismatches are zero, and the final worktree contains no unintended user-file changes.
