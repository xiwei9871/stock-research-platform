# Intraday Risk Control V2 Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a research-only V2 intraday risk-control test and run it against the existing 2025-01-02 to 2026-06-05 mid-trend TopN baseline.

**Architecture:** Add a separate V2 module that reuses existing intraday feature, score, price, and vectorized TopN backtest infrastructure. V2 will normalize intraday features by each stock's rolling history, create structural risk triggers, build rolling mid-trend risk states, and compare baseline against new-entry penalty and confirmed-risk variants.

**Tech Stack:** Python, pandas, pytest, existing `stock_research.vectorized_topn_backtest`, existing `factor.stock_intraday_features_daily`, existing `factor.stock_score_daily`.

---

### Task 1: V2 Signal Construction

**Files:**
- Create: `src/stock_research/intraday_risk_control_v2.py`
- Test: `tests/test_intraday_risk_control_v2.py`

- [ ] **Step 1: Write failing tests**

Add tests proving:

```python
def test_build_intraday_risk_signals_v2_uses_stock_history_not_daily_rank_only():
    features = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "feature_name": "amount_front_1h_ratio", "feature_value": 0.20},
            {"trade_date": "2026-01-02", "asset_id": "A", "feature_name": "amount_front_1h_ratio", "feature_value": 0.21},
            {"trade_date": "2026-01-03", "asset_id": "A", "feature_name": "amount_front_1h_ratio", "feature_value": 0.80},
            {"trade_date": "2026-01-01", "asset_id": "A", "feature_name": "afternoon_return", "feature_value": 0.01},
            {"trade_date": "2026-01-02", "asset_id": "A", "feature_name": "afternoon_return", "feature_value": 0.00},
            {"trade_date": "2026-01-03", "asset_id": "A", "feature_name": "afternoon_return", "feature_value": -0.04},
        ]
    )
    signals = build_intraday_risk_signals_v2(features, lookback=2, zscore_threshold=1.0)
    row = signals[signals["trade_date"].eq("2026-01-03") & signals["asset_id"].eq("A")].iloc[0]
    assert bool(row["front_loaded_failure"])
```

```python
def test_build_midtrend_risk_states_requires_repeated_triggers():
    signals = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "structural_risk_count": 1},
            {"trade_date": "2026-01-02", "asset_id": "A", "structural_risk_count": 0},
            {"trade_date": "2026-01-03", "asset_id": "A", "structural_risk_count": 1},
            {"trade_date": "2026-01-04", "asset_id": "A", "structural_risk_count": 1},
        ]
    )
    states = build_midtrend_risk_states(signals, watch_5d_count=2, high_5d_count=3)
    assert states.iloc[0]["midtrend_risk_level"] == "none"
    assert states.iloc[2]["midtrend_risk_level"] == "watch"
    assert states.iloc[3]["midtrend_risk_level"] == "high"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
./.venv/bin/pytest -q tests/test_intraday_risk_control_v2.py
```

Expected: FAIL because the module and functions do not exist.

- [ ] **Step 3: Implement minimal V2 signal functions**

Create functions:

- `build_intraday_risk_signals_v2(features, lookback=20, zscore_threshold=1.5)`
- `build_midtrend_risk_states(signals, watch_5d_count=2, high_5d_count=3, watch_10d_count=3, high_10d_count=5)`

Implementation details:

- Pivot features to one row per `trade_date, asset_id`.
- Compute rolling mean/std per asset using prior rows only with `shift(1)`.
- Create z-score fields for `amount_front_1h_ratio`, `intraday_volatility_5min`, `last_30m_return`, `close_to_vwap`.
- Create structure flags:
  - `front_loaded_failure`
  - `morning_to_afternoon_reversal`
  - `tail_confirmation_failure`
  - `high_volatility_no_follow_through`
- Set `lhb_risk_level` from same-day structural count.
- Set `midtrend_risk_level` from rolling trigger counts.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
./.venv/bin/pytest -q tests/test_intraday_risk_control_v2.py
```

Expected: PASS.

### Task 2: Mid-Trend V2 Variants And Backtest

**Files:**
- Modify: `src/stock_research/intraday_risk_control_v2.py`
- Test: `tests/test_intraday_risk_control_v2.py`

- [ ] **Step 1: Write failing tests**

Add tests proving:

```python
def test_build_midtrend_score_variants_penalizes_new_entries_but_not_baseline():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "asset_id": "A", "rank": 1, "score_total": 100.0},
            {"trade_date": "2026-01-05", "asset_id": "B", "rank": 2, "score_total": 95.0},
        ]
    )
    states = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "asset_id": "A", "midtrend_risk_level": "high", "midtrend_risk_trigger_count_5d": 3},
            {"trade_date": "2026-01-05", "asset_id": "B", "midtrend_risk_level": "none", "midtrend_risk_trigger_count_5d": 0},
        ]
    )
    variants = build_midtrend_score_variants_v2(scores, states, watch_penalty=3.0, high_penalty=8.0)
    assert variants["baseline_topn"].loc[0, "asset_id"] == "A"
    assert variants["trend_new_entry_penalty"].iloc[0]["asset_id"] == "B"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
./.venv/bin/pytest -q tests/test_intraday_risk_control_v2.py
```

Expected: FAIL because variant functions do not exist.

- [ ] **Step 3: Implement score variants and report writing**

Add:

- `build_midtrend_score_variants_v2`
- `run_intraday_risk_control_v2_from_frames`
- `summarize_intraday_risk_control_v2`
- `write_intraday_risk_control_v2_report`
- `format_intraday_risk_control_v2_report`

Variants:

- `baseline_topn`
- `trend_new_entry_penalty`
- `trend_confirmed_reduce`

For the first test run, `trend_confirmed_reduce` uses mid-trend `high` as the research confirmation proxy and applies a stronger penalty instead of direct sell.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
./.venv/bin/pytest -q tests/test_intraday_risk_control_v2.py
```

Expected: PASS.

### Task 3: CLI And Real Backtest

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Add parser and dispatch tests for command:

```bash
intraday-risk-control-v2-backtest
```

Required args:

- `--start-date`
- `--end-date`
- `--output-dir`

Optional args:

- `--score-version`
- `--top-n-values`
- `--rebalance-frequency`
- `--transaction-cost-bps`
- `--lookback`
- `--zscore-threshold`

- [ ] **Step 2: Run CLI tests and verify RED**

Run:

```bash
./.venv/bin/pytest -q tests/test_factor_cli.py::test_cli_accepts_intraday_risk_control_v2_backtest_command tests/test_factor_cli.py::test_intraday_risk_control_v2_backtest_cli_dispatches
```

Expected: FAIL because CLI command does not exist.

- [ ] **Step 3: Implement CLI loader and dispatch**

Add:

- `load_intraday_risk_control_v2_inputs`
- `run_intraday_risk_control_v2_backtest`
- CLI import, parser, and dispatch.

- [ ] **Step 4: Run focused tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_intraday_risk_control_v2.py tests/test_factor_cli.py::test_cli_accepts_intraday_risk_control_v2_backtest_command tests/test_factor_cli.py::test_intraday_risk_control_v2_backtest_cli_dispatches
```

Expected: PASS.

- [ ] **Step 5: Run real 2025-to-date research backtest**

Run:

```bash
./.venv/bin/python -m stock_research.cli intraday-risk-control-v2-backtest \
  --start-date 2025-01-02 \
  --end-date 2026-06-05 \
  --score-version manual_v1 \
  --top-n-values 10,20 \
  --rebalance-frequency daily \
  --transaction-cost-bps 20 \
  --lookback 20 \
  --zscore-threshold 1.5 \
  --output-dir outputs/research/intraday_risk_control_v2/2026-06-07_full
```

Expected: report and summary CSV written under the output directory.

## Self-Review

- Spec coverage: covers historical normalization, structural triggers, LHB same-day risk state, mid-trend rolling risk state, backtest variants, and research-only outputs.
- Intentional scope cut: first implementation runs mid-trend TopN effect testing because baseline scores and vectorized backtest already exist. LHB-specific candidate source integration remains separate so LHB and mid-trend are not mixed.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: all public function names in tests match implementation tasks.
