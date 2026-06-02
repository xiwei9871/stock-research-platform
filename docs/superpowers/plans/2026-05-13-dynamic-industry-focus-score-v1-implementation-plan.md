# Dynamic Industry Focus Score V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a point-in-time dynamic industry focus score and compare dynamic industry-gated Top20 backtests against the current full-market Top20 baseline.

**Architecture:** Add a focused `industry_focus_score.py` research module that computes industry metrics, ranks industries by date, selects focus industries, filters stock scores, runs vectorized TopN backtests, and writes reports. Add a CLI command that calls the report runner without writing to the database or replacing production Top20 reports.

**Tech Stack:** Python, pandas, pytest, argparse CLI, existing `manual_v1_config`, `score_factor_daily`, `run_vectorized_topn_backtest`, PostgreSQL read-only query helpers.

---

## File Structure

- Create `src/stock_research/industry_focus_score.py`
  - Owns industry metric calculation, cross-sectional ranks, dynamic focus selection, score filtering, backtest orchestration, DB loaders, and report writing.
- Modify `src/stock_research/cli.py`
  - Adds `industry-focus-backtest` command and imports the report runner.
- Create `tests/test_industry_focus_score.py`
  - Unit tests for score calculation, no future data behavior, minimum industry eligibility, Top K selection, hysteresis, and score filtering.
- Create `tests/test_industry_focus_score_cli.py`
  - CLI smoke test using monkeypatched report runner.
- No changes to production Top20 command paths.
- No schema or DB write changes.

## Task 1: Core Ranking And Selection Utilities

**Files:**
- Create: `src/stock_research/industry_focus_score.py`
- Test: `tests/test_industry_focus_score.py`

- [ ] **Step 1: Write failing tests for date-wise ranks and dynamic Top K**

Add to `tests/test_industry_focus_score.py`:

```python
import pandas as pd

from stock_research import industry_focus_score


def test_rank_by_date_computes_cross_sectional_percentiles():
    frame = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "industry_name": "A", "value": 10.0},
            {"trade_date": "2026-01-01", "industry_name": "B", "value": 20.0},
            {"trade_date": "2026-01-01", "industry_name": "C", "value": 30.0},
            {"trade_date": "2026-01-02", "industry_name": "A", "value": 5.0},
            {"trade_date": "2026-01-02", "industry_name": "B", "value": 15.0},
        ]
    )

    ranked = industry_focus_score.rank_by_date(
        frame,
        value_col="value",
        output_col="value_rank",
        ascending=True,
    )

    day1 = ranked[ranked["trade_date"] == "2026-01-01"].sort_values("industry_name")
    day2 = ranked[ranked["trade_date"] == "2026-01-02"].sort_values("industry_name")
    assert list(day1["value_rank"]) == [1 / 3, 2 / 3, 1.0]
    assert list(day2["value_rank"]) == [0.5, 1.0]


def test_select_dynamic_topk_keeps_only_top_ranked_industries():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "industry_name": "A", "industry_focus_score": 0.9},
            {"trade_date": "2026-01-01", "industry_name": "B", "industry_focus_score": 0.8},
            {"trade_date": "2026-01-01", "industry_name": "C", "industry_focus_score": 0.1},
            {"trade_date": "2026-01-02", "industry_name": "A", "industry_focus_score": 0.4},
            {"trade_date": "2026-01-02", "industry_name": "B", "industry_focus_score": 0.7},
            {"trade_date": "2026-01-02", "industry_name": "C", "industry_focus_score": 0.6},
        ]
    )

    selected = industry_focus_score.select_dynamic_topk_focus(scores, top_k=2)

    assert selected[["trade_date", "industry_name"]].to_dict("records") == [
        {"trade_date": "2026-01-01", "industry_name": "A"},
        {"trade_date": "2026-01-01", "industry_name": "B"},
        {"trade_date": "2026-01-02", "industry_name": "B"},
        {"trade_date": "2026-01-02", "industry_name": "C"},
    ]
    assert set(selected["selection_mode"]) == {"dynamic_topk"}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_industry_focus_score.py -q
```

Expected: FAIL because `stock_research.industry_focus_score` does not exist.

- [ ] **Step 3: Implement ranking and Top K selection**

Create `src/stock_research/industry_focus_score.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_config import manual_v1_config
from stock_research.scoring.pipeline import score_factor_daily
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    VectorizedTopNResult,
    run_vectorized_topn_backtest,
)


FIXED_FOCUS_INDUSTRIES = (
    "计算机、通信和其他电子设备制造业",
    "专用设备制造业",
    "软件和信息技术服务业",
)


@dataclass(frozen=True)
class IndustryFocusConfig:
    start_date: object
    end_date: object
    top_n: int = 20
    dynamic_top_k: int = 4
    enter_top_n: int = 4
    exit_top_n: int = 8
    max_focus_industries: int = 6
    min_focus_industries: int = 2
    min_industry_stocks: int = 20
    transaction_cost_bps: tuple[float, ...] = (0.0, 20.0)
    industry_system: str = "csrc"
    industry_level: int = 1
    adjust_type: str = "hfq"


def rank_by_date(
    frame: pd.DataFrame,
    *,
    value_col: str,
    output_col: str,
    ascending: bool = True,
) -> pd.DataFrame:
    result = frame.copy()
    result["trade_date"] = result["trade_date"].map(_iso_date)
    result[output_col] = (
        result.groupby("trade_date", group_keys=False)[value_col]
        .rank(method="average", pct=True, ascending=ascending)
        .astype(float)
    )
    return result


def select_dynamic_topk_focus(
    industry_scores: pd.DataFrame,
    *,
    top_k: int = 4,
    min_score_percentile: float | None = None,
) -> pd.DataFrame:
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    scores = _normalize_industry_scores(industry_scores)
    if scores.empty:
        return _empty_focus_frame()
    ranked = _add_rank_number(scores)
    selected = ranked[ranked["focus_rank"] <= int(top_k)].copy()
    if min_score_percentile is not None:
        selected = selected[selected["score_percentile"] >= float(min_score_percentile)]
    selected["selection_mode"] = "dynamic_topk"
    return selected[["trade_date", "industry_name", "selection_mode", "focus_rank", "industry_focus_score"]]


def _normalize_industry_scores(industry_scores: pd.DataFrame) -> pd.DataFrame:
    if industry_scores.empty:
        return pd.DataFrame(columns=["trade_date", "industry_name", "industry_focus_score"])
    scores = industry_scores.copy()
    scores["trade_date"] = scores["trade_date"].map(_iso_date)
    scores["industry_name"] = scores["industry_name"].astype(str)
    scores["industry_focus_score"] = pd.to_numeric(scores["industry_focus_score"], errors="coerce")
    scores = scores.dropna(subset=["industry_focus_score"])
    return scores


def _add_rank_number(scores: pd.DataFrame) -> pd.DataFrame:
    ranked = scores.sort_values(
        ["trade_date", "industry_focus_score", "industry_name"],
        ascending=[True, False, True],
    ).copy()
    ranked["focus_rank"] = ranked.groupby("trade_date").cumcount() + 1
    ranked["score_percentile"] = (
        ranked.groupby("trade_date")["industry_focus_score"]
        .rank(method="average", pct=True, ascending=True)
        .astype(float)
    )
    return ranked


def _empty_focus_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["trade_date", "industry_name", "selection_mode", "focus_rank", "industry_focus_score"]
    )


def _iso_date(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
.venv/bin/pytest tests/test_industry_focus_score.py -q
```

Expected: PASS for the two tests in this task.

## Task 2: Industry Metrics And Composite Score

**Files:**
- Modify: `src/stock_research/industry_focus_score.py`
- Test: `tests/test_industry_focus_score.py`

- [ ] **Step 1: Write failing tests for point-in-time metrics and minimum stock count**

Append to `tests/test_industry_focus_score.py`:

```python
def _industry_prices():
    rows = []
    for day, a_close, b_close, c_close, d_close in [
        ("2026-01-01", 10.0, 20.0, 30.0, 40.0),
        ("2026-01-02", 11.0, 21.0, 29.0, 39.0),
        ("2026-01-05", 12.0, 22.0, 28.0, 38.0),
        ("2026-01-06", 13.0, 23.0, 27.0, 37.0),
    ]:
        for asset_id, close in [("A1", a_close), ("A2", b_close), ("B1", c_close), ("B2", d_close)]:
            rows.append(
                {
                    "trade_date": day,
                    "asset_id": asset_id,
                    "close": close,
                    "amount": close * 1000,
                }
            )
    return pd.DataFrame(rows)


def _industry_memberships():
    return pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "industry_name": "强行业"},
            {"trade_date": "2026-01-01", "asset_id": "A2", "industry_name": "强行业"},
            {"trade_date": "2026-01-01", "asset_id": "B1", "industry_name": "弱行业"},
            {"trade_date": "2026-01-01", "asset_id": "B2", "industry_name": "弱行业"},
            {"trade_date": "2026-01-02", "asset_id": "A1", "industry_name": "强行业"},
            {"trade_date": "2026-01-02", "asset_id": "A2", "industry_name": "强行业"},
            {"trade_date": "2026-01-02", "asset_id": "B1", "industry_name": "弱行业"},
            {"trade_date": "2026-01-02", "asset_id": "B2", "industry_name": "弱行业"},
            {"trade_date": "2026-01-05", "asset_id": "A1", "industry_name": "强行业"},
            {"trade_date": "2026-01-05", "asset_id": "A2", "industry_name": "强行业"},
            {"trade_date": "2026-01-05", "asset_id": "B1", "industry_name": "弱行业"},
            {"trade_date": "2026-01-05", "asset_id": "B2", "industry_name": "弱行业"},
            {"trade_date": "2026-01-06", "asset_id": "A1", "industry_name": "强行业"},
            {"trade_date": "2026-01-06", "asset_id": "A2", "industry_name": "强行业"},
            {"trade_date": "2026-01-06", "asset_id": "B1", "industry_name": "弱行业"},
            {"trade_date": "2026-01-06", "asset_id": "B2", "industry_name": "弱行业"},
        ]
    )


def _stock_scores():
    return pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "asset_id": "A1", "score_total": 95.0, "rank": 1},
            {"trade_date": "2026-01-05", "asset_id": "A2", "score_total": 90.0, "rank": 2},
            {"trade_date": "2026-01-05", "asset_id": "B1", "score_total": 50.0, "rank": 3},
            {"trade_date": "2026-01-05", "asset_id": "B2", "score_total": 40.0, "rank": 4},
        ]
    )


def test_build_industry_scores_uses_only_dates_up_to_score_date():
    scores = industry_focus_score.build_industry_scores(
        prices=_industry_prices(),
        memberships=_industry_memberships(),
        stock_scores=_stock_scores(),
        min_industry_stocks=2,
        top_candidate_count=2,
        long_window=3,
    )

    scored_day = scores[scores["trade_date"] == "2026-01-05"].set_index("industry_name")
    assert scored_day.loc["强行业", "industry_focus_score"] > scored_day.loc["弱行业", "industry_focus_score"]

    changed_future = _industry_prices()
    changed_future.loc[
        (changed_future["trade_date"] == "2026-01-06") & (changed_future["asset_id"].isin(["B1", "B2"])),
        "close",
    ] = 1000.0
    future_changed_scores = industry_focus_score.build_industry_scores(
        prices=changed_future,
        memberships=_industry_memberships(),
        stock_scores=_stock_scores(),
        min_industry_stocks=2,
        top_candidate_count=2,
        long_window=3,
    )
    original = scores[scores["trade_date"] == "2026-01-05"].sort_values("industry_name")
    revised = future_changed_scores[future_changed_scores["trade_date"] == "2026-01-05"].sort_values("industry_name")
    assert list(original["industry_focus_score"]) == list(revised["industry_focus_score"])


def test_build_industry_scores_excludes_industries_below_min_stock_count():
    scores = industry_focus_score.build_industry_scores(
        prices=_industry_prices(),
        memberships=_industry_memberships(),
        stock_scores=_stock_scores(),
        min_industry_stocks=3,
        top_candidate_count=2,
        long_window=3,
    )

    assert scores.empty
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_industry_focus_score.py -q
```

Expected: FAIL because `build_industry_scores` is not implemented.

- [ ] **Step 3: Implement metric calculation and composite score**

Add to `src/stock_research/industry_focus_score.py`:

```python
INDUSTRY_SCORE_COLUMNS = [
    "trade_date",
    "industry_name",
    "stock_count",
    "industry_ret_20d",
    "industry_ret_60d",
    "industry_amount_ratio_5_20",
    "industry_amount_ratio_20_60",
    "up_ratio_20d",
    "above_ma20_ratio",
    "above_ma60_ratio",
    "new_high_60d_ratio",
    "top100_count",
    "top100_overweight_ratio",
    "top_decile_score_mean",
    "volatility_20d",
    "max_drawdown_20d",
    "momentum_score",
    "breadth_score",
    "volume_score",
    "candidate_density_score",
    "quality_score",
    "overheat_penalty",
    "industry_focus_score",
]


def build_industry_scores(
    *,
    prices: pd.DataFrame,
    memberships: pd.DataFrame,
    stock_scores: pd.DataFrame,
    min_industry_stocks: int = 20,
    top_candidate_count: int = 100,
    long_window: int = 60,
) -> pd.DataFrame:
    merged = _merge_price_membership(prices, memberships)
    if merged.empty:
        return pd.DataFrame(columns=INDUSTRY_SCORE_COLUMNS)

    enriched = _add_stock_history_metrics(merged, long_window=long_window)
    industry_daily = _aggregate_industry_daily(enriched, min_industry_stocks=min_industry_stocks)
    if industry_daily.empty:
        return pd.DataFrame(columns=INDUSTRY_SCORE_COLUMNS)

    candidate_metrics = _candidate_density_metrics(
        stock_scores=stock_scores,
        memberships=memberships,
        min_industry_stocks=min_industry_stocks,
        top_candidate_count=top_candidate_count,
    )
    frame = industry_daily.merge(candidate_metrics, on=["trade_date", "industry_name"], how="left")
    for col in ["top100_count", "top100_overweight_ratio", "top_decile_score_mean"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
    return _build_composite_scores(frame).reindex(columns=INDUSTRY_SCORE_COLUMNS)


def _merge_price_membership(prices: pd.DataFrame, memberships: pd.DataFrame) -> pd.DataFrame:
    price_frame = prices.copy()
    member_frame = memberships.copy()
    if price_frame.empty or member_frame.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "industry_name", "close", "amount"])
    price_frame["trade_date"] = price_frame["trade_date"].map(_iso_date)
    member_frame["trade_date"] = member_frame["trade_date"].map(_iso_date)
    price_frame["asset_id"] = price_frame["asset_id"].astype(str)
    member_frame["asset_id"] = member_frame["asset_id"].astype(str)
    price_frame["close"] = pd.to_numeric(price_frame["close"], errors="coerce")
    price_frame["amount"] = pd.to_numeric(price_frame.get("amount", 0.0), errors="coerce")
    return price_frame.merge(
        member_frame[["trade_date", "asset_id", "industry_name"]],
        on=["trade_date", "asset_id"],
        how="inner",
    ).dropna(subset=["close", "industry_name"])


def _add_stock_history_metrics(frame: pd.DataFrame, *, long_window: int) -> pd.DataFrame:
    data = frame.sort_values(["asset_id", "trade_date"]).copy()
    grouped = data.groupby("asset_id", group_keys=False)
    data["ret_20d"] = grouped["close"].pct_change(periods=min(20, long_window))
    data["ret_60d"] = grouped["close"].pct_change(periods=long_window)
    data["ma20"] = grouped["close"].transform(lambda s: s.rolling(min(20, long_window), min_periods=1).mean())
    data["ma60"] = grouped["close"].transform(lambda s: s.rolling(long_window, min_periods=1).mean())
    data["high_60"] = grouped["close"].transform(lambda s: s.rolling(long_window, min_periods=1).max())
    data["amount_ma5"] = grouped["amount"].transform(lambda s: s.rolling(min(5, long_window), min_periods=1).mean())
    data["amount_ma20"] = grouped["amount"].transform(lambda s: s.rolling(min(20, long_window), min_periods=1).mean())
    data["amount_ma60"] = grouped["amount"].transform(lambda s: s.rolling(long_window, min_periods=1).mean())
    return data


def _aggregate_industry_daily(frame: pd.DataFrame, *, min_industry_stocks: int) -> pd.DataFrame:
    data = frame.copy()
    data["positive_20d"] = data["ret_20d"] > 0
    data["above_ma20"] = data["close"] >= data["ma20"]
    data["above_ma60"] = data["close"] >= data["ma60"]
    data["new_high_60d"] = data["close"] >= data["high_60"]
    data["amount_ratio_5_20"] = data["amount_ma5"] / data["amount_ma20"].replace(0, pd.NA)
    data["amount_ratio_20_60"] = data["amount_ma20"] / data["amount_ma60"].replace(0, pd.NA)
    grouped = data.groupby(["trade_date", "industry_name"], as_index=False)
    result = grouped.agg(
        stock_count=("asset_id", "nunique"),
        industry_ret_20d=("ret_20d", "mean"),
        industry_ret_60d=("ret_60d", "mean"),
        industry_amount_ratio_5_20=("amount_ratio_5_20", "mean"),
        industry_amount_ratio_20_60=("amount_ratio_20_60", "mean"),
        up_ratio_20d=("positive_20d", "mean"),
        above_ma20_ratio=("above_ma20", "mean"),
        above_ma60_ratio=("above_ma60", "mean"),
        new_high_60d_ratio=("new_high_60d", "mean"),
        volatility_20d=("ret_20d", "std"),
    )
    result["max_drawdown_20d"] = result["industry_ret_20d"].clip(upper=0.0)
    return result[result["stock_count"] >= int(min_industry_stocks)].copy()


def _candidate_density_metrics(
    *,
    stock_scores: pd.DataFrame,
    memberships: pd.DataFrame,
    min_industry_stocks: int,
    top_candidate_count: int,
) -> pd.DataFrame:
    if stock_scores.empty or memberships.empty:
        return pd.DataFrame(columns=["trade_date", "industry_name", "top100_count", "top100_overweight_ratio", "top_decile_score_mean"])
    scores = stock_scores.copy()
    scores["trade_date"] = scores["trade_date"].map(_iso_date)
    scores["asset_id"] = scores["asset_id"].astype(str)
    scores["score_total"] = pd.to_numeric(scores["score_total"], errors="coerce")
    members = memberships.copy()
    members["trade_date"] = members["trade_date"].map(_iso_date)
    members["asset_id"] = members["asset_id"].astype(str)
    joined = scores.merge(members[["trade_date", "asset_id", "industry_name"]], on=["trade_date", "asset_id"], how="inner")
    joined = joined.dropna(subset=["score_total", "industry_name"])
    joined = joined.sort_values(["trade_date", "score_total", "asset_id"], ascending=[True, False, True])
    joined["score_rank"] = joined.groupby("trade_date").cumcount() + 1
    joined["in_top_candidates"] = joined["score_rank"] <= int(top_candidate_count)
    industry_counts = joined.groupby(["trade_date", "industry_name"], as_index=False).agg(
        industry_score_count=("asset_id", "nunique"),
        top100_count=("in_top_candidates", "sum"),
        top_decile_score_mean=("score_total", lambda s: s.nlargest(max(1, int(len(s) * 0.1))).mean()),
    )
    totals = joined.groupby("trade_date", as_index=False).agg(total_score_count=("asset_id", "nunique"))
    industry_counts = industry_counts.merge(totals, on="trade_date", how="left")
    industry_counts["industry_share"] = industry_counts["industry_score_count"] / industry_counts["total_score_count"]
    industry_counts["top100_share"] = industry_counts["top100_count"] / float(top_candidate_count)
    industry_counts["top100_overweight_ratio"] = industry_counts["top100_share"] / industry_counts["industry_share"].replace(0, pd.NA)
    return industry_counts[industry_counts["industry_score_count"] >= int(min_industry_stocks)][
        ["trade_date", "industry_name", "top100_count", "top100_overweight_ratio", "top_decile_score_mean"]
    ]


def _build_composite_scores(frame: pd.DataFrame) -> pd.DataFrame:
    scored = frame.copy()
    rank_specs = [
        ("industry_ret_20d", "industry_ret_20d_rank", True),
        ("industry_ret_60d", "industry_ret_60d_rank", True),
        ("up_ratio_20d", "up_ratio_20d_rank", True),
        ("above_ma20_ratio", "above_ma20_ratio_rank", True),
        ("above_ma60_ratio", "above_ma60_ratio_rank", True),
        ("new_high_60d_ratio", "new_high_60d_ratio_rank", True),
        ("industry_amount_ratio_5_20", "industry_amount_ratio_5_20_rank", True),
        ("industry_amount_ratio_20_60", "industry_amount_ratio_20_60_rank", True),
        ("top100_count", "top100_count_rank", True),
        ("top100_overweight_ratio", "top100_overweight_ratio_rank", True),
        ("top_decile_score_mean", "top_decile_score_mean_rank", True),
        ("volatility_20d", "volatility_20d_rank", False),
        ("max_drawdown_20d", "max_drawdown_20d_rank", True),
    ]
    for value_col, output_col, ascending in rank_specs:
        scored = rank_by_date(scored, value_col=value_col, output_col=output_col, ascending=ascending)
    scored["momentum_score"] = 0.5 * scored["industry_ret_20d_rank"] + 0.5 * scored["industry_ret_60d_rank"]
    scored["breadth_score"] = (
        0.30 * scored["up_ratio_20d_rank"]
        + 0.30 * scored["above_ma20_ratio_rank"]
        + 0.20 * scored["above_ma60_ratio_rank"]
        + 0.20 * scored["new_high_60d_ratio_rank"]
    )
    scored["volume_score"] = 0.55 * scored["industry_amount_ratio_5_20_rank"] + 0.45 * scored["industry_amount_ratio_20_60_rank"]
    scored["candidate_density_score"] = (
        0.45 * scored["top100_count_rank"]
        + 0.35 * scored["top100_overweight_ratio_rank"]
        + 0.20 * scored["top_decile_score_mean_rank"]
    )
    scored["quality_score"] = 0.50 * scored["max_drawdown_20d_rank"] + 0.50 * scored["volatility_20d_rank"]
    scored["overheat_penalty"] = scored["industry_amount_ratio_5_20_rank"].fillna(0.0)
    scored["industry_focus_score"] = (
        0.30 * scored["momentum_score"]
        + 0.20 * scored["breadth_score"]
        + 0.20 * scored["volume_score"]
        + 0.20 * scored["candidate_density_score"]
        + 0.10 * scored["quality_score"]
        - 0.10 * scored["overheat_penalty"]
    )
    return scored
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
.venv/bin/pytest tests/test_industry_focus_score.py -q
```

Expected: PASS for ranking, Top K, industry score, and minimum stock count tests.

## Task 3: Hysteresis Selection And Fixed Diagnostic Mode

**Files:**
- Modify: `src/stock_research/industry_focus_score.py`
- Test: `tests/test_industry_focus_score.py`

- [ ] **Step 1: Write failing tests for hysteresis and fixed mode**

Append:

```python
def test_select_dynamic_hysteresis_retains_until_exit_rank():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "industry_name": "A", "industry_focus_score": 0.9},
            {"trade_date": "2026-01-01", "industry_name": "B", "industry_focus_score": 0.8},
            {"trade_date": "2026-01-01", "industry_name": "C", "industry_focus_score": 0.7},
            {"trade_date": "2026-01-02", "industry_name": "B", "industry_focus_score": 0.9},
            {"trade_date": "2026-01-02", "industry_name": "C", "industry_focus_score": 0.8},
            {"trade_date": "2026-01-02", "industry_name": "A", "industry_focus_score": 0.7},
            {"trade_date": "2026-01-03", "industry_name": "B", "industry_focus_score": 0.9},
            {"trade_date": "2026-01-03", "industry_name": "C", "industry_focus_score": 0.8},
            {"trade_date": "2026-01-03", "industry_name": "D", "industry_focus_score": 0.7},
            {"trade_date": "2026-01-03", "industry_name": "A", "industry_focus_score": 0.1},
        ]
    )

    selected = industry_focus_score.select_dynamic_hysteresis_focus(
        scores,
        enter_top_n=2,
        exit_top_n=3,
        max_focus_industries=3,
        min_focus_industries=1,
    )

    by_date = selected.groupby("trade_date")["industry_name"].apply(list).to_dict()
    assert by_date["2026-01-01"] == ["A", "B"]
    assert by_date["2026-01-02"] == ["B", "C", "A"]
    assert by_date["2026-01-03"] == ["B", "C"]
    assert set(selected["selection_mode"]) == {"dynamic_hysteresis"}


def test_select_fixed_focus_labels_mode_as_ex_post():
    selected = industry_focus_score.select_fixed_focus(
        trade_dates=["2026-01-01", "2026-01-02"],
        focus_industries=("行业A", "行业B"),
    )

    assert len(selected) == 4
    assert set(selected["selection_mode"]) == {"fixed_ex_post"}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_industry_focus_score.py -q
```

Expected: FAIL because hysteresis and fixed selection functions are missing.

- [ ] **Step 3: Implement hysteresis and fixed mode**

Add:

```python
def select_dynamic_hysteresis_focus(
    industry_scores: pd.DataFrame,
    *,
    enter_top_n: int = 4,
    exit_top_n: int = 8,
    max_focus_industries: int = 6,
    min_focus_industries: int = 2,
) -> pd.DataFrame:
    if enter_top_n <= 0 or exit_top_n <= 0:
        raise ValueError("enter_top_n and exit_top_n must be positive")
    scores = _add_rank_number(_normalize_industry_scores(industry_scores))
    if scores.empty:
        return _empty_focus_frame()
    rows: list[dict[str, Any]] = []
    active: set[str] = set()
    for trade_date, day in scores.groupby("trade_date", sort=True):
        rank_map = dict(zip(day["industry_name"], day["focus_rank"], strict=False))
        active = {name for name in active if rank_map.get(name, 999999) <= int(exit_top_n)}
        entrants = list(day[day["focus_rank"] <= int(enter_top_n)]["industry_name"])
        active.update(entrants)
        if len(active) < int(min_focus_industries):
            active.update(day.head(int(min_focus_industries))["industry_name"].tolist())
        active_ordered = [
            name
            for name in day.sort_values(["focus_rank", "industry_name"])["industry_name"]
            if name in active
        ][: int(max_focus_industries)]
        active = set(active_ordered)
        for name in active_ordered:
            source = day[day["industry_name"] == name].iloc[0]
            rows.append(
                {
                    "trade_date": trade_date,
                    "industry_name": name,
                    "selection_mode": "dynamic_hysteresis",
                    "focus_rank": int(source["focus_rank"]),
                    "industry_focus_score": float(source["industry_focus_score"]),
                }
            )
    return pd.DataFrame(rows, columns=_empty_focus_frame().columns)


def select_fixed_focus(
    *,
    trade_dates: list[str] | tuple[str, ...],
    focus_industries: tuple[str, ...] = FIXED_FOCUS_INDUSTRIES,
) -> pd.DataFrame:
    rows = [
        {
            "trade_date": _iso_date(trade_date),
            "industry_name": industry_name,
            "selection_mode": "fixed_ex_post",
            "focus_rank": None,
            "industry_focus_score": None,
        }
        for trade_date in sorted({_iso_date(date) for date in trade_dates})
        for industry_name in focus_industries
    ]
    return pd.DataFrame(rows, columns=_empty_focus_frame().columns)
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
.venv/bin/pytest tests/test_industry_focus_score.py -q
```

Expected: PASS.

## Task 4: Score Filtering And Backtest Variants

**Files:**
- Modify: `src/stock_research/industry_focus_score.py`
- Test: `tests/test_industry_focus_score.py`

- [ ] **Step 1: Write failing tests for filtering and reportable variant summaries**

Append:

```python
def test_filter_scores_to_focus_industries_keeps_scores_inside_selected_industries():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "rank": 1, "score_total": 90.0},
            {"trade_date": "2026-01-01", "asset_id": "B1", "rank": 2, "score_total": 80.0},
        ]
    )
    memberships = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "industry_name": "行业A"},
            {"trade_date": "2026-01-01", "asset_id": "B1", "industry_name": "行业B"},
        ]
    )
    focus = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "industry_name": "行业A",
                "selection_mode": "dynamic_topk",
                "focus_rank": 1,
                "industry_focus_score": 0.9,
            }
        ]
    )

    filtered = industry_focus_score.filter_scores_to_focus_industries(scores, memberships, focus)

    assert filtered[["trade_date", "asset_id", "industry_name"]].to_dict("records") == [
        {"trade_date": "2026-01-01", "asset_id": "A1", "industry_name": "行业A"}
    ]


def test_summarize_backtest_result_includes_cost_and_variant():
    result = industry_focus_score.summarize_variant_result(
        variant="base_top20",
        transaction_cost_bps=20.0,
        score_rows=10,
        result_summary={"cumulative_return": 0.1, "annual_return": 0.2, "max_drawdown": -0.05},
    )

    assert result["variant"] == "base_top20"
    assert result["transaction_cost_bps"] == 20.0
    assert result["score_rows"] == 10
    assert result["cumulative_return"] == 0.1
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_industry_focus_score.py -q
```

Expected: FAIL because filtering and summarization functions are missing.

- [ ] **Step 3: Implement filtering and summary helpers**

Add:

```python
def filter_scores_to_focus_industries(
    scores: pd.DataFrame,
    memberships: pd.DataFrame,
    focus_industries: pd.DataFrame,
) -> pd.DataFrame:
    score_frame = scores.copy()
    member_frame = memberships.copy()
    focus_frame = focus_industries.copy()
    for frame in [score_frame, member_frame, focus_frame]:
        frame["trade_date"] = frame["trade_date"].map(_iso_date)
    score_frame["asset_id"] = score_frame["asset_id"].astype(str)
    member_frame["asset_id"] = member_frame["asset_id"].astype(str)
    joined = score_frame.merge(
        member_frame[["trade_date", "asset_id", "industry_name"]],
        on=["trade_date", "asset_id"],
        how="inner",
    )
    allowed = focus_frame[["trade_date", "industry_name"]].drop_duplicates()
    filtered = joined.merge(allowed, on=["trade_date", "industry_name"], how="inner")
    filtered = filtered.sort_values(["trade_date", "score_total", "asset_id"], ascending=[True, False, True]).copy()
    filtered["rank"] = filtered.groupby("trade_date").cumcount() + 1
    return filtered


def summarize_variant_result(
    *,
    variant: str,
    transaction_cost_bps: float,
    score_rows: int,
    result_summary: dict[str, Any],
) -> dict[str, Any]:
    row = {
        "variant": variant,
        "transaction_cost_bps": float(transaction_cost_bps),
        "score_rows": int(score_rows),
    }
    row.update(result_summary)
    return row
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
.venv/bin/pytest tests/test_industry_focus_score.py -q
```

Expected: PASS.

## Task 5: Loaders, Orchestration, And Report Writing

**Files:**
- Modify: `src/stock_research/industry_focus_score.py`
- Test: `tests/test_industry_focus_score.py`

- [ ] **Step 1: Write failing report runner test with monkeypatched loaders**

Append:

```python
from pathlib import Path


def test_run_industry_focus_backtest_report_writes_outputs(tmp_path: Path, monkeypatch):
    factor_rows = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "factor_name": "ret_20", "factor_value": 1.0},
            {"trade_date": "2026-01-01", "asset_id": "B1", "factor_name": "ret_20", "factor_value": 0.1},
            {"trade_date": "2026-01-02", "asset_id": "A1", "factor_name": "ret_20", "factor_value": 1.0},
            {"trade_date": "2026-01-02", "asset_id": "B1", "factor_name": "ret_20", "factor_value": 0.1},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "close": 10.0, "amount": 1000.0},
            {"trade_date": "2026-01-01", "asset_id": "B1", "close": 20.0, "amount": 2000.0},
            {"trade_date": "2026-01-02", "asset_id": "A1", "close": 11.0, "amount": 1100.0},
            {"trade_date": "2026-01-02", "asset_id": "B1", "close": 19.0, "amount": 1900.0},
            {"trade_date": "2026-01-05", "asset_id": "A1", "close": 12.0, "amount": 1200.0},
            {"trade_date": "2026-01-05", "asset_id": "B1", "close": 18.0, "amount": 1800.0},
        ]
    )
    memberships = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A1", "industry_name": "行业A"},
            {"trade_date": "2026-01-01", "asset_id": "B1", "industry_name": "行业B"},
            {"trade_date": "2026-01-02", "asset_id": "A1", "industry_name": "行业A"},
            {"trade_date": "2026-01-02", "asset_id": "B1", "industry_name": "行业B"},
            {"trade_date": "2026-01-05", "asset_id": "A1", "industry_name": "行业A"},
            {"trade_date": "2026-01-05", "asset_id": "B1", "industry_name": "行业B"},
        ]
    )
    monkeypatch.setattr(industry_focus_score, "load_factor_rows", lambda **kwargs: factor_rows)
    monkeypatch.setattr(industry_focus_score, "load_prices", lambda **kwargs: prices)
    monkeypatch.setattr(industry_focus_score, "load_industry_memberships", lambda **kwargs: memberships)

    result = industry_focus_score.run_industry_focus_backtest_report(
        start_date="2026-01-01",
        end_date="2026-01-05",
        top_n=1,
        dynamic_top_k=1,
        min_industry_stocks=1,
        transaction_cost_bps=(0.0, 20.0),
        reports_dir=tmp_path,
    )

    assert Path(result["paths"]["summary"]).exists()
    assert Path(result["paths"]["industry_scores"]).exists()
    assert Path(result["paths"]["focus_industries_daily"]).exists()
    assert Path(result["paths"]["markdown_report"]).read_text(encoding="utf-8").startswith("# Industry Focus Score V1")
    assert set(result["summary"]["transaction_cost_bps"]) == {0.0, 20.0}
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_industry_focus_score.py -q
```

Expected: FAIL because loaders/report runner are missing.

- [ ] **Step 3: Implement DB loaders, report runner, and output writer**

Add:

```python
def load_factor_rows(*, start_date: str, end_date: str, service: str = SETTINGS.research_service) -> pd.DataFrame:
    config = manual_v1_config()
    factor_names = tuple(config["factor_groups"].keys())
    sql = """
    SELECT trade_date, asset_id, factor_name, factor_value
    FROM factor.factor_daily
    WHERE trade_date BETWEEN %s AND %s
      AND factor_name = ANY(%s)
    ORDER BY trade_date, asset_id, factor_name
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, [start_date, end_date, list(factor_names)]))


def load_prices(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT trade_date, asset_id, close, amount
    FROM market_daily_bar
    WHERE adjust_type = %s
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, [adjust_type, start_date, end_date]))


def load_industry_memberships(
    *,
    start_date: str,
    end_date: str,
    industry_system: str = "csrc",
    industry_level: int = 1,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT trade_date, asset_id, industry_name
    FROM core.industry_membership
    WHERE industry_system = %s
      AND industry_level = %s
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, [industry_system, industry_level, start_date, end_date]))


def run_industry_focus_backtest_report(
    *,
    start_date: object,
    end_date: object,
    top_n: int = 20,
    dynamic_top_k: int = 4,
    min_industry_stocks: int = 20,
    transaction_cost_bps: tuple[float, ...] = (0.0, 20.0),
    industry_system: str = "csrc",
    industry_level: int = 1,
    adjust_type: str = "hfq",
    reports_dir: str | Path = Path("/Users/xiwei/stock_research/reports"),
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    factor_rows = load_factor_rows(start_date=start, end_date=end, service=service)
    prices = load_prices(start_date=start, end_date=end, adjust_type=adjust_type, service=service)
    memberships = load_industry_memberships(
        start_date=start,
        end_date=end,
        industry_system=industry_system,
        industry_level=industry_level,
        service=service,
    )
    stock_scores = _score_factor_rows(factor_rows)
    industry_scores = build_industry_scores(
        prices=prices,
        memberships=memberships,
        stock_scores=stock_scores,
        min_industry_stocks=min_industry_stocks,
    )
    trade_dates = sorted(stock_scores["trade_date"].astype(str).unique().tolist())
    focus_frames = {
        "fixed_focus_pool_top20": select_fixed_focus(trade_dates=trade_dates),
        "dynamic_topk_focus_pool_top20": select_dynamic_topk_focus(industry_scores, top_k=dynamic_top_k),
        "dynamic_hysteresis_focus_pool_top20": select_dynamic_hysteresis_focus(industry_scores),
    }
    variant_scores = {"base_top20": stock_scores}
    for variant, focus in focus_frames.items():
        variant_scores[variant] = filter_scores_to_focus_industries(stock_scores, memberships, focus)
    results = []
    summary_rows = []
    for variant, scores in variant_scores.items():
        for cost in transaction_cost_bps:
            config = VectorizedTopNConfig(
                start_date=start,
                end_date=end,
                top_n=top_n,
                rebalance_frequency="daily",
                transaction_cost_bps=float(cost),
            )
            result = run_vectorized_topn_backtest(scores, prices[["trade_date", "asset_id", "close"]], config)
            results.append((variant, float(cost), result))
            summary_rows.append(
                summarize_variant_result(
                    variant=variant,
                    transaction_cost_bps=float(cost),
                    score_rows=len(scores),
                    result_summary=result.summary,
                )
            )
    summary = pd.DataFrame(summary_rows)
    focus_daily = pd.concat(focus_frames.values(), ignore_index=True) if focus_frames else _empty_focus_frame()
    top100_industry_daily = _top100_industry_daily(stock_scores, memberships)
    output_dir = Path(reports_dir) / f"industry_focus_score_v1_{start.replace('-', '')}_{end.replace('-', '')}"
    paths = write_industry_focus_outputs(
        output_dir=output_dir,
        start_date=start,
        end_date=end,
        industry_system=industry_system,
        industry_scores=industry_scores,
        focus_industries_daily=focus_daily,
        top100_industry_daily=top100_industry_daily,
        summary=summary,
        results=results,
    )
    return {
        "paths": paths,
        "summary": summary,
        "industry_scores": industry_scores,
        "focus_industries_daily": focus_daily,
        "top100_industry_daily": top100_industry_daily,
    }


def _score_factor_rows(factor_rows: pd.DataFrame) -> pd.DataFrame:
    config = manual_v1_config()
    scored = score_factor_daily(
        factor_rows,
        factor_directions=config["factor_directions"],
        weights=config["weights"],
        score_version=config["score_version"],
    )
    return scored.sort_values(["trade_date", "score_total", "asset_id"], ascending=[True, False, True])


def _top100_industry_daily(stock_scores: pd.DataFrame, memberships: pd.DataFrame) -> pd.DataFrame:
    if stock_scores.empty or memberships.empty:
        return pd.DataFrame(columns=["trade_date", "industry_name", "top100_count", "top100_avg_score"])
    scores = stock_scores.copy()
    members = memberships.copy()
    scores["trade_date"] = scores["trade_date"].map(_iso_date)
    members["trade_date"] = members["trade_date"].map(_iso_date)
    joined = scores.merge(members[["trade_date", "asset_id", "industry_name"]], on=["trade_date", "asset_id"], how="inner")
    joined = joined.sort_values(["trade_date", "score_total"], ascending=[True, False])
    joined["rank"] = joined.groupby("trade_date").cumcount() + 1
    top = joined[joined["rank"] <= 100]
    return top.groupby(["trade_date", "industry_name"], as_index=False).agg(
        top100_count=("asset_id", "nunique"),
        top100_avg_score=("score_total", "mean"),
    )


def write_industry_focus_outputs(
    *,
    output_dir: Path,
    start_date: str,
    end_date: str,
    industry_system: str,
    industry_scores: pd.DataFrame,
    focus_industries_daily: pd.DataFrame,
    top100_industry_daily: pd.DataFrame,
    summary: pd.DataFrame,
    results: list[tuple[str, float, VectorizedTopNResult]],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "industry_scores": str(output_dir / "industry_scores.csv"),
        "focus_industries_daily": str(output_dir / "focus_industries_daily.csv"),
        "top100_industry_daily": str(output_dir / "top100_industry_daily.csv"),
        "summary": str(output_dir / "summary.csv"),
        "markdown_report": str(output_dir / "industry_focus_score_report.md"),
    }
    industry_scores.to_csv(paths["industry_scores"], index=False)
    focus_industries_daily.to_csv(paths["focus_industries_daily"], index=False)
    top100_industry_daily.to_csv(paths["top100_industry_daily"], index=False)
    summary.to_csv(paths["summary"], index=False)
    for variant, cost, result in results:
        prefix = f"{variant}_cost{int(cost)}"
        equity_path = output_dir / f"{prefix}_equity.csv"
        positions_path = output_dir / f"{prefix}_positions.csv"
        result.equity_curve.to_csv(equity_path, index=False)
        result.positions.to_csv(positions_path, index=False)
        paths[f"{prefix}_equity"] = str(equity_path)
        paths[f"{prefix}_positions"] = str(positions_path)
    report = _markdown_report(
        start_date=start_date,
        end_date=end_date,
        industry_system=industry_system,
        summary=summary,
        focus_industries_daily=focus_industries_daily,
    )
    Path(paths["markdown_report"]).write_text(report, encoding="utf-8")
    return paths


def _markdown_report(
    *,
    start_date: str,
    end_date: str,
    industry_system: str,
    summary: pd.DataFrame,
    focus_industries_daily: pd.DataFrame,
) -> str:
    focus_counts = focus_industries_daily.groupby("selection_mode").size().rename("rows").reset_index()
    return "\n".join(
        [
            "# Industry Focus Score V1",
            "",
            f"Period: {start_date} to {end_date}",
            f"Industry system: {industry_system}",
            "",
            "Point-in-time rule: industry scores use only data with trade_date on or before each score date.",
            "",
            "## Summary",
            "",
            summary.to_markdown(index=False) if not summary.empty else "No summary rows.",
            "",
            "## Focus Selection Rows",
            "",
            focus_counts.to_markdown(index=False) if not focus_counts.empty else "No focus industries selected.",
            "",
            "## Notes",
            "",
            "- Fixed focus industries are labeled `fixed_ex_post` and are diagnostic only.",
            "- Dynamic modes are the valid point-in-time candidates for historical evaluation.",
            "- This phase does not replace production Top20 reports.",
        ]
    )
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
.venv/bin/pytest tests/test_industry_focus_score.py -q
```

Expected: PASS.

## Task 6: CLI Command

**Files:**
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_industry_focus_score_cli.py`

- [ ] **Step 1: Write failing CLI smoke test**

Create `tests/test_industry_focus_score_cli.py`:

```python
from stock_research import cli


def test_industry_focus_backtest_cli_prints_report_paths(monkeypatch, capsys):
    def fake_runner(**kwargs):
        assert kwargs["start_date"] == "2026-01-01"
        assert kwargs["end_date"] == "2026-01-05"
        assert kwargs["top_n"] == 20
        return {
            "paths": {
                "markdown_report": "/tmp/report.md",
                "summary": "/tmp/summary.csv",
                "industry_scores": "/tmp/industry_scores.csv",
                "focus_industries_daily": "/tmp/focus.csv",
            },
            "summary": [1, 2],
        }

    monkeypatch.setattr(cli, "run_industry_focus_backtest_report", fake_runner)
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "industry-focus-backtest",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-05",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert "industry_focus_backtest|report|/tmp/report.md" in out
    assert "industry_focus_backtest|summary|/tmp/summary.csv" in out
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
.venv/bin/pytest tests/test_industry_focus_score_cli.py -q
```

Expected: FAIL because CLI import and command are missing.

- [ ] **Step 3: Add CLI import, parser, and dispatch**

Modify `src/stock_research/cli.py`:

```python
from stock_research.industry_focus_score import run_industry_focus_backtest_report
```

Add parser near other research commands:

```python
    industry_focus_backtest = subparsers.add_parser("industry-focus-backtest")
    industry_focus_backtest.add_argument("--start-date", required=True)
    industry_focus_backtest.add_argument("--end-date", required=True)
    industry_focus_backtest.add_argument("--top-n", type=int, default=20)
    industry_focus_backtest.add_argument("--dynamic-top-k", type=int, default=4)
    industry_focus_backtest.add_argument("--min-industry-stocks", type=int, default=20)
    industry_focus_backtest.add_argument("--industry-system", default="csrc")
    industry_focus_backtest.add_argument("--industry-level", type=int, default=1)
    industry_focus_backtest.add_argument("--adjust-type", default="hfq")
    industry_focus_backtest.add_argument("--reports-dir", default="/Users/xiwei/stock_research/reports")
```

Add dispatch:

```python
    elif args.command == "industry-focus-backtest":
        result = run_industry_focus_backtest_report(
            start_date=args.start_date,
            end_date=args.end_date,
            top_n=args.top_n,
            dynamic_top_k=args.dynamic_top_k,
            min_industry_stocks=args.min_industry_stocks,
            industry_system=args.industry_system,
            industry_level=args.industry_level,
            adjust_type=args.adjust_type,
            reports_dir=args.reports_dir,
        )
        paths = result["paths"]
        print(f"industry_focus_backtest|report|{paths['markdown_report']}")
        print(f"industry_focus_backtest|summary|{paths['summary']}")
        print(f"industry_focus_backtest|industry_scores|{paths['industry_scores']}")
        print(f"industry_focus_backtest|focus_industries_daily|{paths['focus_industries_daily']}")
        print(f"industry_focus_backtest|summary_rows|{len(result['summary'])}")
```

- [ ] **Step 4: Run CLI test and module tests**

Run:

```bash
.venv/bin/pytest tests/test_industry_focus_score.py tests/test_industry_focus_score_cli.py -q
```

Expected: PASS.

## Task 7: Full Validation Backtest

**Files:**
- No code changes expected.
- Output: `reports/industry_focus_score_v1_20240527_<end>/`

- [ ] **Step 1: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_industry_focus_score.py tests/test_industry_focus_score_cli.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full existing test suite**

Run:

```bash
.venv/bin/pytest
```

Expected: PASS or only pre-existing failures clearly unrelated to this task.

- [ ] **Step 3: Run the historical dynamic industry backtest**

Run:

```bash
.venv/bin/stock-research industry-focus-backtest \
  --start-date 2024-05-27 \
  --end-date 2026-05-12 \
  --top-n 20 \
  --dynamic-top-k 4 \
  --min-industry-stocks 20
```

Expected output includes:

```text
industry_focus_backtest|report|/Users/xiwei/stock_research/reports/industry_focus_score_v1_20240527_20260512/industry_focus_score_report.md
industry_focus_backtest|summary|/Users/xiwei/stock_research/reports/industry_focus_score_v1_20240527_20260512/summary.csv
```

- [ ] **Step 4: Inspect summary for required variants and costs**

Run:

```bash
.venv/bin/python -c "import pandas as pd; p='reports/industry_focus_score_v1_20240527_20260512/summary.csv'; df=pd.read_csv(p); print(df[['variant','transaction_cost_bps','cumulative_return','annual_return','max_drawdown','sharpe_ratio','annual_turnover']].to_string(index=False))"
```

Expected:

- `base_top20` has 0 and 20 bps rows.
- `fixed_focus_pool_top20` has 0 and 20 bps rows.
- `dynamic_topk_focus_pool_top20` has 0 and 20 bps rows.
- `dynamic_hysteresis_focus_pool_top20` has 0 and 20 bps rows.

- [ ] **Step 5: Final response**

Report:

- modified files;
- command used;
- generated report path;
- summary metrics for baseline, fixed focus, dynamic Top K, and dynamic hysteresis at 20 bps;
- whether dynamic industry gating materially improves return after costs;
- whether drawdown or industry concentration worsens;
- tests run and result.

## Self-Review

- Spec coverage: the plan covers point-in-time industry scores, dynamic Top K, hysteresis, fixed ex-post diagnostic mode, Top20-gated backtests, 0/20 bps cost reports, output CSVs, Markdown report, and tests.
- Placeholder scan: no `TBD`, `TODO`, or open implementation placeholders remain.
- Type consistency: public function names used in tests match implementation snippets: `build_industry_scores`, `select_dynamic_topk_focus`, `select_dynamic_hysteresis_focus`, `select_fixed_focus`, `filter_scores_to_focus_industries`, `run_industry_focus_backtest_report`.
