# External Factor Library Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first controlled set of external-reference Alpha101, GTJA191, and Qlib-style factors as local pandas/numpy functions and integrate them into `factor.factor_daily` rows without promoting them into scoring.

**Architecture:** Add reusable factor operators to `factors/base.py`, then implement small representative factor sets in the existing adapter modules. Extend `factor_pipeline.py` to emit external-source long factor rows with `source` set to `alpha101`, `gtja191`, or `qlib`, while leaving `manual_v1` scoring weights unchanged.

**Tech Stack:** Python 3.11+, pandas, numpy, pytest, PostgreSQL-backed existing factor pipeline, Git.

---

## Usage Boundaries

- Reference external projects for ideas only.
- Do not add Qlib, RQAlpha, vectorbt, Alphalens, pyfolio, TA-Lib, or pandas-ta as dependencies.
- Do not copy large external code blocks.
- Implement only representative pandas/numpy functions adapted to this repository's bar schema.
- All rolling calculations must use current and prior rows only.
- External-reference factors must be evaluated later before scoring promotion.

## File Map

Modify:

- `src/stock_research/factors/base.py`: shared factor operators.
- `src/stock_research/factors/alpha101.py`: Alpha101-style representative factors.
- `src/stock_research/factors/gtja191.py`: GTJA191-style representative factors.
- `src/stock_research/factors/qlib_alpha.py`: Qlib Alpha158/360-style representative factors.
- `src/stock_research/factor_config.py`: factor groups/directions for external reference factors, no weights.
- `src/stock_research/factor_pipeline.py`: external factor row generation and daily build integration.

Create:

- `tests/test_external_factor_operators.py`
- `tests/test_alpha101_factors.py`
- `tests/test_gtja191_factors.py`
- `tests/test_qlib_alpha_factors.py`

Modify:

- `tests/test_factor_pipeline.py`
- `tests/test_factor_cli.py` only if CLI output or parser behavior changes. This plan should not require CLI changes.

---

## Milestone 1: Shared Factor Operators

### Task 1: Add External Factor Operators

**Files:**

- Modify: `src/stock_research/factors/base.py`
- Create: `tests/test_external_factor_operators.py`

- [ ] **Step 1: Write failing operator tests**

Create `tests/test_external_factor_operators.py`:

```python
import pandas as pd
import pytest

from stock_research.factors import base


def test_cross_sectional_rank_ranks_within_trade_date():
    frame = pd.DataFrame(
        {
            "trade_date": ["2026-01-01", "2026-01-01", "2026-01-02"],
            "asset_id": ["A", "B", "A"],
            "value": [10.0, 20.0, 5.0],
        }
    )

    result = base.cross_sectional_rank(frame, "value")

    assert result.tolist() == [0.5, 1.0, 1.0]


def test_ts_rank_uses_current_and_prior_values_only():
    values = pd.Series([3.0, 1.0, 2.0, 5.0])

    result = base.ts_rank(values, window=3)

    assert pd.isna(result.iloc[0])
    assert result.iloc[2] == pytest.approx(2 / 3)
    assert result.iloc[3] == pytest.approx(1.0)


def test_decay_linear_weights_recent_values_more():
    values = pd.Series([1.0, 2.0, 3.0])

    result = base.decay_linear(values, window=3)

    assert result.iloc[-1] == pytest.approx((1.0 * 1 + 2.0 * 2 + 3.0 * 3) / 6)


def test_delta_delay_signed_power_and_rolling_relationships():
    left = pd.Series([1.0, 2.0, 4.0, 7.0])
    right = pd.Series([2.0, 4.0, 8.0, 14.0])

    assert base.delta(left, period=1).tolist()[1:] == [1.0, 2.0, 3.0]
    assert base.delay(left, period=2).tolist()[2:] == [1.0, 2.0]
    assert base.signed_power(pd.Series([-2.0, 3.0]), 2).tolist() == [-4.0, 9.0]
    assert base.rolling_corr(left, right, window=3).iloc[-1] == pytest.approx(1.0)
    assert base.rolling_cov(left, right, window=3).iloc[-1] > 0
```

- [ ] **Step 2: Run operator tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_external_factor_operators.py -q
```

Expected: FAIL because the operator functions do not exist.

- [ ] **Step 3: Implement shared operators**

In `src/stock_research/factors/base.py`, append:

```python
def cross_sectional_rank(frame: pd.DataFrame, column: str) -> pd.Series:
    values = numeric_series(frame, column)
    return values.groupby(frame["trade_date"]).rank(pct=True)


def ts_rank(values: pd.Series, window: int) -> pd.Series:
    clean = pd.to_numeric(values, errors="coerce")

    def rank_latest(window_values: pd.Series) -> float:
        if window_values.isna().any():
            return np.nan
        return float(window_values.rank(pct=True).iloc[-1])

    return clean.rolling(window).apply(rank_latest, raw=False)


def decay_linear(values: pd.Series, window: int) -> pd.Series:
    clean = pd.to_numeric(values, errors="coerce")
    weights = np.arange(1, window + 1, dtype="float64")
    denominator = float(weights.sum())

    def weighted(window_values: np.ndarray) -> float:
        if np.isnan(window_values).any():
            return np.nan
        return float(np.dot(window_values, weights) / denominator)

    return clean.rolling(window).apply(weighted, raw=True)


def delta(values: pd.Series, period: int = 1) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").diff(period)


def delay(values: pd.Series, period: int = 1) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").shift(period)


def signed_power(values: pd.Series, power: float) -> pd.Series:
    clean = pd.to_numeric(values, errors="coerce")
    return clean.abs().pow(power) * np.sign(clean)


def rolling_corr(left: pd.Series, right: pd.Series, window: int) -> pd.Series:
    return pd.to_numeric(left, errors="coerce").rolling(window).corr(
        pd.to_numeric(right, errors="coerce")
    )


def rolling_cov(left: pd.Series, right: pd.Series, window: int) -> pd.Series:
    return pd.to_numeric(left, errors="coerce").rolling(window).cov(
        pd.to_numeric(right, errors="coerce")
    )
```

- [ ] **Step 4: Run operator tests to verify pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_external_factor_operators.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/factors/base.py tests/test_external_factor_operators.py
git commit -m "Add external factor operators"
```

---

## Milestone 2: Alpha101-Style Representative Factors

### Task 2: Implement Alpha101-Style Factors

**Files:**

- Modify: `src/stock_research/factors/alpha101.py`
- Create: `tests/test_alpha101_factors.py`

- [ ] **Step 1: Write failing Alpha101 tests**

Create `tests/test_alpha101_factors.py`:

```python
import pandas as pd

from stock_research.factors import alpha101


def _bars() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=12, freq="D")
    return pd.DataFrame(
        {
            "trade_date": list(dates) * 2,
            "asset_id": ["A"] * 12 + ["B"] * 12,
            "open": list(range(10, 22)) + list(range(20, 32)),
            "high": list(range(11, 23)) + list(range(21, 33)),
            "low": list(range(9, 21)) + list(range(19, 31)),
            "close": list(range(10, 22)) + list(range(21, 33)),
            "preclose": [None] + list(range(10, 21)) + [None] + list(range(21, 32)),
            "volume": [1000.0 + index * 10 for index in range(12)] * 2,
            "amount": [100000.0 + index * 1000 for index in range(12)] * 2,
        }
    )


def test_compute_alpha101_factors_returns_representative_columns():
    result = alpha101.compute_alpha101_factors(_bars())

    assert {
        "alpha101_delta_close_1_rank",
        "alpha101_corr_open_volume_10",
        "alpha101_decay_delta_close_5",
    }.issubset(result.columns)
    assert set(result["asset_id"]) == {"A", "B"}
    assert not result.groupby("asset_id").tail(1)["alpha101_delta_close_1_rank"].isna().any()


def test_alpha101_factors_do_not_use_future_rows():
    bars = _bars()
    baseline = alpha101.compute_alpha101_factors(bars).copy()
    mutated = bars.copy()
    mutated.loc[mutated["trade_date"] == pd.Timestamp("2026-01-12"), "close"] = 9999.0

    changed = alpha101.compute_alpha101_factors(mutated)
    mask = baseline["trade_date"] < pd.Timestamp("2026-01-12")

    assert baseline.loc[mask, "alpha101_delta_close_1_rank"].equals(
        changed.loc[mask, "alpha101_delta_close_1_rank"]
    )
```

- [ ] **Step 2: Run Alpha101 tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_alpha101_factors.py -q
```

Expected: FAIL because `compute_alpha101_factors` does not exist.

- [ ] **Step 3: Implement Alpha101-style factors**

Replace `src/stock_research/factors/alpha101.py` with:

```python
"""WorldQuant Alpha101-style adapter boundary.

These are small representative price-volume factors inspired by Alpha101
building blocks. They are rewritten for this project's daily bar schema and do
not import external Alpha101 implementations.
"""

import pandas as pd

from stock_research.factors.base import (
    cross_sectional_rank,
    decay_linear,
    delta,
    prepare_daily_bars,
    rolling_corr,
)

SOURCE = "alpha101"


def compute_alpha101_factors(bars: pd.DataFrame) -> pd.DataFrame:
    """Return representative Alpha101-style factors.

    Inputs: trade_date, asset_id, open, close, volume.
    Outputs:
    - alpha101_delta_close_1_rank: cross-sectional rank of negative 1-day close delta.
    - alpha101_corr_open_volume_10: negative rolling correlation between open and volume.
    - alpha101_decay_delta_close_5: 5-day linear-decayed close delta.
    Future data: no future rows are used; all rolling windows are backward-looking.
    """
    frame = prepare_daily_bars(bars)
    pieces = []
    for _, group in frame.groupby("asset_id", sort=False):
        asset = group.sort_values("trade_date").copy()
        asset["_delta_close_1"] = delta(asset["close"], 1)
        asset["alpha101_corr_open_volume_10"] = -rolling_corr(
            asset["open"],
            asset["volume"],
            window=10,
        )
        asset["alpha101_decay_delta_close_5"] = decay_linear(
            delta(asset["close"], 1),
            window=5,
        )
        pieces.append(asset)

    result = pd.concat(pieces, ignore_index=True)
    result["alpha101_delta_close_1_rank"] = cross_sectional_rank(
        result.assign(_negative_delta=-result["_delta_close_1"]),
        "_negative_delta",
    )
    return result[
        [
            "trade_date",
            "asset_id",
            "alpha101_delta_close_1_rank",
            "alpha101_corr_open_volume_10",
            "alpha101_decay_delta_close_5",
        ]
    ]
```

- [ ] **Step 4: Run Alpha101 tests to verify pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_alpha101_factors.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/factors/alpha101.py tests/test_alpha101_factors.py
git commit -m "Add representative Alpha101 factors"
```

---

## Milestone 3: GTJA191-Style Representative Factors

### Task 3: Implement GTJA191-Style Factors

**Files:**

- Modify: `src/stock_research/factors/gtja191.py`
- Create: `tests/test_gtja191_factors.py`

- [ ] **Step 1: Write failing GTJA191 tests**

Create `tests/test_gtja191_factors.py`:

```python
import pandas as pd

from stock_research.factors import gtja191


def test_compute_gtja191_factors_returns_short_horizon_volume_price_columns():
    dates = pd.date_range("2026-01-01", periods=15, freq="D")
    bars = pd.DataFrame(
        {
            "trade_date": dates,
            "asset_id": ["A"] * 15,
            "open": range(10, 25),
            "high": range(11, 26),
            "low": range(9, 24),
            "close": range(10, 25),
            "preclose": [None] + list(range(10, 24)),
            "volume": [1000.0 + index * 20 for index in range(15)],
            "amount": [100000.0 + index * 2000 for index in range(15)],
        }
    )

    result = gtja191.compute_gtja191_factors(bars)

    assert {
        "gtja191_vp_corr_10",
        "gtja191_amount_momentum_5_10",
        "gtja191_intraday_strength_6",
    }.issubset(result.columns)
    assert result.iloc[-1]["gtja191_amount_momentum_5_10"] > 1.0
```

- [ ] **Step 2: Run GTJA191 tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_gtja191_factors.py -q
```

Expected: FAIL because `compute_gtja191_factors` does not exist.

- [ ] **Step 3: Implement GTJA191-style factors**

Replace `src/stock_research/factors/gtja191.py` with:

```python
"""GTJA191-style adapter boundary.

These are small, tested short-horizon volume-price factors adapted to this
project. They are not a wholesale implementation of GTJA191.
"""

import pandas as pd

from stock_research.factors.base import prepare_daily_bars, rolling_corr, safe_divide

SOURCE = "gtja191"


def compute_gtja191_factors(bars: pd.DataFrame) -> pd.DataFrame:
    """Return representative GTJA191-style short-horizon price-volume factors.

    Inputs: trade_date, asset_id, high, low, close, volume, amount.
    Outputs:
    - gtja191_vp_corr_10: 10-day rolling price-volume correlation.
    - gtja191_amount_momentum_5_10: 5-day average amount divided by 10-day average amount.
    - gtja191_intraday_strength_6: 6-day mean close location inside high-low range.
    Future data: all rolling windows are backward-looking.
    """
    frame = prepare_daily_bars(bars)
    pieces = []
    for _, group in frame.groupby("asset_id", sort=False):
        asset = group.sort_values("trade_date").copy()
        close = pd.to_numeric(asset["close"], errors="coerce")
        high = pd.to_numeric(asset["high"], errors="coerce")
        low = pd.to_numeric(asset["low"], errors="coerce")
        amount = pd.to_numeric(asset["amount"], errors="coerce")
        asset["gtja191_vp_corr_10"] = rolling_corr(close, asset["volume"], window=10)
        asset["gtja191_amount_momentum_5_10"] = safe_divide(
            amount.rolling(5).mean(),
            amount.rolling(10).mean(),
        )
        asset["gtja191_intraday_strength_6"] = safe_divide(
            close - low,
            high - low,
        ).rolling(6).mean()
        pieces.append(asset)
    result = pd.concat(pieces, ignore_index=True)
    return result[
        [
            "trade_date",
            "asset_id",
            "gtja191_vp_corr_10",
            "gtja191_amount_momentum_5_10",
            "gtja191_intraday_strength_6",
        ]
    ]
```

- [ ] **Step 4: Run GTJA191 tests to verify pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_gtja191_factors.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/factors/gtja191.py tests/test_gtja191_factors.py
git commit -m "Add representative GTJA191 factors"
```

---

## Milestone 4: Qlib Alpha158/360-Style Representative Factors

### Task 4: Implement Qlib-Style Factors

**Files:**

- Modify: `src/stock_research/factors/qlib_alpha.py`
- Create: `tests/test_qlib_alpha_factors.py`

- [ ] **Step 1: Write failing Qlib-style tests**

Create `tests/test_qlib_alpha_factors.py`:

```python
import pandas as pd

from stock_research.factors import qlib_alpha


def test_compute_qlib_alpha_factors_returns_price_shape_columns():
    dates = pd.date_range("2026-01-01", periods=8, freq="D")
    bars = pd.DataFrame(
        {
            "trade_date": dates,
            "asset_id": ["A"] * 8,
            "open": [10, 11, 12, 13, 14, 15, 16, 17],
            "high": [11, 12, 13, 14, 15, 16, 17, 18],
            "low": [9, 10, 11, 12, 13, 14, 15, 16],
            "close": [10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5],
            "preclose": [None, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5],
            "volume": [1000.0] * 8,
            "amount": [100000.0] * 8,
        }
    )

    result = qlib_alpha.compute_qlib_alpha_factors(bars)

    assert {
        "qlib_klen",
        "qlib_kupper",
        "qlib_klower",
        "qlib_ret_5",
    }.issubset(result.columns)
    assert result.iloc[-1]["qlib_klen"] > 0
```

- [ ] **Step 2: Run Qlib-style tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_qlib_alpha_factors.py -q
```

Expected: FAIL because `compute_qlib_alpha_factors` does not exist.

- [ ] **Step 3: Implement Qlib-style factors**

Replace `src/stock_research/factors/qlib_alpha.py` with:

```python
"""Qlib Alpha158/360-style adapter boundary.

Qlib is a reference for factor organization and Alpha158/360 price-shape ideas,
not a runtime dependency or the project framework.
"""

import pandas as pd

from stock_research.factors.base import prepare_daily_bars, safe_divide

SOURCE = "qlib"


def compute_qlib_alpha_factors(bars: pd.DataFrame) -> pd.DataFrame:
    """Return representative Qlib-style price shape and return factors.

    Inputs: trade_date, asset_id, open, high, low, close.
    Outputs:
    - qlib_klen: absolute candle body divided by open.
    - qlib_kupper: upper shadow divided by open.
    - qlib_klower: lower shadow divided by open.
    - qlib_ret_5: 5-day close return.
    Future data: no future rows are used.
    """
    frame = prepare_daily_bars(bars)
    pieces = []
    for _, group in frame.groupby("asset_id", sort=False):
        asset = group.sort_values("trade_date").copy()
        open_ = pd.to_numeric(asset["open"], errors="coerce")
        high = pd.to_numeric(asset["high"], errors="coerce")
        low = pd.to_numeric(asset["low"], errors="coerce")
        close = pd.to_numeric(asset["close"], errors="coerce")
        asset["qlib_klen"] = safe_divide((close - open_).abs(), open_)
        asset["qlib_kupper"] = safe_divide(high - pd.concat([open_, close], axis=1).max(axis=1), open_)
        asset["qlib_klower"] = safe_divide(pd.concat([open_, close], axis=1).min(axis=1) - low, open_)
        asset["qlib_ret_5"] = safe_divide(close, close.shift(5)) - 1.0
        pieces.append(asset)
    result = pd.concat(pieces, ignore_index=True)
    return result[
        [
            "trade_date",
            "asset_id",
            "qlib_klen",
            "qlib_kupper",
            "qlib_klower",
            "qlib_ret_5",
        ]
    ]
```

- [ ] **Step 4: Run Qlib-style tests to verify pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_qlib_alpha_factors.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/factors/qlib_alpha.py tests/test_qlib_alpha_factors.py
git commit -m "Add representative Qlib-style factors"
```

---

## Milestone 5: Factor Pipeline Integration

### Task 5: Add External Factor Row Generation

**Files:**

- Modify: `src/stock_research/factor_pipeline.py`
- Modify: `src/stock_research/factor_config.py`
- Modify: `tests/test_factor_pipeline.py`

- [ ] **Step 1: Write failing external row test**

Append to `tests/test_factor_pipeline.py`:

```python
def test_compute_external_factor_rows_preserves_source_labels(monkeypatch):
    bars = pd.DataFrame(
        {
            "trade_date": ["2026-05-08"],
            "asset_id": ["A"],
            "open": [10.0],
            "high": [11.0],
            "low": [9.0],
            "close": [10.5],
            "preclose": [10.0],
            "volume": [1000.0],
            "amount": [100000.0],
        }
    )

    monkeypatch.setattr(
        factor_pipeline.alpha101,
        "compute_alpha101_factors",
        lambda frame: pd.DataFrame(
            {"trade_date": ["2026-05-08"], "asset_id": ["A"], "alpha101_delta_close_1_rank": [0.8]}
        ),
    )
    monkeypatch.setattr(
        factor_pipeline.gtja191,
        "compute_gtja191_factors",
        lambda frame: pd.DataFrame(
            {"trade_date": ["2026-05-08"], "asset_id": ["A"], "gtja191_vp_corr_10": [0.5]}
        ),
    )
    monkeypatch.setattr(
        factor_pipeline.qlib_alpha,
        "compute_qlib_alpha_factors",
        lambda frame: pd.DataFrame(
            {"trade_date": ["2026-05-08"], "asset_id": ["A"], "qlib_klen": [0.05]}
        ),
    )

    rows = factor_pipeline.compute_external_factor_rows(
        bars,
        trade_date="2026-05-08",
        factor_groups={
            "alpha101_delta_close_1_rank": "alpha101",
            "gtja191_vp_corr_10": "gtja191",
            "qlib_klen": "qlib",
        },
        calc_version="v1",
        source_data_version="market_daily_bar:hfq",
    )

    assert set(rows["source"]) == {"alpha101", "gtja191", "qlib"}
    assert set(rows["factor_name"]) == {
        "alpha101_delta_close_1_rank",
        "gtja191_vp_corr_10",
        "qlib_klen",
    }
```

- [ ] **Step 2: Run pipeline test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_pipeline.py::test_compute_external_factor_rows_preserves_source_labels -q
```

Expected: FAIL because `compute_external_factor_rows` and imports do not exist.

- [ ] **Step 3: Add external factor config**

In `src/stock_research/factor_config.py`, add these names to `factor_groups`:

```python
        "alpha101_delta_close_1_rank": "alpha101",
        "alpha101_corr_open_volume_10": "alpha101",
        "alpha101_decay_delta_close_5": "alpha101",
        "gtja191_vp_corr_10": "gtja191",
        "gtja191_amount_momentum_5_10": "gtja191",
        "gtja191_intraday_strength_6": "gtja191",
        "qlib_klen": "qlib",
        "qlib_kupper": "qlib",
        "qlib_klower": "qlib",
        "qlib_ret_5": "qlib",
```

Add directions to `factor_directions`:

```python
        "alpha101_delta_close_1_rank": "higher",
        "alpha101_corr_open_volume_10": "higher",
        "alpha101_decay_delta_close_5": "higher",
        "gtja191_vp_corr_10": "higher",
        "gtja191_amount_momentum_5_10": "higher",
        "gtja191_intraday_strength_6": "higher",
        "qlib_klen": "lower",
        "qlib_kupper": "higher",
        "qlib_klower": "higher",
        "qlib_ret_5": "higher",
```

Do not add any of these columns to `weights`.

- [ ] **Step 4: Implement external row generation**

In `src/stock_research/factor_pipeline.py`, update imports:

```python
from stock_research.factors import alpha101, gtja191, momentum, qlib_alpha, risk, sector, trend, volume_price
```

Add:

```python
EXTERNAL_FACTOR_SOURCES = {
    "alpha101": (alpha101.compute_alpha101_factors, "alpha101"),
    "gtja191": (gtja191.compute_gtja191_factors, "gtja191"),
    "qlib": (qlib_alpha.compute_qlib_alpha_factors, "qlib"),
}
```

Add:

```python
def compute_external_factor_rows(
    bars: pd.DataFrame,
    trade_date: str,
    factor_groups: dict[str, str],
    calc_version: str,
    source_data_version: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if bars.empty:
        return pd.DataFrame(columns=FACTOR_DAILY_COLUMNS)

    normalized_trade_date = str(trade_date)[:10]
    external_groups = {
        source: {
            name: group
            for name, group in factor_groups.items()
            if group == source
        }
        for source in EXTERNAL_FACTOR_SOURCES
    }

    for group_name, (calculator, source) in EXTERNAL_FACTOR_SOURCES.items():
        names = external_groups[group_name]
        if not names:
            continue
        computed = calculator(bars)
        latest = computed[computed["trade_date"].astype(str).str[:10] == normalized_trade_date]
        for _, record in latest.iterrows():
            for factor_name, factor_group in names.items():
                if factor_name not in computed.columns:
                    continue
                value = record.get(factor_name)
                if pd.isna(value):
                    continue
                rows.append(
                    {
                        "trade_date": normalized_trade_date,
                        "asset_id": str(record["asset_id"]),
                        "factor_name": factor_name,
                        "factor_group": factor_group,
                        "factor_value": float(value),
                        "calc_version": calc_version,
                        "source": source,
                        "source_data_version": source_data_version,
                    }
                )
    return pd.DataFrame(rows, columns=FACTOR_DAILY_COLUMNS)
```

- [ ] **Step 5: Include external rows in daily build**

In `build_and_store_factor_daily()`, after `sector_factors = ...`, add:

```python
    external_factors = compute_external_factor_rows(
        bars,
        trade_date=trade_date,
        factor_groups=config["factor_groups"],
        calc_version=config["calc_version"],
        source_data_version=config["source_data_version"],
    )
```

Change concat to:

```python
    factors = pd.concat(
        [technical_factors, sector_factors, external_factors],
        ignore_index=True,
    )
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_pipeline.py tests/test_alpha101_factors.py tests/test_gtja191_factors.py tests/test_qlib_alpha_factors.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stock_research/factor_pipeline.py src/stock_research/factor_config.py tests/test_factor_pipeline.py
git commit -m "Integrate external reference factors into factor rows"
```

---

## Milestone 6: Real Build Smoke And Documentation

### Task 6: Verify External Factors Build But Do Not Enter Scoring Weights

**Files:**

- Modify: `docs/astock-research-platform-v1.md`
- Modify: `docs/daily-factor-pipeline-runbook.md`

- [ ] **Step 1: Run full tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Apply schema**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research apply-research-schema
```

Expected:

```text
research_schema_applied
```

- [ ] **Step 3: Build factors for a known loaded date**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research build-factor-daily --trade-date 2026-05-08 --lookback-bars 130
```

Expected:

```text
factor_daily_stored|<positive integer greater than 98029>
```

- [ ] **Step 4: Verify source counts**

Run:

```bash
psql service=stock_research -Atc "SELECT source || '|' || count(*) FROM factor.factor_daily WHERE trade_date = '2026-05-08' GROUP BY source ORDER BY source;"
```

Expected output includes:

```text
alpha101|<positive integer>
custom|<positive integer>
gtja191|<positive integer>
qlib|<positive integer>
```

- [ ] **Step 5: Verify external factors are not scoring weights**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python - <<'PY'
from stock_research.factor_config import manual_v1_config

config = manual_v1_config()
external = [name for name in config["weights"] if name.startswith(("alpha101_", "gtja191_", "qlib_"))]
print(external)
PY
```

Expected:

```text
[]
```

- [ ] **Step 6: Update docs**

In `docs/astock-research-platform-v1.md`, under phase 3 current progress, add:

```markdown
- 已落地第一批外部参考因子：Alpha101-style、GTJA191-style、Qlib-style 代表性 pandas 实现。
- 外部参考因子已进入 `factor.factor_daily`，但进入 `factor.stock_score_daily` 前仍需通过 `factor_eval` 评价门禁。
```

In `docs/daily-factor-pipeline-runbook.md`, under Guardrails, add:

```markdown
- Alpha101 / GTJA191 / Qlib-style factors are research candidates until factor evaluation approves them for scoring.
```

- [ ] **Step 7: Run final tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 8: Commit and push**

```bash
git add docs/astock-research-platform-v1.md docs/daily-factor-pipeline-runbook.md
git commit -m "Document external reference factor phase one"
git push
```

---

## Acceptance Criteria

- `tests/test_external_factor_operators.py` passes.
- `tests/test_alpha101_factors.py` passes.
- `tests/test_gtja191_factors.py` passes.
- `tests/test_qlib_alpha_factors.py` passes.
- Full test suite passes.
- Real build for `2026-05-08` writes `alpha101`, `gtja191`, `qlib`, and `custom` source rows to `factor.factor_daily`.
- `manual_v1_config()["weights"]` contains no external-reference factor score columns.
- No large external framework is added as a dependency.
- No V3 strategy thresholds or backtest rules are changed.

## Self-Review

Spec coverage:

- External factor operators: Task 1.
- Alpha101 representative factors: Task 2.
- GTJA191 representative factors: Task 3.
- Qlib-style representative factors: Task 4.
- Pipeline long-row integration and source labels: Task 5.
- Real build, no scoring promotion, documentation: Task 6.

Placeholder scan:

- No TBD or TODO placeholders remain.

Type consistency:

- Factor calculators accept `pd.DataFrame` and return `pd.DataFrame`.
- Long rows use `FACTOR_DAILY_COLUMNS`.
- Source labels are exactly `alpha101`, `gtja191`, and `qlib`.
