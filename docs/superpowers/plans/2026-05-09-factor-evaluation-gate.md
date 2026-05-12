# Factor Evaluation Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a formal factor evaluation gate so candidate factors can be evaluated across multiple horizons, summarized with exposure and segment diagnostics, and recorded as approved or rejected before any scoring promotion.

**Architecture:** Extend the existing Alphalens-style `factor_eval/` modules rather than importing Alphalens. Keep evaluation computation in pure pandas modules, persistence in `factor_eval_store.py` and `schema.py`, and operator access in `cli.py`. This plan records approval metadata only; it does not change `manual_v1` scoring weights.

**Tech Stack:** Python 3.11+, pandas, pytest, PostgreSQL, existing `stock_research` CLI, Git.

---

## Current Baseline

Already implemented:

- `factor_eval.ic`: IC, RankIC, ICIR summary.
- `factor_eval.quantile_return`: quantile returns and Top-Bottom spread.
- `factor_eval.turnover`: TopN turnover.
- `factor_eval.report`: one-horizon report wrapper.
- `factor_eval_store.load_factor_eval_inputs`: one-horizon DB loader.
- `labels.compute_labels_for_asset`: currently supports horizons 5, 20, 60.
- `eval-factor` CLI: prints one-horizon IC summary.

Missing:

- `forward_return_10d`.
- multi-horizon evaluation wrapper for 5/10/20/60.
- by-year IC and Top-Bottom summaries.
- generic segment performance, usable for market-state labels later.
- industry and size exposure diagnostics.
- factor evaluation persistence and approval metadata.
- CLI gate command that evaluates thresholds and records approved/rejected state.

## Usage Boundaries

- Do not import Alphalens as a dependency.
- Do not promote any factor into `manual_v1` weights in this plan.
- Do not change V3 strategy thresholds.
- Do not produce buy/sell recommendations.
- Do not use future data in factor values; forward returns may use future prices only in label generation.

## File Map

Modify:

- `src/stock_research/labels.py`: add 10-day labels.
- `src/stock_research/schema.py`: add `factor.factor_eval_run` and `factor.factor_approval`.
- `src/stock_research/factor_eval_store.py`: add multi-horizon loaders and persistence helpers.
- `src/stock_research/cli.py`: add `evaluate-factor-gate` command.
- `src/stock_research/factor_eval/__init__.py`: export new modules.
- `docs/astock-research-platform-v1.md`: update progress.
- `docs/daily-factor-pipeline-runbook.md`: document gate command.

Create:

- `src/stock_research/factor_eval/multi_horizon.py`
- `src/stock_research/factor_eval/period.py`
- `src/stock_research/factor_eval/segment.py`
- `src/stock_research/factor_eval/exposure.py`
- `src/stock_research/factor_eval/gate.py`
- `tests/test_factor_eval_multi_horizon.py`
- `tests/test_factor_eval_period_segment.py`
- `tests/test_factor_eval_exposure.py`
- `tests/test_factor_eval_gate.py`

Modify tests:

- `tests/test_labels.py`
- `tests/test_schema.py`
- `tests/test_factor_eval_store.py`
- `tests/test_factor_cli.py`

---

## Milestone 1: Add 10-Day Forward Return Labels

### Task 1: Add 10-Day Label Horizon

**Files:**

- Modify: `src/stock_research/labels.py`
- Modify: `tests/test_labels.py`

- [ ] **Step 1: Write failing label horizon test**

Append to `tests/test_labels.py`:

```python
def test_compute_labels_for_asset_includes_10_day_horizon():
    bars = pd.DataFrame(
        {
            "trade_date": pd.date_range("2026-01-01", periods=70, freq="D"),
            "close": [float(i) for i in range(1, 71)],
        }
    )

    labels = compute_labels_for_asset("CN:SH:600000", bars)

    sample = labels[
        (labels["trade_date"] == "2026-01-01")
        & (labels["horizon"] == 10)
        & (labels["label_name"] == "future_return")
    ]
    assert round(float(sample.iloc[0]["label_value"]), 6) == 10.0
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_labels.py::test_compute_labels_for_asset_includes_10_day_horizon -q
```

Expected: FAIL because horizon 10 is not generated.

- [ ] **Step 3: Add 10-day horizon**

In `src/stock_research/labels.py`, change:

```python
HORIZONS = [5, 20, 60]
```

to:

```python
HORIZONS = [5, 10, 20, 60]
```

Update `test_compute_labels_for_asset_includes_supported_horizons_when_available` in `tests/test_labels.py`:

```python
assert set(labels["horizon"]) == {5, 10, 20, 60}
```

- [ ] **Step 4: Run label tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_labels.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/labels.py tests/test_labels.py
git commit -m "Add 10-day forward return labels"
```

---

## Milestone 2: Multi-Horizon Evaluation Reports

### Task 2: Add Multi-Horizon Evaluation Wrapper

**Files:**

- Create: `src/stock_research/factor_eval/multi_horizon.py`
- Modify: `src/stock_research/factor_eval/__init__.py`
- Create: `tests/test_factor_eval_multi_horizon.py`

- [ ] **Step 1: Write failing multi-horizon tests**

Create `tests/test_factor_eval_multi_horizon.py`:

```python
import pandas as pd
import pytest

from stock_research.factor_eval.multi_horizon import generate_multi_horizon_report


def test_generate_multi_horizon_report_runs_each_return_column():
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 2.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "factor_value": 3.0},
            {"trade_date": "2026-01-01", "asset_id": "D", "factor_value": 4.0},
            {"trade_date": "2026-01-02", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-02", "asset_id": "B", "factor_value": 2.0},
            {"trade_date": "2026-01-02", "asset_id": "C", "factor_value": 3.0},
            {"trade_date": "2026-01-02", "asset_id": "D", "factor_value": 4.0},
        ]
    )
    returns = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "forward_return_5d": 0.01, "forward_return_10d": 0.02},
            {"trade_date": "2026-01-01", "asset_id": "B", "forward_return_5d": 0.02, "forward_return_10d": 0.03},
            {"trade_date": "2026-01-01", "asset_id": "C", "forward_return_5d": 0.03, "forward_return_10d": 0.04},
            {"trade_date": "2026-01-01", "asset_id": "D", "forward_return_5d": 0.04, "forward_return_10d": 0.05},
            {"trade_date": "2026-01-02", "asset_id": "A", "forward_return_5d": 0.01, "forward_return_10d": 0.02},
            {"trade_date": "2026-01-02", "asset_id": "B", "forward_return_5d": 0.02, "forward_return_10d": 0.03},
            {"trade_date": "2026-01-02", "asset_id": "C", "forward_return_5d": 0.03, "forward_return_10d": 0.04},
            {"trade_date": "2026-01-02", "asset_id": "D", "forward_return_5d": 0.04, "forward_return_10d": 0.05},
        ]
    )

    result = generate_multi_horizon_report(
        factors,
        returns,
        factor_name="demo_factor",
        horizons=[5, 10],
        quantiles=2,
        top_n=2,
    )

    assert set(result["horizons"]) == {5, 10}
    assert result["reports"][5]["ic_summary"]["mean_ic"] == pytest.approx(1.0)
    assert result["reports"][10]["return_col"] == "forward_return_10d"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_eval_multi_horizon.py -q
```

Expected: FAIL because `factor_eval.multi_horizon` does not exist.

- [ ] **Step 3: Implement multi-horizon wrapper**

Create `src/stock_research/factor_eval/multi_horizon.py`:

```python
from __future__ import annotations

from typing import Any

import pandas as pd

from stock_research.factor_eval.report import generate_factor_eval_report


def generate_multi_horizon_report(
    factors: pd.DataFrame,
    returns: pd.DataFrame,
    factor_name: str,
    horizons: list[int],
    factor_col: str = "factor_value",
    quantiles: int = 5,
    top_n: int = 20,
) -> dict[str, Any]:
    reports = {}
    for horizon in horizons:
        return_col = f"forward_return_{horizon}d"
        reports[horizon] = generate_factor_eval_report(
            factors,
            returns,
            factor_name=factor_name,
            factor_col=factor_col,
            return_col=return_col,
            quantiles=quantiles,
            top_n=top_n,
        )
    return {"factor_name": factor_name, "horizons": list(horizons), "reports": reports}
```

In `src/stock_research/factor_eval/__init__.py`, change:

```python
from stock_research.factor_eval import ic, quantile_return, report, turnover

__all__ = ["ic", "quantile_return", "report", "turnover"]
```

to:

```python
from stock_research.factor_eval import ic, multi_horizon, quantile_return, report, turnover

__all__ = ["ic", "multi_horizon", "quantile_return", "report", "turnover"]
```

- [ ] **Step 4: Run multi-horizon tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_eval_multi_horizon.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/factor_eval/__init__.py src/stock_research/factor_eval/multi_horizon.py tests/test_factor_eval_multi_horizon.py
git commit -m "Add multi-horizon factor evaluation"
```

---

## Milestone 3: Period And Segment Diagnostics

### Task 3: Add By-Year And Segment Summaries

**Files:**

- Create: `src/stock_research/factor_eval/period.py`
- Create: `src/stock_research/factor_eval/segment.py`
- Create: `tests/test_factor_eval_period_segment.py`

- [ ] **Step 1: Write failing period and segment tests**

Create `tests/test_factor_eval_period_segment.py`:

```python
import pandas as pd
import pytest

from stock_research.factor_eval.period import summarize_ic_by_year, summarize_spread_by_year
from stock_research.factor_eval.segment import summarize_return_by_segment


def test_summarize_ic_by_year_groups_ic_values():
    ic_frame = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "ic": 0.1},
            {"trade_date": "2025-01-02", "ic": 0.3},
            {"trade_date": "2026-01-01", "ic": -0.2},
        ]
    )

    result = summarize_ic_by_year(ic_frame, ic_col="ic")

    assert result.to_dict("records") == [
        {"year": 2025, "mean_ic": 0.2, "ic_count": 2},
        {"year": 2026, "mean_ic": -0.2, "ic_count": 1},
    ]


def test_summarize_spread_by_year_groups_top_bottom_spread():
    spread = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "top_bottom_spread": 0.05},
            {"trade_date": "2025-01-02", "top_bottom_spread": 0.03},
            {"trade_date": "2026-01-01", "top_bottom_spread": -0.01},
        ]
    )

    result = summarize_spread_by_year(spread)

    assert result.set_index("year").loc[2025, "mean_top_bottom_spread"] == pytest.approx(0.04)
    assert result.set_index("year").loc[2026, "spread_count"] == 1


def test_summarize_return_by_segment_joins_segment_labels():
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 2.0},
        ]
    )
    returns = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "forward_return_5d": 0.01},
            {"trade_date": "2026-01-01", "asset_id": "B", "forward_return_5d": 0.03},
        ]
    )
    segments = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "market_state": "weak"},
            {"trade_date": "2026-01-01", "asset_id": "B", "market_state": "strong"},
        ]
    )

    result = summarize_return_by_segment(
        factors,
        returns,
        segments,
        segment_col="market_state",
        return_col="forward_return_5d",
    )

    assert result.set_index("market_state").loc["strong", "mean_return"] == pytest.approx(0.03)
    assert result.set_index("market_state").loc["weak", "count"] == 1
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_eval_period_segment.py -q
```

Expected: FAIL because modules do not exist.

- [ ] **Step 3: Implement period summaries**

Create `src/stock_research/factor_eval/period.py`:

```python
from __future__ import annotations

import pandas as pd


def summarize_ic_by_year(ic_frame: pd.DataFrame, ic_col: str = "ic") -> pd.DataFrame:
    if ic_frame.empty:
        return pd.DataFrame(columns=["year", "mean_ic", "ic_count"])
    frame = ic_frame.copy()
    frame["year"] = pd.to_datetime(frame["trade_date"]).dt.year
    frame[ic_col] = pd.to_numeric(frame[ic_col], errors="coerce")
    result = (
        frame.dropna(subset=[ic_col])
        .groupby("year", as_index=False)[ic_col]
        .agg(mean_ic="mean", ic_count="count")
        .sort_values("year")
        .reset_index(drop=True)
    )
    result["ic_count"] = result["ic_count"].astype(int)
    return result


def summarize_spread_by_year(spread_frame: pd.DataFrame) -> pd.DataFrame:
    if spread_frame.empty:
        return pd.DataFrame(columns=["year", "mean_top_bottom_spread", "spread_count"])
    frame = spread_frame.copy()
    frame["year"] = pd.to_datetime(frame["trade_date"]).dt.year
    frame["top_bottom_spread"] = pd.to_numeric(frame["top_bottom_spread"], errors="coerce")
    result = (
        frame.dropna(subset=["top_bottom_spread"])
        .groupby("year", as_index=False)["top_bottom_spread"]
        .agg(mean_top_bottom_spread="mean", spread_count="count")
        .sort_values("year")
        .reset_index(drop=True)
    )
    result["spread_count"] = result["spread_count"].astype(int)
    return result
```

- [ ] **Step 4: Implement segment summary**

Create `src/stock_research/factor_eval/segment.py`:

```python
from __future__ import annotations

import pandas as pd

from stock_research.factor_eval.base import KEY_COLUMNS, merged_factor_returns, normalize_keys


def summarize_return_by_segment(
    factors: pd.DataFrame,
    returns: pd.DataFrame,
    segments: pd.DataFrame,
    segment_col: str,
    factor_col: str = "factor_value",
    return_col: str = "forward_return_5d",
) -> pd.DataFrame:
    merged = merged_factor_returns(factors, returns, factor_col, return_col)
    segment_frame = normalize_keys(segments)
    joined = merged.merge(segment_frame[KEY_COLUMNS + [segment_col]], on=KEY_COLUMNS, how="inner")
    if joined.empty:
        return pd.DataFrame(columns=[segment_col, "mean_return", "count"])
    result = (
        joined.groupby(segment_col, as_index=False)[return_col]
        .agg(mean_return="mean", count="count")
        .sort_values(segment_col)
        .reset_index(drop=True)
    )
    result["count"] = result["count"].astype(int)
    return result
```

- [ ] **Step 5: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_eval_period_segment.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/factor_eval/period.py src/stock_research/factor_eval/segment.py tests/test_factor_eval_period_segment.py
git commit -m "Add factor period and segment diagnostics"
```

---

## Milestone 4: Industry And Size Exposure

### Task 4: Add Exposure Diagnostics

**Files:**

- Create: `src/stock_research/factor_eval/exposure.py`
- Create: `tests/test_factor_eval_exposure.py`

- [ ] **Step 1: Write failing exposure tests**

Create `tests/test_factor_eval_exposure.py`:

```python
import pandas as pd
import pytest

from stock_research.factor_eval.exposure import calc_group_exposure, calc_size_exposure


def test_calc_group_exposure_returns_factor_mean_by_industry():
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 3.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "factor_value": 5.0},
        ]
    )
    groups = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "industry_code": "I1"},
            {"trade_date": "2026-01-01", "asset_id": "B", "industry_code": "I1"},
            {"trade_date": "2026-01-01", "asset_id": "C", "industry_code": "I2"},
        ]
    )

    result = calc_group_exposure(factors, groups, group_col="industry_code")

    assert result.set_index("industry_code").loc["I1", "mean_factor"] == pytest.approx(2.0)
    assert result.set_index("industry_code").loc["I2", "count"] == 1


def test_calc_size_exposure_correlates_factor_with_log_market_cap_by_date():
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_value": 2.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "factor_value": 3.0},
        ]
    )
    size = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "market_cap": 100.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "market_cap": 200.0},
            {"trade_date": "2026-01-01", "asset_id": "C", "market_cap": 300.0},
        ]
    )

    result = calc_size_exposure(factors, size)

    assert result.iloc[0]["trade_date"] == "2026-01-01"
    assert result.iloc[0]["size_corr"] > 0.9
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_eval_exposure.py -q
```

Expected: FAIL because exposure module does not exist.

- [ ] **Step 3: Implement exposure diagnostics**

Create `src/stock_research/factor_eval/exposure.py`:

```python
from __future__ import annotations

import numpy as np
import pandas as pd

from stock_research.factor_eval.base import KEY_COLUMNS, normalize_keys


def calc_group_exposure(
    factors: pd.DataFrame,
    groups: pd.DataFrame,
    group_col: str,
    factor_col: str = "factor_value",
) -> pd.DataFrame:
    factor_frame = normalize_keys(factors)
    group_frame = normalize_keys(groups)
    joined = factor_frame[KEY_COLUMNS + [factor_col]].merge(
        group_frame[KEY_COLUMNS + [group_col]],
        on=KEY_COLUMNS,
        how="inner",
    )
    if joined.empty:
        return pd.DataFrame(columns=[group_col, "mean_factor", "count"])
    joined[factor_col] = pd.to_numeric(joined[factor_col], errors="coerce")
    result = (
        joined.dropna(subset=[factor_col, group_col])
        .groupby(group_col, as_index=False)[factor_col]
        .agg(mean_factor="mean", count="count")
        .sort_values(group_col)
        .reset_index(drop=True)
    )
    result["count"] = result["count"].astype(int)
    return result


def calc_size_exposure(
    factors: pd.DataFrame,
    size: pd.DataFrame,
    factor_col: str = "factor_value",
    size_col: str = "market_cap",
) -> pd.DataFrame:
    factor_frame = normalize_keys(factors)
    size_frame = normalize_keys(size)
    joined = factor_frame[KEY_COLUMNS + [factor_col]].merge(
        size_frame[KEY_COLUMNS + [size_col]],
        on=KEY_COLUMNS,
        how="inner",
    )
    if joined.empty:
        return pd.DataFrame(columns=["trade_date", "size_corr", "n"])
    joined[factor_col] = pd.to_numeric(joined[factor_col], errors="coerce")
    joined[size_col] = pd.to_numeric(joined[size_col], errors="coerce")
    joined = joined.dropna(subset=[factor_col, size_col])
    joined = joined[joined[size_col] > 0].copy()
    joined["log_size"] = np.log(joined[size_col])
    rows = []
    for trade_date, group in joined.groupby("trade_date", sort=True):
        if len(group) < 2 or group[factor_col].nunique() < 2 or group["log_size"].nunique() < 2:
            corr = None
        else:
            corr = float(group[factor_col].corr(group["log_size"]))
        rows.append({"trade_date": trade_date, "size_corr": corr, "n": int(len(group))})
    return pd.DataFrame(rows, columns=["trade_date", "size_corr", "n"])
```

- [ ] **Step 4: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_eval_exposure.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/factor_eval/exposure.py tests/test_factor_eval_exposure.py
git commit -m "Add factor exposure diagnostics"
```

---

## Milestone 5: Evaluation Gate Logic

### Task 5: Add Gate Decision Logic

**Files:**

- Create: `src/stock_research/factor_eval/gate.py`
- Create: `tests/test_factor_eval_gate.py`

- [ ] **Step 1: Write failing gate tests**

Create `tests/test_factor_eval_gate.py`:

```python
from stock_research.factor_eval.gate import decide_factor_gate


def test_decide_factor_gate_approves_when_primary_horizon_passes_thresholds():
    report = {
        "reports": {
            5: {"ic_summary": {"mean_ic": 0.04, "icir": 0.6, "ic_count": 30}},
            10: {"ic_summary": {"mean_ic": 0.03, "icir": 0.5, "ic_count": 30}},
        }
    }

    result = decide_factor_gate(
        factor_name="alpha101_demo",
        multi_horizon_report=report,
        primary_horizon=5,
        min_abs_mean_ic=0.02,
        min_icir=0.3,
        min_ic_count=20,
    )

    assert result["status"] == "approved"
    assert result["reason"] == "passed_thresholds"


def test_decide_factor_gate_rejects_low_sample_count():
    report = {"reports": {5: {"ic_summary": {"mean_ic": 0.04, "icir": 0.6, "ic_count": 3}}}}

    result = decide_factor_gate("alpha101_demo", report, min_ic_count=20)

    assert result["status"] == "rejected"
    assert result["reason"] == "insufficient_ic_count"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_eval_gate.py -q
```

Expected: FAIL because gate module does not exist.

- [ ] **Step 3: Implement gate decision logic**

Create `src/stock_research/factor_eval/gate.py`:

```python
from __future__ import annotations

from typing import Any


def decide_factor_gate(
    factor_name: str,
    multi_horizon_report: dict[str, Any],
    primary_horizon: int = 5,
    min_abs_mean_ic: float = 0.02,
    min_icir: float = 0.3,
    min_ic_count: int = 20,
) -> dict[str, Any]:
    reports = multi_horizon_report.get("reports", {})
    primary = reports.get(primary_horizon)
    if primary is None:
        return {
            "factor_name": factor_name,
            "status": "rejected",
            "reason": "missing_primary_horizon",
            "primary_horizon": primary_horizon,
        }

    summary = primary.get("ic_summary", {})
    mean_ic = summary.get("mean_ic")
    icir = summary.get("icir")
    ic_count = int(summary.get("ic_count") or 0)
    if ic_count < min_ic_count:
        reason = "insufficient_ic_count"
        status = "rejected"
    elif mean_ic is None or abs(float(mean_ic)) < min_abs_mean_ic:
        reason = "mean_ic_below_threshold"
        status = "rejected"
    elif icir is None or abs(float(icir)) < min_icir:
        reason = "icir_below_threshold"
        status = "rejected"
    else:
        reason = "passed_thresholds"
        status = "approved"
    return {
        "factor_name": factor_name,
        "status": status,
        "reason": reason,
        "primary_horizon": primary_horizon,
        "mean_ic": mean_ic,
        "icir": icir,
        "ic_count": ic_count,
        "thresholds": {
            "min_abs_mean_ic": min_abs_mean_ic,
            "min_icir": min_icir,
            "min_ic_count": min_ic_count,
        },
    }
```

- [ ] **Step 4: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_eval_gate.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/factor_eval/gate.py tests/test_factor_eval_gate.py
git commit -m "Add factor evaluation gate decisions"
```

---

## Milestone 6: Schema And Store Persistence

### Task 6: Add Factor Evaluation Persistence

**Files:**

- Modify: `src/stock_research/schema.py`
- Modify: `src/stock_research/factor_eval_store.py`
- Modify: `tests/test_schema.py`
- Modify: `tests/test_factor_eval_store.py`

- [ ] **Step 1: Write failing schema test**

Append to `tests/test_schema.py`:

```python
def test_research_extension_includes_factor_eval_gate_tables():
    from stock_research.schema import CREATE_RESEARCH_EXTENSION_SQL

    assert "CREATE TABLE IF NOT EXISTS factor.factor_eval_run" in CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS factor.factor_approval" in CREATE_RESEARCH_EXTENSION_SQL
    assert "idx_factor_eval_run_factor" in CREATE_RESEARCH_EXTENSION_SQL
```

- [ ] **Step 2: Run schema test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_schema.py::test_research_extension_includes_factor_eval_gate_tables -q
```

Expected: FAIL because the tables are missing.

- [ ] **Step 3: Add schema tables**

In `src/stock_research/schema.py`, inside `CREATE_RESEARCH_EXTENSION_SQL` after `factor.stock_score_daily`, add:

```sql
CREATE TABLE IF NOT EXISTS factor.factor_eval_run (
    run_id text PRIMARY KEY,
    factor_name text NOT NULL,
    calc_version text NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    horizons integer[] NOT NULL,
    primary_horizon integer NOT NULL,
    status text NOT NULL,
    reason text NOT NULL,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS factor.factor_approval (
    factor_name text NOT NULL,
    calc_version text NOT NULL,
    score_version text NOT NULL,
    status text NOT NULL,
    reason text NOT NULL,
    eval_run_id text NOT NULL REFERENCES factor.factor_eval_run(run_id),
    approved_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (factor_name, calc_version, score_version)
);
```

Near the factor indexes, add:

```sql
CREATE INDEX IF NOT EXISTS idx_factor_eval_run_factor
    ON factor.factor_eval_run (factor_name, calc_version, created_at DESC);
```

- [ ] **Step 4: Write failing store tests**

Append to `tests/test_factor_eval_store.py`:

```python
def test_store_factor_eval_run_writes_metrics_json(monkeypatch):
    calls = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params):
            calls.append((sql, params))

    class Conn:
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(factor_eval_store, "connect", lambda service: _context(Conn()))

    factor_eval_store.store_factor_eval_run(
        run_id="run-1",
        factor_name="ret_20",
        calc_version="v1",
        start_date="2026-01-01",
        end_date="2026-02-01",
        horizons=[5, 10],
        primary_horizon=5,
        status="approved",
        reason="passed_thresholds",
        metrics={"mean_ic": 0.03},
    )

    assert "INSERT INTO factor.factor_eval_run" in calls[0][0]
    assert calls[0][1]["metrics"] == '{"mean_ic": 0.03}'


def test_store_factor_approval_upserts_status(monkeypatch):
    calls = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params):
            calls.append((sql, params))

    class Conn:
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(factor_eval_store, "connect", lambda service: _context(Conn()))

    factor_eval_store.store_factor_approval(
        factor_name="ret_20",
        calc_version="v1",
        score_version="manual_v1",
        status="approved",
        reason="passed_thresholds",
        eval_run_id="run-1",
    )

    assert "INSERT INTO factor.factor_approval" in calls[0][0]
    assert calls[0][1]["score_version"] == "manual_v1"
```

- [ ] **Step 5: Implement store helpers**

In `src/stock_research/factor_eval_store.py`, add imports:

```python
import json
from typing import Any
```

Append:

```python
def store_factor_eval_run(
    run_id: str,
    factor_name: str,
    calc_version: str,
    start_date: str,
    end_date: str,
    horizons: list[int],
    primary_horizon: int,
    status: str,
    reason: str,
    metrics: dict[str, Any],
    service: str = SETTINGS.research_service,
) -> None:
    sql = """
    INSERT INTO factor.factor_eval_run (
        run_id, factor_name, calc_version, start_date, end_date, horizons,
        primary_horizon, status, reason, metrics
    )
    VALUES (
        %(run_id)s, %(factor_name)s, %(calc_version)s, %(start_date)s, %(end_date)s,
        %(horizons)s, %(primary_horizon)s, %(status)s, %(reason)s, %(metrics)s::jsonb
    )
    ON CONFLICT (run_id) DO UPDATE SET
        status = EXCLUDED.status,
        reason = EXCLUDED.reason,
        metrics = EXCLUDED.metrics
    """
    params = {
        "run_id": run_id,
        "factor_name": factor_name,
        "calc_version": calc_version,
        "start_date": start_date,
        "end_date": end_date,
        "horizons": horizons,
        "primary_horizon": primary_horizon,
        "status": status,
        "reason": reason,
        "metrics": json.dumps(metrics, ensure_ascii=False),
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)


def store_factor_approval(
    factor_name: str,
    calc_version: str,
    score_version: str,
    status: str,
    reason: str,
    eval_run_id: str,
    service: str = SETTINGS.research_service,
) -> None:
    sql = """
    INSERT INTO factor.factor_approval (
        factor_name, calc_version, score_version, status, reason, eval_run_id
    )
    VALUES (
        %(factor_name)s, %(calc_version)s, %(score_version)s, %(status)s,
        %(reason)s, %(eval_run_id)s
    )
    ON CONFLICT (factor_name, calc_version, score_version)
    DO UPDATE SET
        status = EXCLUDED.status,
        reason = EXCLUDED.reason,
        eval_run_id = EXCLUDED.eval_run_id,
        approved_at = now()
    """
    params = {
        "factor_name": factor_name,
        "calc_version": calc_version,
        "score_version": score_version,
        "status": status,
        "reason": reason,
        "eval_run_id": eval_run_id,
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
```

- [ ] **Step 6: Run focused persistence tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_schema.py::test_research_extension_includes_factor_eval_gate_tables tests/test_factor_eval_store.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stock_research/schema.py src/stock_research/factor_eval_store.py tests/test_schema.py tests/test_factor_eval_store.py
git commit -m "Add factor evaluation gate persistence"
```

---

## Milestone 7: CLI Gate Command

### Task 7: Add `evaluate-factor-gate` CLI

**Files:**

- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/factor_eval_store.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing parser test**

Append to `tests/test_factor_cli.py`:

```python
def test_cli_accepts_evaluate_factor_gate_command():
    args = build_parser().parse_args(
        [
            "evaluate-factor-gate",
            "--factor-name",
            "alpha101_delta_close_1_rank",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
            "--horizons",
            "5,10,20,60",
            "--primary-horizon",
            "5",
            "--score-version",
            "manual_v1",
        ]
    )

    assert args.command == "evaluate-factor-gate"
    assert args.factor_name == "alpha101_delta_close_1_rank"
    assert args.horizons == "5,10,20,60"
    assert args.primary_horizon == 5
```

- [ ] **Step 2: Run parser test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_cli.py::test_cli_accepts_evaluate_factor_gate_command -q
```

Expected: FAIL because the command is missing.

- [ ] **Step 3: Add multi-horizon DB loader**

Append to `src/stock_research/factor_eval_store.py`:

```python
def load_multi_horizon_factor_eval_inputs(
    factor_name: str,
    start_date: str,
    end_date: str,
    horizons: list[int],
    calc_version: str = "v1",
    label_set: str = "forward_return",
    label_version: str = "v1",
    service: str = SETTINGS.research_service,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    factor_sql = """
    SELECT trade_date, asset_id, factor_value
    FROM factor.factor_daily
    WHERE factor_name = %s
      AND calc_version = %s
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id
    """
    return_sql = """
    SELECT trade_date, asset_id, horizon, label_value
    FROM label_snapshot
    WHERE label_set = %s
      AND label_version = %s
      AND horizon = ANY(%s)
      AND label_name IN ('forward_return', 'future_return')
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id, horizon
    """
    with connect(service) as conn:
        factor_rows = fetch_all(conn, factor_sql, [factor_name, calc_version, start_date, end_date])
        return_rows = fetch_all(conn, return_sql, [label_set, label_version, horizons, start_date, end_date])
    factors = pd.DataFrame(factor_rows)
    raw_returns = pd.DataFrame(return_rows)
    if raw_returns.empty:
        return factors, pd.DataFrame(columns=["trade_date", "asset_id"] + [f"forward_return_{horizon}d" for horizon in horizons])
    returns = raw_returns.pivot_table(
        index=["trade_date", "asset_id"],
        columns="horizon",
        values="label_value",
        aggfunc="last",
    ).reset_index()
    returns.columns = [
        f"forward_return_{column}d" if isinstance(column, int) else column
        for column in returns.columns
    ]
    return factors, returns
```

- [ ] **Step 4: Add CLI dispatch test**

Append to `tests/test_factor_cli.py`:

```python
def test_evaluate_factor_gate_cli_prints_and_stores_status(monkeypatch, capsys):
    import sys

    import pandas as pd

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "load_multi_horizon_factor_eval_inputs",
        lambda **kwargs: (
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "factor_value": [1.0]}),
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "forward_return_5d": [0.01]}),
        ),
    )
    monkeypatch.setattr(
        cli,
        "generate_multi_horizon_report",
        lambda **kwargs: {"factor_name": "ret_20", "horizons": [5], "reports": {5: {"ic_summary": {"mean_ic": 0.04, "icir": 0.6, "ic_count": 30}}}},
    )
    monkeypatch.setattr(
        cli,
        "decide_factor_gate",
        lambda **kwargs: {"factor_name": kwargs["factor_name"], "status": "approved", "reason": "passed_thresholds", "primary_horizon": 5},
    )
    monkeypatch.setattr(cli, "store_factor_eval_run", lambda **kwargs: calls.append(("run", kwargs)))
    monkeypatch.setattr(cli, "store_factor_approval", lambda **kwargs: calls.append(("approval", kwargs)))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "evaluate-factor-gate",
            "--factor-name",
            "ret_20",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-02-01",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "factor_gate|ret_20|approved|passed_thresholds|5"
    assert [kind for kind, _ in calls] == ["run", "approval"]
```

- [ ] **Step 5: Implement CLI imports, parser, and dispatch**

In `src/stock_research/cli.py`, add imports:

```python
from uuid import uuid4

from stock_research.factor_eval.gate import decide_factor_gate
from stock_research.factor_eval.multi_horizon import generate_multi_horizon_report
from stock_research.factor_eval_store import (
    load_factor_eval_inputs,
    load_multi_horizon_factor_eval_inputs,
    store_factor_approval,
    store_factor_eval_run,
)
```

Keep the existing `load_factor_eval_inputs` import in this grouped import and remove any duplicate single-line import.

In `build_parser()`, add:

```python
    evaluate_factor_gate = subparsers.add_parser("evaluate-factor-gate")
    evaluate_factor_gate.add_argument("--factor-name", required=True)
    evaluate_factor_gate.add_argument("--start-date", required=True)
    evaluate_factor_gate.add_argument("--end-date", required=True)
    evaluate_factor_gate.add_argument("--horizons", default="5,10,20,60")
    evaluate_factor_gate.add_argument("--primary-horizon", type=int, default=5)
    evaluate_factor_gate.add_argument("--score-version", default="manual_v1")
    evaluate_factor_gate.add_argument("--calc-version", default="v1")
    evaluate_factor_gate.add_argument("--min-abs-mean-ic", type=float, default=0.02)
    evaluate_factor_gate.add_argument("--min-icir", type=float, default=0.3)
    evaluate_factor_gate.add_argument("--min-ic-count", type=int, default=20)
```

In `main()`, add before `run-daily-factor-pipeline`:

```python
    elif args.command == "evaluate-factor-gate":
        horizons = [int(value) for value in args.horizons.split(",") if value.strip()]
        factors, returns = load_multi_horizon_factor_eval_inputs(
            factor_name=args.factor_name,
            start_date=args.start_date,
            end_date=args.end_date,
            horizons=horizons,
            calc_version=args.calc_version,
        )
        multi_report = generate_multi_horizon_report(
            factors=factors,
            returns=returns,
            factor_name=args.factor_name,
            horizons=horizons,
        )
        decision = decide_factor_gate(
            factor_name=args.factor_name,
            multi_horizon_report=multi_report,
            primary_horizon=args.primary_horizon,
            min_abs_mean_ic=args.min_abs_mean_ic,
            min_icir=args.min_icir,
            min_ic_count=args.min_ic_count,
        )
        run_id = f"factor-eval-{uuid4().hex}"
        store_factor_eval_run(
            run_id=run_id,
            factor_name=args.factor_name,
            calc_version=args.calc_version,
            start_date=args.start_date,
            end_date=args.end_date,
            horizons=horizons,
            primary_horizon=args.primary_horizon,
            status=decision["status"],
            reason=decision["reason"],
            metrics={"decision": decision, "multi_horizon": multi_report},
        )
        store_factor_approval(
            factor_name=args.factor_name,
            calc_version=args.calc_version,
            score_version=args.score_version,
            status=decision["status"],
            reason=decision["reason"],
            eval_run_id=run_id,
        )
        print(
            f"factor_gate|{args.factor_name}|{decision['status']}|"
            f"{decision['reason']}|{decision['primary_horizon']}"
        )
```

- [ ] **Step 6: Run CLI and store tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_cli.py tests/test_factor_eval_store.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stock_research/cli.py src/stock_research/factor_eval_store.py tests/test_factor_cli.py
git commit -m "Add factor evaluation gate command"
```

---

## Milestone 8: Real Gate Smoke And Documentation

### Task 8: Apply Schema And Run Gate Smoke

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

- [ ] **Step 3: Ensure labels include 10-day horizon**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research labels --end-date 2026-05-08
```

Expected:

```text
labels_stored|<positive integer>
```

- [ ] **Step 4: Run factor gate smoke**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research evaluate-factor-gate --factor-name alpha101_delta_close_1_rank --start-date 2026-01-01 --end-date 2026-05-08 --horizons 5,10,20,60 --primary-horizon 5 --score-version manual_v1
```

Expected:

```text
factor_gate|alpha101_delta_close_1_rank|approved|passed_thresholds|5
```

or:

```text
factor_gate|alpha101_delta_close_1_rank|rejected|<specific_reason>|5
```

Acceptance: command exits 0 and persists both `factor.factor_eval_run` and `factor.factor_approval`. Rejection is acceptable if metrics do not meet thresholds.

- [ ] **Step 5: Verify DB persistence**

Run:

```bash
psql service=stock_research -Atc "SELECT factor_name || '|' || status || '|' || reason FROM factor.factor_approval WHERE factor_name = 'alpha101_delta_close_1_rank' AND score_version = 'manual_v1';"
```

Expected:

```text
alpha101_delta_close_1_rank|approved|passed_thresholds
```

or the rejected status and reason from Step 4.

- [ ] **Step 6: Update docs**

In `docs/astock-research-platform-v1.md`, under factor evaluation current progress, add:

```markdown
- 已落地因子评价门禁：支持多周期评价、分年份诊断、分组表现、行业/市值暴露诊断，以及 `factor.factor_approval` 审批状态记录。
```

In `docs/daily-factor-pipeline-runbook.md`, add a command section:

```markdown
Evaluate a candidate factor before scoring promotion:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research evaluate-factor-gate --factor-name FACTOR_NAME --start-date YYYY-MM-DD --end-date YYYY-MM-DD --horizons 5,10,20,60 --primary-horizon 5 --score-version manual_v1
```
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
git commit -m "Document factor evaluation gate"
git push
```

---

## Acceptance Criteria

- `compute_labels_for_asset` generates horizons `{5, 10, 20, 60}`.
- Multi-horizon factor reports run for `forward_return_5d`, `forward_return_10d`, `forward_return_20d`, and `forward_return_60d`.
- ICIR remains available via `ic.summarize_ic`.
- By-year IC and Top-Bottom spread summaries exist.
- Segment return summaries exist for arbitrary segment labels, including market-state labels once available.
- Industry/group exposure and size exposure diagnostics exist.
- `factor.factor_eval_run` and `factor.factor_approval` exist in schema.
- `evaluate-factor-gate` persists an approval or rejection decision.
- No scoring weights are changed by this plan.
- Full tests pass.

## Self-Review

Spec coverage:

- Forward return 10d: Task 1.
- Multi-horizon evaluation: Task 2.
- By-year and segment performance: Task 3.
- Industry and size exposure: Task 4.
- Gate threshold decision: Task 5.
- Persistence: Task 6.
- CLI: Task 7.
- Real smoke and docs: Task 8.

Placeholder scan:

- No unresolved placeholders remain.

Type consistency:

- Horizons are `list[int]`.
- Return columns use `forward_return_{horizon}d`.
- Gate statuses are `approved` or `rejected`.
- Persistence table names are `factor.factor_eval_run` and `factor.factor_approval`.
