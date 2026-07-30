# Consumer Oversold Elasticity Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a point-in-time, single-list consumer oversold Top20 that keeps the existing fundamental gates and combines repair-potential rank at 70% with rebound-elasticity rank at 30%, then regenerate the list from complete 2026-07-29 data.

**Architecture:** Keep the existing fundamental, valuation, hard-risk, and evidence pipeline intact. Add a focused `elasticity.py` module for two-year price compression, historical stock-character, current market-capacity, and catalyst/liquidity features; merge its percentile score only after the existing eligibility gates. Publish one unified Top20 plus reserve, pre-audit, comparison, exclusion, evidence, coverage, and report artifacts while retaining backward-compatible reading of historical two-bucket releases.

**Tech Stack:** Python 3.14, pandas, NumPy, PostgreSQL/psycopg, pytest, immutable filesystem releases with SHA-256 manifests.

---

## File structure

- Create `src/stock_research/consumer_oversold/elasticity.py`: pure feature and percentile calculations for residual price deviation, stock character, market-capacity, and catalyst/liquidity fit.
- Modify `src/stock_research/consumer_oversold/contracts.py`: ranking weights, coverage thresholds, and new output filenames.
- Modify `src/stock_research/consumer_oversold/loaders.py`: two-year PIT bars, amount/turnover/status fields, and PIT total/float/free-float shares.
- Modify `src/stock_research/consumer_oversold/scoring.py`: preserve hard gates, add single-list percentile aggregation and stable rank tie-breaking.
- Modify `src/stock_research/consumer_oversold/pipeline.py`: quantitative pre-audit Top60, evidence-complete pool enforcement, unified Top20/reserve, and old/new comparison.
- Modify `src/stock_research/consumer_oversold/reporting.py`: publish and render the expanded immutable artifact set.
- Modify `src/stock_research/consumer_oversold/evaluation.py`: read both legacy bucket releases and new unified releases; support 5-day and 20-day evaluation.
- Modify `src/stock_research/cli.py`: allow explicit historical cutoff or automatic latest-complete daily cutoff.
- Create `tests/test_consumer_oversold_elasticity.py`: isolated feature tests.
- Modify the existing consumer-oversold tests named below for contracts, loaders, scoring, pipeline, reporting, CLI, and evaluation.
- Create operational evidence and release files under `outputs/research/consumer_oversold_daily/2026-07-29/`; do not commit generated releases.

### Task 1: Extend contracts for the unified ranking

**Files:**
- Modify: `src/stock_research/consumer_oversold/contracts.py`
- Modify: `src/stock_research/consumer_oversold/__init__.py`
- Test: `tests/test_consumer_oversold_contracts.py`

- [ ] **Step 1: Write failing contract tests**

Add assertions for the approved weights, coverage sizes, and stable filenames:

```python
def test_elasticity_ranking_defaults_match_approved_design():
    config = ConsumerOversoldConfig(trade_date="2026-07-29")

    assert config.repair_rank_weight == pytest.approx(0.70)
    assert config.elasticity_rank_weight == pytest.approx(0.30)
    assert config.residual_deviation_weight == pytest.approx(0.35)
    assert config.stock_character_weight == pytest.approx(0.25)
    assert config.market_capacity_weight == pytest.approx(0.20)
    assert config.catalyst_liquidity_weight == pytest.approx(0.20)
    assert config.preaudit_size == 60
    assert config.minimum_evidence_complete == 40
    assert config.final_top_n == 20
    assert config.reserve_top_n == 20


def test_unified_output_filenames_are_stable():
    assert OUTPUT_FILENAMES["top20"] == "consumer_oversold_unified_top20.csv"
    assert OUTPUT_FILENAMES["reserve"] == "consumer_oversold_reserve_21_40.csv"
    assert OUTPUT_FILENAMES["preaudit"] == "consumer_oversold_preaudit_top60.csv"
    assert OUTPUT_FILENAMES["comparison"] == "consumer_oversold_old_new_rank_comparison.csv"
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_consumer_oversold_contracts.py -q
```

Expected: failures for missing config fields and output keys.

- [ ] **Step 3: Add frozen configuration fields and output names**

Extend `ConsumerOversoldConfig` with finite numeric validation and exact weight-sum checks:

```python
repair_rank_weight: float = 0.70
elasticity_rank_weight: float = 0.30
residual_deviation_weight: float = 0.35
stock_character_weight: float = 0.25
market_capacity_weight: float = 0.20
catalyst_liquidity_weight: float = 0.20
preaudit_size: int = 60
minimum_evidence_complete: int = 40
final_top_n: int = 20
reserve_top_n: int = 20
```

Add output keys `top20`, `reserve`, `preaudit`, and `comparison`. Keep legacy `expected` and `early` names available only through a separate `LEGACY_OUTPUT_FILENAMES` mapping used by the evaluator; new releases must not publish separate Top10 lists.

- [ ] **Step 4: Run contract tests and verify GREEN**

Run the command from Step 2.

Expected: all contract tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/consumer_oversold/contracts.py \
  src/stock_research/consumer_oversold/__init__.py \
  tests/test_consumer_oversold_contracts.py
rtk git commit -m "feat: define unified consumer elasticity ranking contracts"
```

### Task 2: Load two-year PIT market and share-capacity inputs

**Files:**
- Modify: `src/stock_research/consumer_oversold/loaders.py:18-22,242-280,390-420`
- Test: `tests/test_consumer_oversold_loaders.py`

- [ ] **Step 1: Write failing loader tests**

Require 520 latest market dates and stable market columns:

```python
def test_market_requests_two_years_and_returns_elasticity_inputs(monkeypatch):
    calls = _install_db(monkeypatch, [[{
        "asset_id": "A",
        "trade_date": date(2026, 7, 29),
        "close": Decimal("10"),
        "raw_close": Decimal("5"),
        "amount": Decimal("100000000"),
        "turnover_rate": Decimal("2.5"),
        "pct_chg": Decimal("7.2"),
        "is_st": False,
        "trade_status": "交易",
    }]])

    result = load_consumer_market_history("2026-07-29", service="svc")

    assert calls[0][1][1] == 520
    assert tuple(result.columns) == MARKET_COLUMNS
    assert result.iloc[0]["amount"] == Decimal("100000000")
```

Add a PIT share-capital test:

```python
def test_share_capacity_uses_latest_visible_event_and_preserves_float_fallback(monkeypatch):
    _install_db(monkeypatch, [[
        {"asset_id": "A", "total_share": 100.0, "float_share": 80.0, "free_float_share": 60.0},
    ]])

    result = load_consumer_share_capacity(["A"], "2026-07-29", service="svc")

    assert result.to_dict("records") == [{
        "asset_id": "A",
        "total_share": 100.0,
        "float_share": 80.0,
        "free_float_share": 60.0,
    }]
```

- [ ] **Step 2: Run loader tests and verify RED**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_consumer_oversold_loaders.py -q
```

Expected: the market window remains 260, required columns are absent, and `load_consumer_share_capacity` does not exist.

- [ ] **Step 3: Extend the PIT SQL and schemas**

Set:

```python
MARKET_COLUMNS = (
    "asset_id", "trade_date", "close", "raw_close", "amount",
    "turnover_rate", "pct_chg", "is_st", "trade_status",
)
SHARE_CAPACITY_COLUMNS = (
    "asset_id", "total_share", "float_share", "free_float_share",
)
```

Change the market-date limit to 520. Select the extra fields from the hfq bar while retaining `raw.close` for actual market-cap calculations. Add `load_consumer_share_capacity()` using `finance.share_capital_event` with both `event_date <= cutoff` and `announcement_date IS NULL OR announcement_date <= cutoff`, stable source tie-breaking, and asset-scoped validation.

The market loader remains keyed by `asset_id`. Before calling stock-character functions, the pipeline must merge `assets[["asset_id", "stock_code"]]` into the market frame with a validated many-to-one merge; the feature function must not infer board rules from `asset_id` text.

- [ ] **Step 4: Run loader tests and verify GREEN**

Run the command from Step 2.

Expected: all loader tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/consumer_oversold/loaders.py \
  tests/test_consumer_oversold_loaders.py
rtk git commit -m "feat: load PIT consumer elasticity inputs"
```

### Task 3: Implement residual price-deviation features

**Files:**
- Create: `src/stock_research/consumer_oversold/elasticity.py`
- Create: `tests/test_consumer_oversold_elasticity.py`

- [ ] **Step 1: Write failing residual-deviation tests**

Use deterministic synthetic price paths:

```python
def test_residual_deviation_keeps_post_limit_stock_high_when_still_depressed():
    bars = price_path(
        asset_id="A",
        hfq_closes=[100.0] * 20 + list(np.linspace(100.0, 40.0, 499)) + [44.0],
    )

    result = compute_residual_price_features(bars, trade_date="2026-07-29").iloc[0]

    assert result["return_1d"] == pytest.approx(0.10)
    assert result["drawdown_from_high_1y"] < -0.50
    assert result["drawdown_from_high_2y"] < -0.50
    assert result["price_position_2y"] < 0.20
    assert result["residual_deviation_coverage"]


def test_residual_deviation_marks_large_cumulative_rebound_as_consumed():
    bars = price_path(asset_id="A", hfq_closes=[100.0] * 400 + [40.0] + list(np.linspace(40.0, 70.0, 119)))

    result = compute_residual_price_features(bars, trade_date="2026-07-29").iloc[0]

    assert result["rebound_from_low_120d"] > 0.70
    assert result["price_position_1y"] > 0.45
```

Add tests for future-bar rejection, duplicate dates, fewer than 504 valid HFQ bars, invalid HFQ prices, raw-price independence, and exact 252/504-session windows.

- [ ] **Step 2: Run the new tests and verify RED**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_consumer_oversold_elasticity.py -q
```

Expected: import failure for the new module.

- [ ] **Step 3: Implement the pure residual feature function**

Create:

```python
def compute_residual_price_features(
    bars: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    """Return one PIT residual-price row per asset from HFQ closes."""
```

Return at least:

```python
(
    "asset_id", "price_series_source", "return_1d", "drawdown_from_high_1y",
    "drawdown_from_high_2y", "price_position_1y", "price_position_2y",
    "distance_hfq_ma120", "distance_hfq_ma250", "rebound_from_low_60d",
    "rebound_from_low_120d", "residual_deviation_coverage",
)
```

Use HFQ closes for every dimensionless historical technical deviation, including returns, high/low positions, moving-average distances, and rebounds. Require 504 valid HFQ sessions for residual-deviation coverage. `raw_close` is neither required nor part of this coverage decision. All windows are trading-session windows ending at the cutoff.

- [ ] **Step 4: Run the new tests and verify GREEN**

Run the command from Step 2.

Expected: all residual-deviation tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/consumer_oversold/elasticity.py \
  tests/test_consumer_oversold_elasticity.py
rtk git commit -m "feat: compute residual consumer price deviation"
```

### Task 4: Implement two-year stock-character features

**Files:**
- Modify: `src/stock_research/consumer_oversold/elasticity.py`
- Modify: `tests/test_consumer_oversold_elasticity.py`

- [ ] **Step 1: Write failing board-aware character tests**

```python
@pytest.mark.parametrize(
    ("stock_code", "is_st", "pct_chg", "expected"),
    [
        ("600418", False, 9.95, True),
        ("300750", False, 19.95, True),
        ("688001", False, 19.95, True),
        ("600418", True, 4.95, True),
        ("600418", False, 9.40, False),
    ],
)
def test_historical_limit_up_detection_uses_board_and_st_rules(stock_code, is_st, pct_chg, expected):
    assert is_limit_up_day(stock_code, is_st, pct_chg, trade_date="2026-01-05") is expected


def test_stock_character_counts_tail_days_and_forward_continuation_without_future_leakage():
    bars = character_bars(asset_id="A", stock_code="600418")

    result = compute_stock_character_features(bars, trade_date="2026-07-29").iloc[0]

    assert result["limit_up_count_2y"] == 3
    assert result["up_7pct_count_2y"] == 5
    assert result["up_5pct_count_2y"] == 8
    assert result["positive_after_big_up_1d_rate"] == pytest.approx(0.60)
    assert result["stock_character_coverage"]
```

The continuation denominator must exclude a big-up event whose forward horizon extends beyond the cutoff.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_consumer_oversold_elasticity.py -k 'limit_up or stock_character' -q
```

Expected: missing functions.

- [ ] **Step 3: Implement stock-character functions**

首版只支持 2025—2026 年分析日，涨停识别统一使用当前制度，不实现制度日期分支。

Add:

```python
def is_limit_up_day(
    stock_code: str,
    is_st: bool,
    pct_chg: float,
    *,
    trade_date: str,
) -> bool:
    validate_trade_date(trade_date)
    code = stock_code.strip()
    if is_st:
        threshold = 4.8
    elif code.startswith(("4", "8", "920")):
        threshold = 29.8
    elif code.startswith(("300", "301", "688", "689")):
        threshold = 19.8
    else:
        threshold = 9.8
    return math.isfinite(float(pct_chg)) and float(pct_chg) >= threshold


def compute_stock_character_features(
    bars: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    cutoff = pd.Timestamp(trade_date).normalize()
    frame = bars.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise").dt.normalize()
    frame = frame.loc[frame["trade_date"].le(cutoff)].sort_values(
        ["asset_id", "trade_date"], kind="stable"
    )
    rows = []
    for asset_id, history in frame.groupby("asset_id", sort=True):
        window = history.tail(504).copy()
        returns = pd.to_numeric(window["pct_chg"], errors="coerce") / 100.0
        valid = returns.notna()
        limit_flags = [
            is_limit_up_day(row.stock_code, bool(row.is_st), float(row.pct_chg), trade_date=str(row.trade_date.date()))
            for row in window.loc[valid].itertuples(index=False)
        ]
        big_up = returns.ge(0.07)
        continuation = {}
        for horizon in (1, 3, 5):
            future = window["close"].shift(-horizon) / window["close"] - 1.0
            eligible = big_up & future.notna()
            continuation[horizon] = float(future.loc[eligible].gt(0.0).mean()) if eligible.any() else math.nan
        rows.append({
            "asset_id": asset_id,
            "limit_up_count_2y": int(sum(limit_flags)),
            "up_7pct_count_2y": int(big_up.sum()),
            "up_5pct_count_2y": int(returns.ge(0.05).sum()),
            "mean_abs_return_2y": float(returns.abs().mean()),
            "return_volatility_2y": float(returns.std(ddof=1)),
            "upside_tail_volatility_2y": float(returns.loc[returns.gt(0.0)].std(ddof=1)),
            "positive_after_big_up_1d_rate": continuation[1],
            "positive_after_big_up_3d_rate": continuation[3],
            "positive_after_big_up_5d_rate": continuation[5],
            "stock_character_coverage": int(valid.sum()) >= 400,
        })
    return pd.DataFrame(rows).sort_values("asset_id", kind="stable").reset_index(drop=True)
```

Return counts for limit-up, >=7%, >=5%, daily absolute-return mean, daily-return standard deviation, upside-tail standard deviation, maximum limit-up streak, and positive continuation rates after >=7% days for 1/3/5 sessions. Require at least 400 valid sessions within the latest 504-session window; mark coverage false otherwise.

- [ ] **Step 4: Run focused and full elasticity tests**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_consumer_oversold_elasticity.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/consumer_oversold/elasticity.py \
  tests/test_consumer_oversold_elasticity.py
rtk git commit -m "feat: measure two-year consumer stock character"
```

### Task 5: Implement actual market-capacity and liquidity features

**Files:**
- Modify: `src/stock_research/consumer_oversold/elasticity.py`
- Modify: `tests/test_consumer_oversold_elasticity.py`

- [ ] **Step 1: Write failing market-capacity tests**

```python
def test_market_capacity_prefers_free_float_then_float_then_total_share():
    bars = latest_raw_market_rows(raw_close=10.0, average_amount_20d=200_000_000.0)
    shares = pd.DataFrame([
        {"asset_id": "A", "total_share": 100.0, "float_share": 80.0, "free_float_share": 60.0},
        {"asset_id": "B", "total_share": 100.0, "float_share": 80.0, "free_float_share": np.nan},
        {"asset_id": "C", "total_share": 100.0, "float_share": np.nan, "free_float_share": np.nan},
    ])

    result = compute_market_capacity_features(bars, shares, trade_date="2026-07-29").set_index("asset_id")

    assert result.loc["A", "current_float_market_cap"] == pytest.approx(600.0)
    assert result.loc["A", "market_cap_source"] == "free_float_share"
    assert result.loc["B", "market_cap_source"] == "float_share"
    assert result.loc["C", "market_cap_source"] == "total_share_fallback"


def test_scenario_market_cap_is_never_used_as_current_market_cap():
    result = compute_market_capacity_features(
        latest_raw_market_rows(raw_close=5.0),
        pd.DataFrame([{"asset_id": "A", "total_share": 100.0, "float_share": 80.0, "free_float_share": 60.0}]),
        trade_date="2026-07-29",
    ).iloc[0]

    assert result["current_total_market_cap"] == pytest.approx(500.0)
```

- [ ] **Step 2: Run focused tests and verify RED**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_consumer_oversold_elasticity.py -k market_capacity -q
```

Expected: missing function.

- [ ] **Step 3: Implement capacity and liquidity calculation**

Add `compute_market_capacity_features()` returning current total/float market cap, `log_current_float_market_cap`, source, 20-day average amount, amount-to-float-cap ratio, average turnover rate, and coverage. Validate positive raw close and positive shares. Normalize Tushare-derived amounts before passing them into this function; do not normalize inside the pure feature layer.

`raw_close` remains required here because actual market capitalization must use the unadjusted current price; it is not reused for Task 3 historical technical deviations.

- [ ] **Step 4: Run elasticity tests and verify GREEN**

Run the full elasticity test command from Task 4.

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/consumer_oversold/elasticity.py \
  tests/test_consumer_oversold_elasticity.py
rtk git commit -m "feat: compute actual consumer market capacity"
```

### Task 6: Score elasticity components and combine one final rank

**Files:**
- Modify: `src/stock_research/consumer_oversold/elasticity.py`
- Modify: `src/stock_research/consumer_oversold/scoring.py:502-end`
- Modify: `tests/test_consumer_oversold_elasticity.py`
- Modify: `tests/test_consumer_oversold_scoring.py`

- [ ] **Step 1: Write failing percentile and gate tests**

```python
def test_elasticity_score_uses_approved_component_weights_and_winsorized_percentiles():
    rows = elasticity_component_rows()

    result = score_rebound_elasticity(rows).set_index("asset_id")

    assert result.loc["A", "elasticity_score"] == pytest.approx(
        result.loc["A", "residual_deviation_score"] * 0.35
        + result.loc["A", "stock_character_score"] * 0.25
        + result.loc["A", "market_capacity_score"] * 0.20
        + result.loc["A", "catalyst_liquidity_score"] * 0.20
    )


def test_small_cap_cannot_rescue_ineligible_candidate():
    rows = unified_rank_rows()
    rows.loc[rows.asset_id.eq("bad"), ["eligible", "elasticity_score"]] = [False, 100.0]

    result = rank_unified_candidates(rows, CONFIG)

    assert "bad" not in set(result["asset_id"])


def test_final_score_is_seventy_thirty_percentile_rank_with_stable_ties():
    result = rank_unified_candidates(unified_rank_rows(), CONFIG)

    expected = result["repair_rank_percentile"] * 0.70 + result["elasticity_rank_percentile"] * 0.30
    assert result["final_rank_score"].tolist() == pytest.approx(expected.tolist())
    assert result.sort_values("final_rank")["asset_id"].tolist() == ["A", "B", "C"]
```

Add tests proving missing coverage cannot become a zero or best value, and a recent limit-up does not receive an automatic penalty when residual deviation remains high.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_consumer_oversold_elasticity.py \
  tests/test_consumer_oversold_scoring.py -q
```

Expected: missing scoring functions and legacy bucket rank assertions fail after the intended API change.

- [ ] **Step 3: Implement component percentiles and unified rank**

Add:

```python
RESIDUAL_COMPONENT_DIRECTIONS = {
    "drawdown_from_high_1y": False,
    "drawdown_from_high_2y": False,
    "price_position_1y": False,
    "price_position_2y": False,
    "distance_hfq_ma120": False,
    "distance_hfq_ma250": False,
    "rebound_from_low_60d": False,
    "rebound_from_low_120d": False,
    "relative_return_6m": False,
    "valuation_percentile": False,
}
STOCK_CHARACTER_COMPONENT_DIRECTIONS = {
    "limit_up_count_2y": True,
    "up_7pct_count_2y": True,
    "up_5pct_count_2y": True,
    "upside_tail_volatility_2y": True,
    "positive_after_big_up_1d_rate": True,
    "positive_after_big_up_3d_rate": True,
    "positive_after_big_up_5d_rate": True,
}
MARKET_CAPACITY_COMPONENT_DIRECTIONS = {
    "log_current_float_market_cap": False,
}
CATALYST_LIQUIDITY_COMPONENT_DIRECTIONS = {
    "catalyst_verifiability_score": True,
    "average_amount_20d": True,
    "average_turnover_rate_20d": True,
    "amount_to_float_cap_20d": True,
}


def winsorize(values: pd.Series, lower: float, upper: float) -> pd.Series:
    finite = values.replace([np.inf, -np.inf], np.nan).dropna()
    if finite.empty:
        return values.astype(float)
    return values.clip(lower=finite.quantile(lower), upper=finite.quantile(upper))


def score_rebound_elasticity(rows: pd.DataFrame) -> pd.DataFrame:
    # Final components share one eligible-and-complete cross-section.
    # Automatic components are recomputed in an independent automatic-eligible cross-section.
    frame = rows.copy()
    component_specs = {
        "residual_deviation_score": RESIDUAL_COMPONENT_DIRECTIONS,
        "stock_character_score": STOCK_CHARACTER_COMPONENT_DIRECTIONS,
        "market_capacity_score": MARKET_CAPACITY_COMPONENT_DIRECTIONS,
        "catalyst_liquidity_score": CATALYST_LIQUIDITY_COMPONENT_DIRECTIONS,
    }
    for output, directions in component_specs.items():
        percentiles = []
        for field, ascending in directions.items():
            numeric = winsorize(pd.to_numeric(frame[field], errors="coerce"), 0.05, 0.95)
            percentiles.append(numeric.rank(pct=True, ascending=ascending, method="average") * 100.0)
        frame[output] = pd.concat(percentiles, axis=1).mean(axis=1, skipna=False)
    frame["elasticity_score"] = (
        frame["residual_deviation_score"] * 0.35
        + frame["stock_character_score"] * 0.25
        + frame["market_capacity_score"] * 0.20
        + frame["catalyst_liquidity_score"] * 0.20
    )
    return frame


def rank_unified_candidates(
    scored_rows: pd.DataFrame,
    config: ConsumerOversoldConfig,
) -> pd.DataFrame:
    required_coverage = [
        "residual_deviation_coverage",
        "stock_character_coverage",
        "market_capacity_coverage",
        "catalyst_liquidity_coverage",
    ]
    frame = scored_rows.loc[
        scored_rows["eligible"].eq(True)
        & scored_rows[required_coverage].all(axis=1)
    ].copy()
    frame["repair_rank_percentile"] = frame["composite_score"].rank(
        pct=True, ascending=True, method="average"
    ) * 100.0
    frame["elasticity_rank_percentile"] = frame["elasticity_score"].rank(
        pct=True, ascending=True, method="average"
    ) * 100.0
    frame["final_rank_score"] = (
        frame["repair_rank_percentile"] * config.repair_rank_weight
        + frame["elasticity_rank_percentile"] * config.elasticity_rank_weight
    )
    frame = frame.sort_values(
        ["final_rank_score", "composite_score", "elasticity_score", "asset_id"],
        ascending=[False, False, False, True],
        kind="stable",
    ).reset_index(drop=True)
    frame["final_rank"] = np.arange(1, len(frame) + 1)
    return frame
```

Use candidate-pool percentiles with explicit direction for every component. Winsorize raw count/volatility inputs at the 5th and 95th percentiles before ranking. Rank only rows where existing `eligible` is true and all elasticity coverage flags are true. Stable tie-break order is `final_rank_score DESC`, `composite_score DESC`, `elasticity_score DESC`, `asset_id ASC`.

Keep `repair_bucket` as a label. Deprecate `rank_candidate_buckets()` from new pipeline calls but retain it until legacy tests and readers are migrated.

- [ ] **Step 4: Run scoring tests and verify GREEN**

Run the command from Step 2.

Expected: all elasticity and scoring tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/consumer_oversold/elasticity.py \
  src/stock_research/consumer_oversold/scoring.py \
  tests/test_consumer_oversold_elasticity.py \
  tests/test_consumer_oversold_scoring.py
rtk git commit -m "feat: rank consumer repair and rebound elasticity"
```

### Task 7: Build Top60 pre-audit, evidence coverage, Top20, and reserve

**Files:**
- Modify: `src/stock_research/consumer_oversold/pipeline.py:294-524,588-end`
- Modify: `tests/test_consumer_oversold_pipeline.py`

- [ ] **Step 1: Write failing two-stage pipeline tests**

```python
def test_pipeline_scores_full_pool_before_evidence_and_publishes_one_top20():
    frames, evidence, config = elasticity_frames(asset_count=65, evidence_count=45)

    result = build_consumer_oversold_weekly_from_frames(
        frames,
        repair_evidence=evidence,
        config=config,
    )

    assert len(result["preaudit"]) == 60
    assert len(result["top20"]) == 20
    assert len(result["reserve"]) == 20
    assert result["top20"]["final_rank"].tolist() == list(range(1, 21))
    assert result["reserve"]["final_rank"].tolist() == list(range(21, 41))
    assert set(result["top20"]["asset_id"]).isdisjoint(result["reserve"]["asset_id"])


def test_pipeline_refuses_claim_of_complete_top20_when_evidence_pool_below_forty():
    frames, evidence, config = elasticity_frames(asset_count=65, evidence_count=39)

    result = build_consumer_oversold_weekly_from_frames(
        frames,
        repair_evidence=evidence,
        config=config,
    )

    assert result["top20"].empty
    assert "evidence_complete_pool_below_40" in result["coverage"]["warnings"]
    assert result["coverage"]["publication_status"] == "coverage_insufficient"


def test_pipeline_old_new_comparison_tracks_rank_changes_and_nonselection():
    frames, evidence, config = elasticity_frames(asset_count=65, evidence_count=45)
    result = build_consumer_oversold_weekly_from_frames(
        frames,
        repair_evidence=evidence,
        config=config,
    )
    comparison = result["comparison"].set_index("asset_id")

    assert comparison.loc["JAC", "old_rank"] == 18
    assert comparison.loc["JAC", "new_rank"] < 18
    assert comparison.loc["SERES", "new_exclusion_reasons"] != ""
```

- [ ] **Step 2: Run pipeline tests and verify RED**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_consumer_oversold_pipeline.py -q
```

Expected: missing output keys and legacy two-bucket assumptions.

- [ ] **Step 3: Add the two-stage data flow**

Refactor the pipeline in this order:

```python
quantitative = build_quantitative_candidate_frame(
    frames=working_frames,
    config=config,
)
preaudit_ranked = build_preaudit_rank(quantitative, config).head(config.preaudit_size)
validated_evidence = validate_repair_evidence(repair_evidence, config.trade_date)
reviewed = merge_evidence_and_apply_hard_gates(
    quantitative=quantitative,
    validated_evidence=validated_evidence,
    hard_risk_features=hard_risk_features,
    config=config,
)
elasticity = build_elasticity_frame(
    market_history=working_frames["market"],
    share_capacity=working_frames["share_capacity"],
    reviewed_candidates=reviewed,
    config=config,
)
ranked = rank_unified_candidates(reviewed.merge(elasticity, on="asset_id"), config)
top20 = ranked.head(config.final_top_n)
reserve = ranked.iloc[config.final_top_n:config.final_top_n + config.reserve_top_n]
```

The pre-audit frame must retain evidence status but must not require evidence to calculate automatic rank. The final ranked pool must require evidence and both gates. Add coverage counts for full pool, automatic eligibility, pre-audit 60, evidence reviewed, evidence complete, elasticity complete, final 20, and reserve 20.

Immediately after valuation-feature creation, rename the scenario output columns for every downstream/public frame:

```python
valuation_features = valuation_features.rename(columns={
    "pessimistic_market_cap": "pessimistic_scenario_market_cap",
    "base_market_cap": "base_scenario_market_cap",
    "optimistic_market_cap": "optimistic_scenario_market_cap",
})
```

The actual capacity frame owns `current_total_market_cap` and `current_float_market_cap`; no public artifact may expose a scenario column under the ambiguous name `base_market_cap`.

Define the evidence-independent pre-audit score exactly as:

```python
preaudit_score = (
    oversold_score * 0.30
    + valuation_repair_score * 0.25
    + operating_gap_score * 0.20
    + balance_sheet_score * 0.15
    + automatic_elasticity_score * 0.10
)
```

`automatic_elasticity_score` reweights only residual deviation, stock character, and market capacity to 45%/30%/25%; it must not use catalyst evidence or any 2026-07-30 outcome. Pre-audit eligibility requires the terminal-consumer audit, market/finance/valuation coverage, automatic hard-risk clearance, and quantitative oversold gates, but intentionally does not require manual evidence. Rank ties by `preaudit_score DESC`, `oversold_score DESC`, `asset_id ASC`.

Build comparison columns `asset_id`, `stock_code`, `stock_name`, `repair_bucket`, `old_bucket_rank`, `old_combined_rank`, `new_rank`, `rank_change`, `composite_score`, `elasticity_score`, `final_rank_score`, and exclusion reasons.

For comparison only, define `old_combined_rank` by sorting every legacy-gate-eligible row on `composite_score DESC, asset_id ASC`; do not concatenate the historical bucket outputs and treat their bucket ranks as directly comparable. Preserve `old_bucket_rank` separately when a row appeared in a legacy bucket.

- [ ] **Step 4: Run pipeline tests and verify GREEN**

Run the command from Step 2.

Expected: all pipeline tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/consumer_oversold/pipeline.py \
  tests/test_consumer_oversold_pipeline.py
rtk git commit -m "feat: build audited unified consumer top twenty"
```

### Task 8: Publish unified immutable artifacts and report

**Files:**
- Modify: `src/stock_research/consumer_oversold/reporting.py:89-end`
- Modify: `tests/test_consumer_oversold_reporting.py`
- Modify: `tests/test_consumer_oversold_pipeline.py`

- [ ] **Step 1: Write failing reporting tests**

```python
def test_unified_release_contains_all_rank_and_audit_artifacts(tmp_path):
    paths = write_consumer_oversold_artifacts(
        output_dir=tmp_path,
        top20=top20_frame(),
        reserve=reserve_frame(),
        preaudit=preaudit_frame(),
        comparison=comparison_frame(),
        scores=scores_frame(),
        exclusions=exclusions_frame(),
        evidence=evidence_frame(),
        coverage=coverage_payload(),
    )

    assert set(paths) == set(OUTPUT_FILENAMES)
    assert len(pd.read_csv(paths["top20"])) == 20
    assert len(pd.read_csv(paths["reserve"])) == 20
    assert len(pd.read_csv(paths["preaudit"])) == 60


def test_report_explains_single_rank_and_jac_she_de_seres_breakdown(tmp_path):
    report = Path(paths["report"]).read_text(encoding="utf-8")

    assert "修复潜力分位 × 70%" in report
    assert "反弹弹性分位 × 30%" in report
    assert "江淮汽车" in report
    assert "舍得酒业" in report
    assert "赛力斯" in report
    assert "研究候选，不是交易指令" in report
```

Retain existing manifest, readonly permission, lock, rollback, CSV formula-safety, and symlink-attack tests.

- [ ] **Step 2: Run reporting tests and verify RED**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_consumer_oversold_reporting.py \
  tests/test_consumer_oversold_pipeline.py -q
```

Expected: writer signature and manifest expectations still use the legacy artifacts.

- [ ] **Step 3: Update artifact publication and report rendering**

Publish exactly the new `OUTPUT_FILENAMES` set. The Top20 report table must include:

```text
rank, stock_code, stock_name, repair_bucket,
repair_rank_percentile, elasticity_rank_percentile, final_rank_score,
current_float_market_cap, current_total_market_cap, market_cap_source,
limit_up_count_2y, up_7pct_count_2y, up_5pct_count_2y,
drawdown_from_high_1y, drawdown_from_high_2y,
price_position_1y, price_position_2y,
rebound_from_low_60d, rebound_from_low_120d,
repair_thesis, leading_indicator, main_risks, invalidation_conditions
```

The coverage section must make any Top60 evidence gap visible. Continue using a release directory, manifest verification, 0444 files, 0555 release directory, process lock, atomic `current` switch, and rollback.

- [ ] **Step 4: Run reporting and pipeline tests and verify GREEN**

Run the command from Step 2.

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/consumer_oversold/reporting.py \
  tests/test_consumer_oversold_reporting.py \
  tests/test_consumer_oversold_pipeline.py
rtk git commit -m "feat: publish unified consumer elasticity artifacts"
```

### Task 9: Preserve historical evaluation and add 5/20-day horizons

**Files:**
- Modify: `src/stock_research/consumer_oversold/evaluation.py:20-320`
- Modify: `tests/test_consumer_oversold_evaluation.py`

- [ ] **Step 1: Write failing compatibility tests**

```python
def test_snapshot_reader_accepts_new_unified_top20_release(tmp_path):
    release = sealed_unified_release(tmp_path, trade_date="2026-07-29", asset_count=20)

    snapshots, membership = _discover_snapshots(release, "2026-08-31")

    assert len(snapshots) == 20
    assert set(snapshots["repair_bucket"]) == {"expected_repair", "early_validation"}


def test_snapshot_reader_still_accepts_legacy_two_bucket_release(tmp_path):
    release = _sealed_release(tmp_path, "consumer-oversold-old", "2026-07-28", "A", "expected_repair")

    snapshots, _ = _discover_snapshots(release, "2026-08-31")

    assert len(snapshots) == 1


def test_default_evaluation_horizons_include_five_and_twenty_sessions():
    result = evaluate_consumer_oversold_snapshots(_snapshots(), _bars(periods=21))

    assert set(result["detail"]["horizon"]) == {5, 20}
```

- [ ] **Step 2: Run evaluation tests and verify RED**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_consumer_oversold_evaluation.py -q
```

Expected: new unified artifact is not discovered and default horizons remain legacy values.

- [ ] **Step 3: Implement dual-schema snapshot reading**

When `consumer_oversold_unified_top20.csv` exists and is present in the verified manifest, read it. Otherwise read the legacy expected/early pair. Never mix the two schemas in one release. Change default horizons to `(5, 20)` while retaining optional caller-provided horizons. Keep snapshot membership immutable and all existing calendar, lock, manifest, and rollback protections.

- [ ] **Step 4: Run evaluation tests and verify GREEN**

Run the command from Step 2.

Expected: all evaluation tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/consumer_oversold/evaluation.py \
  tests/test_consumer_oversold_evaluation.py
rtk git commit -m "feat: evaluate unified consumer ranks at five and twenty days"
```

### Task 10: Add explicit backtest cutoff and automatic latest-complete daily mode

**Files:**
- Modify: `src/stock_research/consumer_oversold/loaders.py`
- Modify: `src/stock_research/consumer_oversold/pipeline.py`
- Modify: `src/stock_research/cli.py:3960-3990`
- Modify: `tests/test_consumer_oversold_loaders.py`
- Modify: `tests/test_consumer_oversold_cli.py`

- [ ] **Step 1: Write failing latest-complete-date and CLI tests**

```python
def test_latest_complete_trade_date_requires_broad_raw_and_hfq_coverage(monkeypatch):
    _install_db(monkeypatch, [[
        {"trade_date": "2026-07-30", "hfq_assets": 5000, "raw_assets": 1200},
        {"trade_date": "2026-07-29", "hfq_assets": 5000, "raw_assets": 4998},
    ]])

    assert resolve_latest_complete_consumer_trade_date(service="svc") == "2026-07-29"


def test_cli_uses_explicit_date_for_backtest_mode(monkeypatch):
    args = parser().parse_args([
        "consumer-oversold-weekly",
        "--trade-date", "2026-07-29",
        "--evidence-path", "/tmp/evidence.csv",
        "--output-dir", "/tmp/out",
    ])

    assert args.trade_date == "2026-07-29"


def test_cli_resolves_latest_complete_date_when_trade_date_is_omitted(monkeypatch):
    monkeypatch.setattr(cli, "resolve_latest_complete_consumer_trade_date", lambda service: "2026-07-29")
    runner = monkeypatch_runner(monkeypatch)

    cli.main(["consumer-oversold-weekly", "--evidence-path", "/tmp/evidence.csv", "--output-dir", "/tmp/out"])

    assert runner.call_args.kwargs["trade_date"] == "2026-07-29"


def test_cli_preaudit_only_does_not_claim_final_top20(monkeypatch, capsys):
    runner = monkeypatch_runner(
        monkeypatch,
        result={"preaudit": pd.DataFrame(index=range(60)), "top20": pd.DataFrame()},
    )

    cli.main([
        "consumer-oversold-weekly",
        "--trade-date", "2026-07-29",
        "--preaudit-only",
        "--evidence-path", "/tmp/evidence.csv",
        "--output-dir", "/tmp/out",
    ])

    assert runner.call_args.kwargs["preaudit_only"] is True
    assert "consumer_oversold|publication_status|preaudit_only" in capsys.readouterr().out
```

- [ ] **Step 2: Run loader and CLI tests and verify RED**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_consumer_oversold_loaders.py \
  tests/test_consumer_oversold_cli.py -q
```

Expected: resolver absent and `--trade-date` still required.

- [ ] **Step 3: Implement the cutoff resolver and CLI behavior**

Add `resolve_latest_complete_consumer_trade_date()` using the latest open exchange date where both raw and hfq distinct-asset counts are at least 99% of the maximum respective counts observed over the previous 20 open trading dates. Make `--trade-date` optional; an explicit value always wins. Add `--preaudit-only`; it must publish only the pre-audit/coverage artifacts and set `publication_status=preaudit_only`, never a final Top20. Print:

```text
consumer_oversold|as_of_trade_date|2026-07-29
consumer_oversold|date_mode|explicit_backtest
```

or `latest_complete_daily` when resolved automatically.

- [ ] **Step 4: Run loader and CLI tests and verify GREEN**

Run the command from Step 2.

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/consumer_oversold/loaders.py \
  src/stock_research/consumer_oversold/pipeline.py \
  src/stock_research/cli.py \
  tests/test_consumer_oversold_loaders.py \
  tests/test_consumer_oversold_cli.py
rtk git commit -m "feat: support daily and historical consumer ranking cutoffs"
```

### Task 11: Build the 2026-07-29 evidence buffer and regenerate Top20

**Files:**
- Create operational input: `outputs/research/consumer_oversold_daily/2026-07-29/consumer_oversold_repair_evidence.csv`
- Create a generated immutable release beneath `outputs/research/consumer_oversold_daily/2026-07-29/.releases/`.
- Verify generated `current/` artifacts; do not commit operational outputs.

- [ ] **Step 1: Run a quantitative pre-audit without claiming a final list**

Run the pipeline in pre-audit mode:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  consumer-oversold-weekly \
  --trade-date 2026-07-29 \
  --preaudit-only \
  --evidence-path outputs/research/consumer_oversold_daily/2026-07-29/consumer_oversold_repair_evidence.csv \
  --output-dir outputs/research/consumer_oversold_daily/2026-07-29
```

Expected: Top60 pre-audit is produced, final publication status is `preaudit_only`, and no Top20 is claimed.

- [ ] **Step 2: Audit the Top60 evidence buffer**

For the automatic Top60, populate or verify:

```text
repair thesis and unrepaired metrics
catalyst source/title/date
audit source/title/date
pledge-debt source/title/date
permanent-impairment source/title/date
expected validation date
main risks and invalidation conditions
terminal consumer brand or OEM audit decision
```

All source dates must be no later than 2026-07-29. Continue reviewing candidates in automatic rank order until at least 40 evidence-complete, gate-clear candidates exist. Do not use 2026-07-30 market behavior to decide whom to review or include.

- [ ] **Step 3: Run the final 2026-07-29 ranking**

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  consumer-oversold-weekly \
  --trade-date 2026-07-29 \
  --evidence-path outputs/research/consumer_oversold_daily/2026-07-29/consumer_oversold_repair_evidence.csv \
  --output-dir outputs/research/consumer_oversold_daily/2026-07-29
```

Expected machine lines:

```text
consumer_oversold|as_of_trade_date|2026-07-29
consumer_oversold|top20_rows|20
consumer_oversold|reserve_rows|20
consumer_oversold|preaudit_rows|60
```

- [ ] **Step 4: Verify 江淮、舍得、赛力斯 without outcome leakage**

Inspect the comparison and full-score artifacts. Confirm that:

- 江淮汽车 and 舍得酒业 receive actual market-cap and historical-character values calculated only through 2026-07-29;
- 赛力斯 is either ranked with complete evidence or excluded with explicit reasons; it must not disappear because evidence was never reviewed;
- `current_market_cap` is distinct from `base_scenario_market_cap`;
- no selected or reserve row contains a source date after 2026-07-29;
- Top20 and reserve are disjoint and ranks 1—40 are contiguous.

- [ ] **Step 5: Verify manifests and immutable permissions**

```bash
rtk sh -c 'cd outputs/research/consumer_oversold_daily/2026-07-29/current && sha256sum -c .manifest.sha256'
rtk ls -laL outputs/research/consumer_oversold_daily/2026-07-29/current
```

Expected: every hash is `OK`, artifacts are 0444, and the release directory is 0555.

### Task 12: Final regression, PIT audit, and independent review

**Files:**
- Verify all files from Tasks 1—11.

- [ ] **Step 1: Run the complete consumer feature regression**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_consumer_oversold_contracts.py \
  tests/test_consumer_oversold_universe.py \
  tests/test_consumer_oversold_features.py \
  tests/test_consumer_oversold_elasticity.py \
  tests/test_consumer_oversold_fundamentals.py \
  tests/test_consumer_oversold_evidence.py \
  tests/test_consumer_oversold_scoring.py \
  tests/test_consumer_oversold_reporting.py \
  tests/test_consumer_oversold_loaders.py \
  tests/test_consumer_oversold_pipeline.py \
  tests/test_consumer_oversold_cli.py \
  tests/test_consumer_oversold_evaluation.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run adjacent PIT, factor, and universe regressions**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_point_in_time_finance.py \
  tests/test_finance_ttm.py \
  tests/test_factor_fundamental.py \
  tests/test_factor_value.py \
  tests/test_universe.py \
  tests/test_industry_membership_service.py \
  tests/test_watchlist_fundamental_pit_context.py \
  tests/test_dragon_case_library.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run repository hygiene checks**

```bash
rtk git diff --check
rtk git status --short
```

Expected: no whitespace errors and no unintended tracked changes.

- [ ] **Step 4: Perform a strict 2026-07-29 PIT audit**

Check the sealed artifacts programmatically:

```python
assert market_date_max <= "2026-07-29"
assert finance_announcement_max <= "2026-07-29"
assert evidence_source_date_max <= "2026-07-29"
assert top20["final_rank"].tolist() == list(range(1, 21))
assert reserve["final_rank"].tolist() == list(range(21, 41))
assert set(top20.asset_id).isdisjoint(reserve.asset_id)
assert preaudit.asset_id.nunique() == 60
assert evidence_complete_pool >= 40
```

Expected: every assertion passes.

- [ ] **Step 5: Request independent code and artifact review**

Review the complete implementation against:

```text
docs/superpowers/specs/2026-07-30-consumer-oversold-elasticity-ranking-design.md
```

The reviewer must explicitly check for future leakage, market-cap field confusion, micro-cap bias, board-aware limit-up counting, evidence-caused omissions, unified rank arithmetic, legacy snapshot compatibility, immutable publication, and the actual 2026-07-29 Top20/reserve/Top60 artifacts. Resolve every Critical and Important finding and rerun affected tests before delivery.
