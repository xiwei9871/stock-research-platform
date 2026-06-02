# Technical Feature Promotion Plan

**Goal:** Define a unified promotion framework for technical fields so the project can decide, with evidence, which fields belong in `factor.stock_technical_features_daily`, which fields should be elevated into `factor.factor_daily`, which fields should remain derived-only, and which should be dropped.

**Architecture:** Keep a two-layer model. `factor.stock_technical_features_daily` stores reusable atomic daily technical state. `factor.factor_daily` stores a smaller set of stable, non-redundant, cross-workflow factor rows suitable for daily factor scoring and downstream joins. Derived event/risk combos stay out of both storage layers unless they later prove stable across environments.

**Scope Boundary:** This plan does not add trading rules, does not change Dragon/LHB scoring, and does not treat technical validation results as production strategy signals. It only governs storage promotion and downstream reuse.

---

## 1. Current State

### Existing atomic technical store
- Source: [technical_features.py](/Users/xiwei/stock_research/src/stock_research/technical_features.py)
- Store/upsert path: [technical_feature_store.py](/Users/xiwei/stock_research/src/stock_research/technical_feature_store.py)
- Current stored fields include:
  - `ma5`, `ma10`, `ma20`, `ma60`, `ma120`
  - `ema12`, `ema26`
  - `macd_dif`, `macd_dea`, `macd_hist`
  - `rsi6`, `rsi12`, `rsi24`
  - `boll_upper_20`, `boll_mid_20`, `boll_lower_20`
  - `atr14`, `cci14`
  - `kdj_k`, `kdj_d`, `kdj_j`
  - `adx14`, `obv`
  - `ret_1d`, `ret_20d`, `close_position_in_day`

### Existing factor layer
- Source: [factor_pipeline.py](/Users/xiwei/stock_research/src/stock_research/factor_pipeline.py)
- Configuration: [factor_config.py](/Users/xiwei/stock_research/src/stock_research/factor_config.py)
- Current technical factor rows already cover:
  - `amount_ratio_5_20`
  - `volatility_20`
  - `max_drawdown_20`
  - `atr_pct`
  - `distance_ma20`, `distance_ma60`
  - `upper_shadow_ratio`
  - several trend / momentum / volume ratios

### Validation evidence used by this plan
- [technical_method_validation_report.md](/Users/xiwei/stock_research/outputs/research/technical_method_validation_report.md)
- [technical_method_recommendation.csv](/Users/xiwei/stock_research/outputs/research/technical_method_recommendation.csv)
- [technical_method_redundancy_report.csv](/Users/xiwei/stock_research/outputs/research/technical_method_redundancy_report.csv)
- [technical_method_case_event_effectiveness.csv](/Users/xiwei/stock_research/outputs/research/technical_method_case_event_effectiveness.csv)
- [technical_method_lhb_cross_effectiveness.csv](/Users/xiwei/stock_research/outputs/research/technical_method_lhb_cross_effectiveness.csv)

---

## 2. Promotion Framework

Promotion decisions should not be made on single-metric intuition. A field should be evaluated on five dimensions:

1. **Reuse breadth**
   - Is the field already reused or clearly needed in at least two of:
     - technical validation
     - Dragon diagnostics
     - LHB diagnostics
     - failure-event rules
     - watchlist / risk filtering

2. **Evidence strength**
   - Did the field show value in at least two of:
     - bucket effectiveness
     - combo effectiveness
     - regime effectiveness
     - case-event effectiveness
     - LHB cross effectiveness

3. **Redundancy cost**
   - If the field is in a high-correlation redundancy group, prefer one representative field.
   - Do not promote multiple near-duplicates unless they serve clearly different downstream uses.

4. **Operational cost**
   - Must be computable from same-day and historical bars only.
   - Must be cheap enough for daily build/backfill.
   - Must not require future returns, case labeling, or event replay.

5. **Layer fit**
   - **Atomic technical store**: raw, reusable daily state fields.
   - **Factor layer**: compact, stable, non-redundant factor rows suitable for ranking/scoring/joins.
   - **Derived-only**: thresholds, event combinations, and diagnosis rules that should be recomputed downstream.

### Decision rules

- Promote to `stock_technical_features_daily` when:
  - reusable,
  - cheap,
  - non-leaky,
  - and repeatedly needed by research or diagnostics.

- Promote to `factor_daily` only when:
  - the field has stable evidence,
  - redundancy is acceptable,
  - and the field is suitable as a general-purpose daily factor row.

- Keep as derived-only when:
  - it is a thresholded combination,
  - depends on context,
  - or is more interpretable as a rule than as a stored factor.

- Discard or deprioritize when:
  - evidence is weak,
  - effect is inconsistent,
  - or the field is dominated by a stronger representative.

---

## 3. Promotion Decisions

### Phase 1: Promote into `factor.stock_technical_features_daily`

These are the highest-value atomic additions:

1. `amount_vs_20d`
   - Rationale: repeatedly used in Dragon, LHB, failure diagnostics, and technical validation.
   - Role: reusable daily liquidity/attention scale.

2. `high_to_close_drawdown`
   - Rationale: strong event-diagnostic value for high-open-low-close failure, A-kill, and intraday fade risk.
   - Role: reusable daily intraday exhaustion field.

3. `volatility_5d`
   - Rationale: more relevant than long-window volatility for short-event diagnostics.
   - Role: short-horizon risk state.

4. `max_drawdown_20d`
   - Rationale: already strong as a risk concept and already present in factor form; add to atomic store for direct joins and event diagnostics.

5. `atr_pct14`
   - Rationale: useful risk scale with low compute cost and broad reuse potential.

### Phase 1.5: Promote into atomic store only if downstream use remains active

6. `boll_position_20`
7. `plus_di14`
8. `minus_di14`

These have some research value, but they are less urgent than the first five and should not block the first batch.

### Phase 2: Promote into `factor.factor_daily`

Add only a small batch of new long-form factor rows:

1. `amount_vs_20d`
   - Reason: strong reuse, low ambiguity, good daily-state factor candidate.

2. `volatility_5d`
   - Reason: short-horizon risk factor missing from current factor layer.

3. `high_to_close_drawdown`
   - Reason: event-risk factor with clear daily interpretation and low redundancy with the current long-form set.

### Phase 2 holdout candidate

4. `close_position_in_day`
   - Keep as a holdout candidate.
   - Reason: useful in case/LHB diagnostics, but single-feature evidence is weaker than the top three.

### Keep out of `factor_daily`

Do not promote these into factor rows yet:

- `rsi6`, `rsi12`, `rsi24`
- `boll_position_20`
- `plus_di14`, `minus_di14`
- `macd_dea`
- `obv`
- `ma*` / `close_vs_ma*`
- `kdj*`

Reason:
- either redundant,
- or better kept as atomic features,
- or statistically weak for current use,
- or more appropriate for diagnostic interpretation than daily factor storage.

### Derived-only, never direct storage promotion for now

Keep these as downstream formulas/rules, not stored daily factors:

- `rsi6_above_90`
- `rsi12_above_80`
- `amount_vs_20d_above_5`
- `extreme_amount_weak_close`
- `high_fade_with_high_amount`
- `rsi6_extreme_with_extreme_amount`
- `second_wave_supportive_setup`

These are thresholded composites. They belong in watchlist/risk filtering logic or event diagnostics, not in reusable storage tables.

---

## 4. Why This Split Is Correct

### Why not promote everything that looks useful?

Because `factor_daily` is a compact factor layer, not a generic feature dump. Overloading it with raw technical state, duplicated variants, and thresholded combos makes downstream scoring noisier and raises backfill and maintenance cost without improving clarity.

### Why not rely only on `factor_daily`?

Because LHB diagnostics, failure-event rules, and case/event alignment need atomic technical state. Those workflows benefit from a wider technical base than the factor layer should carry.

### Why not keep everything out of storage and compute on the fly?

Because the same fields already recur across multiple research loops. Persisting the reusable atomic subset reduces repeated recomputation and keeps later diagnostics consistent.

---

## 5. Execution Plan

### Stage A: Atomic technical store promotion

**Files likely to change**
- [technical_features.py](/Users/xiwei/stock_research/src/stock_research/technical_features.py)
- [technical_feature_store.py](/Users/xiwei/stock_research/src/stock_research/technical_feature_store.py)
- schema SQL or schema generator backing `factor.stock_technical_features_daily`
- related tests:
  - `tests/test_technical_features.py`
  - `tests/test_technical_feature_store.py`
  - `tests/test_schema.py`

**Deliverables**
- add new columns to `TECHNICAL_FEATURE_COLUMNS`
- compute and upsert the promoted atomic fields
- update schema and tests
- backfill via existing technical-feature backfill workflow

### Stage B: Factor layer promotion

**Files likely to change**
- [factor_pipeline.py](/Users/xiwei/stock_research/src/stock_research/factor_pipeline.py)
- [factor_config.py](/Users/xiwei/stock_research/src/stock_research/factor_config.py)
- tests around factor generation and storage:
  - `tests/test_factor_pipeline.py`
  - `tests/test_factor_cli.py`
  - `tests/test_factor_eval.py`

**Deliverables**
- add `amount_vs_20d`, `volatility_5d`, `high_to_close_drawdown` as factor candidates
- define factor groups and directions explicitly
- keep the initial score weights unchanged unless separately justified
- validate factor availability and storage coverage

### Stage C: Post-promotion verification

Re-run:
- technical feature build/backfill smoke
- factor daily build smoke
- diagnostic joins that rely on the new atomic fields
- full `pytest`

---

## 6. Acceptance Gates

Promotion is successful only if all of these are true:

1. New fields are built from historical bars only.
2. Schema, build, and upsert are replay-safe.
3. Backfill completes without special-case scripts.
4. Dragon/LHB/case-diagnostic readers can use the promoted fields without recomputing them ad hoc.
5. No threshold combo is forced into persistent storage.
6. `factor_daily` remains compact and readable.

---

## 7. Final Recommendation

Use a strict layered policy:

- **Atomic store first** for reusable technical state
- **Factor layer second** for a small, stable subset
- **Derived combos downstream** only

If we do that, the next promotion batch should be:

- `stock_technical_features_daily`
  - `amount_vs_20d`
  - `high_to_close_drawdown`
  - `volatility_5d`
  - `max_drawdown_20d`
  - `atr_pct14`

- `factor_daily`
  - `amount_vs_20d`
  - `volatility_5d`
  - `high_to_close_drawdown`

Everything else should wait until it proves incremental value beyond the current redundancy groups and risk-diagnostic use cases.
