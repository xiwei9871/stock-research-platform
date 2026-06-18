# Tech Bottleneck Point-In-Time EOD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Tech Bottleneck's fixed candidate CSV dependency with a formal point-in-time daily candidate snapshot and manifest-backed EOD strategy chain.

**Architecture:** Add a focused candidate snapshot builder that turns the accepted `strict_153_st_only_financial_state` universe into daily point-in-time ranked rows. Add a ranked-snapshot simulation path so portfolio logic consumes precomputed daily `bottleneck_rank`/`bottleneck_score` rows instead of rebuilding from a latest-only candidate file. Publish Tech readiness through manifest metadata and make Home, Review Queue, and Strategy Lab reject or label stale Tech candidate sources.

**Tech Stack:** Python 3.11, pandas, pytest, existing PostgreSQL manifest helpers, existing Strategy Lab API adapters, Vite/React dashboard tests only where labels or warnings need browser-visible coverage.

---

## File Structure

- Create `src/stock_research/tech_bottleneck_candidates.py`
  - Owns point-in-time candidate snapshot schema, strict source freshness validation, invariant validation, daily/full rebuild frame construction, CSV artifact read/write helpers.
- Create `tests/test_tech_bottleneck_candidates.py`
  - Covers no-future-data invariants, daily update rows, full rebuild rows, score/rank determinism.
- Modify `src/stock_research/serenity_tight3b_c2_experiment.py`
  - Adds `build_serenity_tight3b_c2_experiment_from_rank_frames(...)` so Tech can run from already ranked daily snapshots.
- Modify `tests/test_serenity_tight3b_c2_experiment.py`
  - Covers rank-frame simulation and proves no future snapshot row is read.
- Modify `src/stock_research/tech_bottleneck_v1.py`
  - Switches dashboard fresh runs from fixed CSV candidates to point-in-time snapshots, while keeping old CSV only as research fallback behind an explicit flag.
- Modify `tests/test_tech_bottleneck_v1.py`
  - Asserts `data_coverage.source == "point_in_time_daily_candidates"` and stale/missing snapshots fail clearly.
- Create `src/stock_research/tech_bottleneck_eod.py`
  - Runs daily/full Tech EOD: snapshot build, official contract simulation, artifact writing, manifest upserts.
- Create `tests/test_tech_bottleneck_eod.py`
  - Covers manifest metadata, artifact paths, official contract fields, idempotent daily rerun behavior.
- Modify `src/stock_research/cli.py`
  - Adds CLI commands for full rebuild and daily EOD.
- Modify `src/stock_research/dashboard/display_date_gate.py`
  - Requires `tech_bottleneck_candidates` success for display readiness and validates Tech candidate snapshot date.
- Modify `tests/test_dashboard_display_date_gate.py`
  - Adds stale Tech candidate snapshot cases.
- Modify `src/stock_research/dashboard/review_queue.py`
  - Rejects Tech manifest artifacts whose candidate snapshot metadata does not match the requested review date.
- Modify `tests/test_dashboard_review_queue.py`
  - Covers Review Queue ignoring stale Tech artifacts.
- Modify `src/stock_research/dashboard/backtests.py` only if it needs a clearer error payload from `run_tech_bottleneck_v1_backtest_for_dashboard`.
  - Keeps Strategy Lab route names stable.

## Task 1: Candidate Snapshot Builder

**Files:**
- Create: `src/stock_research/tech_bottleneck_candidates.py`
- Test: `tests/test_tech_bottleneck_candidates.py`

- [ ] **Step 1: Write failing tests for point-in-time invariants and daily/full rebuild output**

Create `tests/test_tech_bottleneck_candidates.py`:

```python
from __future__ import annotations

import pandas as pd
import pytest

from stock_research.tech_bottleneck_candidates import (
    TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION,
    build_point_in_time_candidate_snapshots,
    read_candidate_snapshots,
    validate_base_candidate_source_freshness,
    validate_candidate_snapshot_frame,
    write_candidate_snapshots,
)


def test_snapshot_excludes_future_first_hit_and_future_as_of_dates() -> None:
    snapshots = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [
                {
                    "asset_id": "A",
                    "stock_name": "Alpha",
                    "first_hit_date": "2025-01-02",
                    "hit_count": 5,
                    "primary_chain_id": "chain-a",
                    "primary_chain_name": "算力",
                    "financial_as_of_date": "2025-01-02",
                    "technical_as_of_date": "2025-01-02",
                },
                {
                    "asset_id": "B",
                    "stock_name": "Beta",
                    "first_hit_date": "2025-01-04",
                    "hit_count": 9,
                    "primary_chain_id": "chain-b",
                    "primary_chain_name": "半导体",
                    "financial_as_of_date": "2025-01-04",
                    "technical_as_of_date": "2025-01-04",
                },
                {
                    "asset_id": "C",
                    "stock_name": "Gamma",
                    "first_hit_date": "2025-01-02",
                    "hit_count": 7,
                    "primary_chain_id": "chain-c",
                    "primary_chain_name": "PCB",
                    "financial_as_of_date": "2025-01-05",
                    "technical_as_of_date": "2025-01-02",
                },
            ]
        ),
        prices=_prices(["A", "B", "C"], "2025-01-02", 4),
        start_date="2025-01-02",
        end_date="2025-01-03",
        run_id="tech-bt-20250103-test",
    )

    assert set(snapshots["trade_date"]) == {"2025-01-02", "2025-01-03"}
    assert snapshots[snapshots["trade_date"] == "2025-01-02"]["asset_id"].tolist() == ["A"]
    assert set(snapshots["asset_id"]) == {"A"}
    assert snapshots["data_as_of_date"].max() <= "2025-01-03"
    assert snapshots["engine_version"].unique().tolist() == [TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION]
    assert snapshots["filter_decision"].unique().tolist() == ["pass"]


def test_snapshot_ranks_are_daily_and_top5_flag_is_per_trade_date() -> None:
    snapshots = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [
                {"asset_id": f"A{i}", "stock_name": f"Name{i}", "first_hit_date": "2025-01-01", "hit_count": 10 - i}
                for i in range(1, 8)
            ]
        ),
        prices=_prices([f"A{i}" for i in range(1, 8)], "2025-01-01", 3),
        start_date="2025-01-01",
        end_date="2025-01-03",
        run_id="tech-bt-20250103-test",
    )

    day = snapshots[snapshots["trade_date"] == "2025-01-03"].sort_values("bottleneck_rank")
    assert day["bottleneck_rank"].tolist() == [1, 2, 3, 4, 5, 6, 7]
    assert day["is_top5"].tolist() == [True, True, True, True, True, False, False]
    assert day.iloc[0]["hit_count_as_of_date"] >= day.iloc[-1]["hit_count_as_of_date"]


def test_validate_candidate_snapshot_frame_rejects_future_dates() -> None:
    frame = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-03",
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-04",
                "hit_count_as_of_date": 1,
                "primary_chain_id": "",
                "primary_chain_name": "",
                "matched_bottleneck_dimensions": "",
                "financial_as_of_date": "2025-01-03",
                "technical_as_of_date": "2025-01-03",
                "data_as_of_date": "2025-01-03",
                "filter_decision": "pass",
                "filter_reason": "",
                "bottleneck_score": 0.5,
                "bottleneck_rank": 1,
                "is_top5": True,
                "engine_version": TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION,
                "run_id": "run-a",
            }
        ]
    )

    with pytest.raises(ValueError, match="first_hit_date must be <= trade_date"):
        validate_candidate_snapshot_frame(frame)


def test_write_and_read_candidate_snapshots_round_trip(tmp_path) -> None:
    frame = build_point_in_time_candidate_snapshots(
        base_candidates=pd.DataFrame(
            [{"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01", "hit_count": 3}]
        ),
        prices=_prices(["A"], "2025-01-01", 2),
        start_date="2025-01-01",
        end_date="2025-01-02",
        run_id="tech-bt-20250102-test",
    )
    path = tmp_path / "tech_bottleneck_daily_candidates.csv"

    write_candidate_snapshots(frame, path)
    loaded = read_candidate_snapshots(path, start_date="2025-01-02", end_date="2025-01-02")

    assert loaded["trade_date"].unique().tolist() == ["2025-01-02"]
    assert loaded["asset_id"].tolist() == ["A"]
    assert loaded["bottleneck_rank"].tolist() == [1]


def test_validate_base_candidate_source_requires_fresh_generation_date() -> None:
    stale = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "stock_name": "Alpha",
                "first_hit_date": "2025-01-01",
                "hit_count": 3,
                "source_latest_trade_date": "2025-01-02",
            }
        ]
    )

    with pytest.raises(ValueError, match="base candidate source is stale"):
        validate_base_candidate_source_freshness(stale, end_date="2025-01-03")


def _prices(asset_ids: list[str], start_date: str, periods: int) -> pd.DataFrame:
    rows = []
    for offset, trade_date in enumerate(pd.date_range(start_date, periods=periods, freq="D")):
        for asset_index, asset_id in enumerate(asset_ids, start=1):
            close = 10.0 + asset_index + offset
            rows.append(
                {
                    "trade_date": trade_date.strftime("%Y-%m-%d"),
                    "asset_id": asset_id,
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                }
            )
    return pd.DataFrame(rows)
```

- [ ] **Step 2: Run the new tests and verify they fail because the module does not exist**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_tech_bottleneck_candidates.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'stock_research.tech_bottleneck_candidates'
```

- [ ] **Step 3: Implement the candidate snapshot builder**

Create `src/stock_research/tech_bottleneck_candidates.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION = "tech_bottleneck_daily_candidates_v1"
TECH_BOTTLENECK_CANDIDATE_SOURCE = "point_in_time_daily_candidates"
TECH_BOTTLENECK_CANDIDATE_COLUMNS = [
    "trade_date",
    "asset_id",
    "stock_name",
    "first_hit_date",
    "hit_count_as_of_date",
    "primary_chain_id",
    "primary_chain_name",
    "matched_bottleneck_dimensions",
    "financial_as_of_date",
    "technical_as_of_date",
    "data_as_of_date",
    "filter_decision",
    "filter_reason",
    "bottleneck_score",
    "bottleneck_rank",
    "is_top5",
    "engine_version",
    "run_id",
]


def build_point_in_time_candidate_snapshots(
    *,
    base_candidates: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    run_id: str,
    engine_version: str = TECH_BOTTLENECK_CANDIDATE_ENGINE_VERSION,
) -> pd.DataFrame:
    candidates = _normalize_base_candidates(base_candidates)
    normalized_prices = _normalize_prices(prices, start_date=start_date, end_date=end_date)
    trading_dates = sorted(normalized_prices["trade_date"].dropna().astype(str).unique().tolist())
    trading_dates = [date for date in trading_dates if start_date <= date <= end_date]
    if not trading_dates or candidates.empty:
        return pd.DataFrame(columns=TECH_BOTTLENECK_CANDIDATE_COLUMNS)

    closes = normalized_prices.pivot(index="trade_date", columns="asset_id", values="close").sort_index()
    high_120 = closes.rolling(120, min_periods=3).max()
    max_evidence = float(np.log1p(pd.to_numeric(candidates["hit_count"], errors="coerce").fillna(1)).max())
    max_evidence = max(max_evidence, 1.0)
    rows: list[dict[str, Any]] = []

    for trade_date in trading_dates:
        eligible = candidates[
            (candidates["first_hit_date"] <= trade_date)
            & (candidates["financial_as_of_date"] <= trade_date)
            & (candidates["technical_as_of_date"] <= trade_date)
        ].copy()
        for row in eligible.itertuples(index=False):
            asset_id = str(row.asset_id)
            score = _bottleneck_score(
                row=row,
                trade_date=trade_date,
                closes=closes,
                high_120=high_120,
                max_evidence=max_evidence,
            )
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "stock_name": str(getattr(row, "stock_name", "") or ""),
                    "first_hit_date": str(row.first_hit_date),
                    "hit_count_as_of_date": float(row.hit_count),
                    "primary_chain_id": str(getattr(row, "primary_chain_id", "") or ""),
                    "primary_chain_name": str(getattr(row, "primary_chain_name", "") or ""),
                    "matched_bottleneck_dimensions": str(getattr(row, "matched_bottleneck_dimensions", "") or ""),
                    "financial_as_of_date": str(row.financial_as_of_date),
                    "technical_as_of_date": str(row.technical_as_of_date),
                    "data_as_of_date": trade_date,
                    "filter_decision": "pass",
                    "filter_reason": "",
                    "bottleneck_score": score,
                    "engine_version": engine_version,
                    "run_id": str(run_id),
                }
            )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=TECH_BOTTLENECK_CANDIDATE_COLUMNS)
    frame = frame.sort_values(
        ["trade_date", "bottleneck_score", "hit_count_as_of_date", "asset_id"],
        ascending=[True, False, False, True],
    ).reset_index(drop=True)
    frame["bottleneck_rank"] = frame.groupby("trade_date").cumcount() + 1
    frame["is_top5"] = frame["bottleneck_rank"] <= 5
    frame = frame[TECH_BOTTLENECK_CANDIDATE_COLUMNS]
    validate_candidate_snapshot_frame(frame)
    return frame


def validate_candidate_snapshot_frame(frame: pd.DataFrame) -> None:
    missing = [column for column in TECH_BOTTLENECK_CANDIDATE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"candidate snapshot missing columns: {missing}")
    if frame.empty:
        return
    normalized = frame.copy()
    for column in ["trade_date", "first_hit_date", "financial_as_of_date", "technical_as_of_date", "data_as_of_date"]:
        normalized[column] = pd.to_datetime(normalized[column], errors="coerce").dt.strftime("%Y-%m-%d")
    checks = [
        ("first_hit_date", "first_hit_date must be <= trade_date"),
        ("financial_as_of_date", "financial_as_of_date must be <= trade_date"),
        ("technical_as_of_date", "technical_as_of_date must be <= trade_date"),
        ("data_as_of_date", "data_as_of_date must be <= trade_date"),
    ]
    for column, message in checks:
        bad = normalized[column] > normalized["trade_date"]
        if bool(bad.any()):
            raise ValueError(message)


def write_candidate_snapshots(frame: pd.DataFrame, path: str | Path) -> Path:
    validate_candidate_snapshot_frame(frame)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    return output


def read_candidate_snapshots(path: str | Path, *, start_date: str, end_date: str) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False)
    validate_candidate_snapshot_frame(frame)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame = frame[frame["trade_date"].between(start_date, end_date)].copy()
    return frame.sort_values(["trade_date", "bottleneck_rank", "asset_id"]).reset_index(drop=True)


def read_base_candidate_source(path: str | Path, *, end_date: str) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False)
    validate_base_candidate_source_freshness(frame, end_date=end_date)
    return frame


def validate_base_candidate_source_freshness(frame: pd.DataFrame, *, end_date: str) -> None:
    if frame.empty:
        raise ValueError("base candidate source is empty")
    for column in ["source_latest_trade_date", "data_as_of_date", "generated_trade_date"]:
        if column in frame.columns:
            latest = str(pd.to_datetime(frame[column], errors="coerce").dt.strftime("%Y-%m-%d").max())
            if latest >= end_date:
                return
            raise ValueError(f"base candidate source is stale: {latest} < {end_date}")
    if "first_hit_date" in frame.columns:
        latest_first_hit = str(pd.to_datetime(frame["first_hit_date"], errors="coerce").dt.strftime("%Y-%m-%d").max())
        if latest_first_hit >= end_date:
            return
    raise ValueError("base candidate source is stale: no freshness column covers requested end_date")


def _normalize_base_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame(
            columns=[
                "asset_id",
                "stock_name",
                "first_hit_date",
                "hit_count",
                "primary_chain_id",
                "primary_chain_name",
                "matched_bottleneck_dimensions",
                "financial_as_of_date",
                "technical_as_of_date",
            ]
        )
    frame = candidates.copy()
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["stock_name"] = frame.get("stock_name", "").fillna("").astype(str)
    frame["first_hit_date"] = pd.to_datetime(frame["first_hit_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["hit_count"] = pd.to_numeric(frame.get("hit_count", 1), errors="coerce").fillna(1.0)
    for column in ["primary_chain_id", "primary_chain_name", "matched_bottleneck_dimensions"]:
        if column not in frame.columns:
            frame[column] = ""
        frame[column] = frame[column].fillna("").astype(str)
    if "financial_as_of_date" not in frame.columns:
        frame["financial_as_of_date"] = frame["first_hit_date"]
    if "technical_as_of_date" not in frame.columns:
        frame["technical_as_of_date"] = frame["first_hit_date"]
    frame["financial_as_of_date"] = pd.to_datetime(frame["financial_as_of_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["technical_as_of_date"] = pd.to_datetime(frame["technical_as_of_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return frame.dropna(subset=["asset_id", "first_hit_date", "financial_as_of_date", "technical_as_of_date"])


def _normalize_prices(prices: pd.DataFrame, *, start_date: str, end_date: str) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "open", "high", "low", "close"])
    frame = prices.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["asset_id"] = frame["asset_id"].astype(str)
    for column in ["open", "close"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "high" not in frame.columns:
        frame["high"] = frame[["open", "close"]].max(axis=1)
    if "low" not in frame.columns:
        frame["low"] = frame[["open", "close"]].min(axis=1)
    frame["high"] = pd.to_numeric(frame["high"], errors="coerce")
    frame["low"] = pd.to_numeric(frame["low"], errors="coerce")
    frame = frame[frame["trade_date"].between(start_date, end_date)]
    return frame.dropna(subset=["trade_date", "asset_id", "close"]).sort_values(["trade_date", "asset_id"])


def _bottleneck_score(*, row: Any, trade_date: str, closes: pd.DataFrame, high_120: pd.DataFrame, max_evidence: float) -> float:
    evidence_norm = float(np.log1p(float(row.hit_count)) / max_evidence)
    age_days = max((pd.Timestamp(trade_date) - pd.Timestamp(row.first_hit_date)).days, 0)
    freshness = max(0.0, 1.0 - age_days / 240.0)
    low_position = 0.5
    asset_id = str(row.asset_id)
    if asset_id in closes.columns and trade_date in closes.index:
        close = closes.at[trade_date, asset_id]
        rolling_high = high_120.at[trade_date, asset_id] if asset_id in high_120.columns else np.nan
        if pd.notna(close) and pd.notna(rolling_high) and rolling_high > 0:
            low_position = float(max(0.0, min(1.0, 1.0 - close / rolling_high)))
    return float(0.45 * evidence_norm + 0.25 * freshness + 0.30 * low_position)
```

- [ ] **Step 4: Run candidate snapshot tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_tech_bottleneck_candidates.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit candidate snapshot builder**

```bash
git add src/stock_research/tech_bottleneck_candidates.py tests/test_tech_bottleneck_candidates.py
git commit -m "feat: add tech bottleneck point-in-time candidates"
```

## Task 2: Run Portfolio Simulation From Daily Ranked Snapshots

**Files:**
- Modify: `src/stock_research/serenity_tight3b_c2_experiment.py`
- Test: `tests/test_serenity_tight3b_c2_experiment.py`

- [ ] **Step 1: Write failing tests for ranked snapshot simulation**

Append to `tests/test_serenity_tight3b_c2_experiment.py`:

```python
def test_build_experiment_from_rank_frames_uses_only_requested_snapshot_dates() -> None:
    from stock_research.serenity_tight3b_c2_experiment import build_serenity_tight3b_c2_experiment_from_rank_frames

    ranks = pd.DataFrame(
        [
            {"trade_date": "2025-01-01", "asset_id": "A", "bottleneck_rank": 1, "bottleneck_score": 0.9},
            {"trade_date": "2025-01-01", "asset_id": "B", "bottleneck_rank": 2, "bottleneck_score": 0.8},
            {"trade_date": "2025-01-02", "asset_id": "A", "bottleneck_rank": 1, "bottleneck_score": 0.9},
            {"trade_date": "2025-01-02", "asset_id": "B", "bottleneck_rank": 2, "bottleneck_score": 0.8},
            {"trade_date": "2025-01-03", "asset_id": "FUTURE", "bottleneck_rank": 1, "bottleneck_score": 1.0},
        ]
    )

    result = build_serenity_tight3b_c2_experiment_from_rank_frames(
        ranks=ranks,
        prices=_rank_frame_prices(),
        market_exposure=pd.DataFrame(
            [
                {"trade_date": "2025-01-01", "target_exposure": 1.0},
                {"trade_date": "2025-01-02", "target_exposure": 1.0},
            ]
        ),
        start_date="2025-01-01",
        end_date="2025-01-02",
        universe_name="strict_153_st_only_financial_state",
        top_n_values=[1],
        rebalance_frequencies=["weekly"],
        protection_configs=[{"name": "rank_exit_top10_1d", "rank_exit": 10, "confirm_days": 1}],
        transaction_cost_bps=20.0,
    )

    traded_assets = set(result["best_trades"]["asset_id"].astype(str).tolist())
    assert "A" in traded_assets
    assert "FUTURE" not in traded_assets
    assert result["summary"].iloc[0]["top_n"] == 1


def _rank_frame_prices() -> pd.DataFrame:
    rows = []
    for trade_date in ["2025-01-01", "2025-01-02", "2025-01-03"]:
        for asset_id, close in {"A": 10.0, "B": 20.0, "FUTURE": 30.0}.items():
            rows.append(
                {
                    "trade_date": trade_date,
                    "asset_id": asset_id,
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                }
            )
    return pd.DataFrame(rows)
```

- [ ] **Step 2: Run the new test and verify it fails on missing function**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_serenity_tight3b_c2_experiment.py::test_build_experiment_from_rank_frames_uses_only_requested_snapshot_dates -q
```

Expected:

```text
ImportError: cannot import name 'build_serenity_tight3b_c2_experiment_from_rank_frames'
```

- [ ] **Step 3: Add ranked-frame entry point without changing existing CSV experiment behavior**

In `src/stock_research/serenity_tight3b_c2_experiment.py`, add this public function immediately after `build_serenity_tight3b_c2_experiment_from_frames(...)`:

```python
def build_serenity_tight3b_c2_experiment_from_rank_frames(
    *,
    ranks: pd.DataFrame,
    prices: pd.DataFrame,
    market_exposure: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    universe_name: str = "strict_153",
    top_n_values: list[int] | None = None,
    rebalance_frequencies: list[str] | None = None,
    protection_configs: list[dict[str, Any]] | None = None,
    transaction_cost_bps: float = 20.0,
    adjust_type: str = "hfq",
) -> dict[str, Any]:
    top_ns = _clean_top_n_values(top_n_values)
    frequencies = _clean_frequencies(rebalance_frequencies)
    protections = _clean_protection_configs(protection_configs)
    normalized_prices = _normalize_prices(prices, start_date=start_date, end_date=end_date)
    normalized_ranks = _normalize_rank_snapshots(ranks, start_date=start_date, end_date=end_date)
    normalized_exposure = _normalize_market_exposure(market_exposure)

    all_summary: list[pd.DataFrame] = []
    all_equity: list[pd.DataFrame] = []
    all_positions: list[pd.DataFrame] = []
    all_trades: list[pd.DataFrame] = []
    runs: dict[tuple[str, int, str], dict[str, pd.DataFrame]] = {}

    for frequency in frequencies:
        for top_n in top_ns:
            for protection in protections:
                run = _simulate_one_config(
                    ranks=normalized_ranks,
                    prices=normalized_prices,
                    market_exposure=normalized_exposure,
                    start_date=start_date,
                    end_date=end_date,
                    universe_name=universe_name,
                    frequency=frequency,
                    top_n=top_n,
                    protection=protection,
                    transaction_cost_bps=transaction_cost_bps,
                )
                all_summary.append(run["summary"])
                all_equity.append(run["equity"])
                all_positions.append(run["positions"])
                all_trades.append(run["trades"])
                runs[(frequency, top_n, protection.name)] = run

    summary = _rank_summary(_concat(all_summary, SUMMARY_COLUMNS))
    equity = _concat(all_equity)
    positions = _concat(all_positions)
    trades = _concat(all_trades)
    report = _render_report(summary)
    best = _best_run(summary, runs)
    result: dict[str, Any] = {
        "summary": summary,
        "equity": equity,
        "positions": positions,
        "trades": trades,
        "best_equity": best.get("equity", pd.DataFrame()),
        "best_positions": best.get("positions", pd.DataFrame()),
        "best_trades": best.get("trades", pd.DataFrame()),
        "universe_definitions": pd.DataFrame(),
        "report": report,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        paths = {
            "summary": output / "serenity_tight3b_c2_matrix_summary.csv",
            "equity": output / "serenity_tight3b_c2_equity.csv",
            "positions": output / "serenity_tight3b_c2_positions.csv",
            "trades": output / "serenity_tight3b_c2_trades.csv",
            "best_equity": output / "serenity_tight3b_c2_best_equity.csv",
            "best_positions": output / "serenity_tight3b_c2_best_positions.csv",
            "best_trades": output / "serenity_tight3b_c2_best_trades.csv",
            "report": output / "summary.md",
        }
        summary.to_csv(paths["summary"], index=False)
        equity.to_csv(paths["equity"], index=False)
        positions.to_csv(paths["positions"], index=False)
        trades.to_csv(paths["trades"], index=False)
        result["best_equity"].to_csv(paths["best_equity"], index=False)
        result["best_positions"].to_csv(paths["best_positions"], index=False)
        result["best_trades"].to_csv(paths["best_trades"], index=False)
        paths["report"].write_text(report, encoding="utf-8")
        result["paths"] = {key: str(value) for key, value in paths.items()}
    return result
```

Add this helper near `_normalize_candidates(...)`:

```python
def _normalize_rank_snapshots(ranks: pd.DataFrame, *, start_date: str, end_date: str) -> pd.DataFrame:
    if ranks.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id", "bottleneck_rank", "bottleneck_score"])
    frame = ranks.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["bottleneck_rank"] = pd.to_numeric(frame["bottleneck_rank"], errors="coerce")
    frame["bottleneck_score"] = pd.to_numeric(frame["bottleneck_score"], errors="coerce")
    frame = frame[frame["trade_date"].between(start_date, end_date)].copy()
    frame = frame.dropna(subset=["trade_date", "asset_id", "bottleneck_rank", "bottleneck_score"])
    frame["bottleneck_rank"] = frame["bottleneck_rank"].astype(int)
    return frame.sort_values(["trade_date", "bottleneck_rank", "asset_id"]).reset_index(drop=True)
```

- [ ] **Step 4: Run ranked-frame tests and existing experiment tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_serenity_tight3b_c2_experiment.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit ranked-frame simulation**

```bash
git add src/stock_research/serenity_tight3b_c2_experiment.py tests/test_serenity_tight3b_c2_experiment.py
git commit -m "feat: run serenity c2 from ranked snapshots"
```

## Task 3: Switch Tech V1 To Point-In-Time Snapshot Source

**Files:**
- Modify: `src/stock_research/tech_bottleneck_v1.py`
- Test: `tests/test_tech_bottleneck_v1.py`

- [ ] **Step 1: Write failing tests for snapshot source metadata and missing snapshot failure**

Append to `tests/test_tech_bottleneck_v1.py`:

```python
def test_tech_bottleneck_v1_from_rank_snapshots_labels_point_in_time_source() -> None:
    from stock_research.tech_bottleneck_v1 import build_tech_bottleneck_v1_from_rank_snapshots

    result = build_tech_bottleneck_v1_from_rank_snapshots(
        candidate_snapshots=_rank_snapshots(),
        prices=_prices(),
        market_exposure=_market_exposure(),
        start_date="2025-01-01",
        end_date="2025-01-08",
        top_n=2,
        rebalance_frequency="weekly",
        transaction_cost_bps=20,
    )

    summary = result["summary"]
    assert summary["data_coverage"]["source"] == "point_in_time_daily_candidates"
    assert summary["data_coverage"]["candidate_snapshot_latest_date"] == "2025-01-08"
    assert summary["data_coverage"]["candidate_snapshot_rows"] == len(_rank_snapshots())
    assert result["trades"]


def test_tech_bottleneck_v1_requires_snapshot_rows_for_requested_range() -> None:
    from stock_research.tech_bottleneck_v1 import build_tech_bottleneck_v1_from_rank_snapshots

    with pytest.raises(ValueError, match="Tech Bottleneck candidate snapshots are missing"):
        build_tech_bottleneck_v1_from_rank_snapshots(
            candidate_snapshots=pd.DataFrame(),
            prices=_prices(),
            market_exposure=_market_exposure(),
            start_date="2025-01-01",
            end_date="2025-01-08",
            top_n=2,
            rebalance_frequency="weekly",
            transaction_cost_bps=20,
        )


def _rank_snapshots() -> pd.DataFrame:
    rows = []
    for trade_date in pd.date_range("2025-01-01", periods=8, freq="D"):
        rows.extend(
            [
                {
                    "trade_date": trade_date.strftime("%Y-%m-%d"),
                    "asset_id": "A",
                    "stock_name": "Alpha",
                    "bottleneck_rank": 1,
                    "bottleneck_score": 0.9,
                },
                {
                    "trade_date": trade_date.strftime("%Y-%m-%d"),
                    "asset_id": "B",
                    "stock_name": "Beta",
                    "bottleneck_rank": 2,
                    "bottleneck_score": 0.8,
                },
            ]
        )
    return pd.DataFrame(rows)
```

Add `import pytest` to the top of `tests/test_tech_bottleneck_v1.py`.

- [ ] **Step 2: Run Tech V1 tests and verify missing function failure**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_tech_bottleneck_v1.py -q
```

Expected:

```text
ImportError: cannot import name 'build_tech_bottleneck_v1_from_rank_snapshots'
```

- [ ] **Step 3: Add snapshot-based Tech builder and loader path**

In `src/stock_research/tech_bottleneck_v1.py`, update imports:

```python
from stock_research.serenity_tight3b_c2_experiment import (
    ProtectionConfig,
    build_serenity_tight3b_c2_experiment_from_frames,
    build_serenity_tight3b_c2_experiment_from_rank_frames,
    _summary_frame,
)
from stock_research.tech_bottleneck_candidates import (
    TECH_BOTTLENECK_CANDIDATE_SOURCE,
    read_candidate_snapshots,
)
```

Add constants near the existing paths:

```python
TECH_BOTTLENECK_V1_SNAPSHOT_ROOT = (
    SETTINGS.output_root / "research" / "tech_bottleneck_point_in_time_candidates"
)
TECH_BOTTLENECK_V1_SNAPSHOT_FILENAME = "tech_bottleneck_daily_candidates.csv"
```

Add this builder after `build_tech_bottleneck_v1_from_frames(...)`:

```python
def build_tech_bottleneck_v1_from_rank_snapshots(
    *,
    candidate_snapshots: pd.DataFrame,
    prices: pd.DataFrame,
    market_exposure: pd.DataFrame,
    start_date: str,
    end_date: str,
    top_n: int = 5,
    rebalance_frequency: str = "weekly",
    transaction_cost_bps: float = 20.0,
    max_position_weight: float | None = None,
    adjust_type: str = "hfq",
    report_start_date: str | None = None,
) -> dict[str, Any]:
    if candidate_snapshots.empty:
        raise ValueError("Tech Bottleneck candidate snapshots are missing for requested range")
    frequency = _supported_frequency(rebalance_frequency)
    config = TechBottleneckV1Config(
        start_date=start_date,
        end_date=end_date,
        top_n=int(top_n),
        rebalance_frequency=frequency,
        transaction_cost_bps=float(transaction_cost_bps),
        max_position_weight=max_position_weight,
        adjust_type=adjust_type,
    )
    result = build_serenity_tight3b_c2_experiment_from_rank_frames(
        ranks=candidate_snapshots,
        prices=prices,
        market_exposure=market_exposure,
        start_date=config.start_date,
        end_date=config.end_date,
        universe_name="strict_153_st_only_financial_state",
        top_n_values=[config.top_n],
        rebalance_frequencies=[config.rebalance_frequency],
        protection_configs=[{"name": TECH_BOTTLENECK_V1_PROTECTION_NAME, "rank_exit": 10, "confirm_days": 1}],
        transaction_cost_bps=config.transaction_cost_bps,
        adjust_type=config.adjust_type,
    )
    run = {
        "summary": result["summary"].iloc[0].to_dict() if not result["summary"].empty else {},
        "equity": result["best_equity"],
        "positions": result["best_positions"],
        "trades": result["best_trades"],
    }
    if report_start_date and report_start_date > config.start_date:
        run = _slice_lifecycle_result(
            run,
            requested_start_date=report_start_date,
            requested_end_date=config.end_date,
            top_n=config.top_n,
            frequency=config.rebalance_frequency,
        )
    summary = _dashboard_summary(run["summary"])
    snapshot_dates = sorted(candidate_snapshots["trade_date"].dropna().astype(str).unique().tolist())
    summary.update(
        {
            "engine_version": config.engine_version,
            "fresh_engine_note": "Tech Bottleneck V1 fresh recompute via point-in-time daily candidates",
            "baseline_name": TECH_BOTTLENECK_V1_BASELINE_NAME,
            "simulation_start_date": config.start_date,
            "requested_start_date": report_start_date or config.start_date,
            "transaction_cost_bps": config.transaction_cost_bps,
            "adjust_type": config.adjust_type,
            "position_rows": int(len(run["positions"])),
            "trade_rows": int(len(run["trades"])),
            "data_coverage": {
                "source": TECH_BOTTLENECK_CANDIDATE_SOURCE,
                "candidate_snapshot_rows": int(len(candidate_snapshots)),
                "candidate_snapshot_start_date": snapshot_dates[0] if snapshot_dates else "",
                "candidate_snapshot_latest_date": snapshot_dates[-1] if snapshot_dates else "",
                "price_rows": int(len(prices)),
                "market_exposure_rows": int(len(market_exposure)),
            },
        }
    )
    config_payload = asdict(config)
    if report_start_date:
        config_payload["start_date"] = report_start_date
        config_payload["simulation_start_date"] = config.start_date
    return {
        "strategy_id": "tech_bottleneck",
        "strategy_name": "Tech Bottleneck Discovery",
        "read_only": False,
        "source_kind": TECH_BOTTLENECK_V1_ENGINE_VERSION,
        "config": config_payload,
        "summary": summary,
        "equity_curve": _records(run["equity"]),
        "positions": _records(run["positions"]),
        "trades": _records(run["trades"]),
    }
```

Change `run_tech_bottleneck_v1_backtest_for_dashboard(...)` to call the snapshot builder:

```python
frames = load_tech_bottleneck_v1_frames(config)
return build_tech_bottleneck_v1_from_rank_snapshots(
    candidate_snapshots=frames["candidate_snapshots"],
    prices=frames["prices"],
    market_exposure=frames["market_exposure"],
    start_date=config.start_date,
    end_date=config.end_date,
    top_n=config.top_n,
    rebalance_frequency=config.rebalance_frequency,
    transaction_cost_bps=config.transaction_cost_bps,
    max_position_weight=config.max_position_weight,
    adjust_type=config.adjust_type,
    report_start_date=requested_start_date,
)
```

Change `load_tech_bottleneck_v1_frames(...)` to read snapshots:

```python
snapshot_path = _latest_candidate_snapshot_path()
candidate_snapshots = read_candidate_snapshots(
    snapshot_path,
    start_date=config.start_date,
    end_date=config.end_date,
)
asset_ids = sorted(candidate_snapshots["asset_id"].dropna().astype(str).unique().tolist())
return {
    "candidate_snapshots": candidate_snapshots,
    "market_exposure": market_exposure,
    "prices": _load_prices(
        start_date=config.start_date,
        end_date=config.end_date,
        adjust_type=config.adjust_type,
        asset_ids=asset_ids,
        service=service,
    ),
}
```

Add helper:

```python
def _latest_candidate_snapshot_path() -> Path:
    candidates = sorted(TECH_BOTTLENECK_V1_SNAPSHOT_ROOT.glob(f"*/{TECH_BOTTLENECK_V1_SNAPSHOT_FILENAME}"))
    if not candidates:
        raise FileNotFoundError(
            f"Tech Bottleneck point-in-time snapshots not found under {TECH_BOTTLENECK_V1_SNAPSHOT_ROOT}"
        )
    return candidates[-1]
```

- [ ] **Step 4: Run Tech V1 tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_tech_bottleneck_v1.py tests/test_dashboard_backtests.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: Commit Tech V1 snapshot source switch**

```bash
git add src/stock_research/tech_bottleneck_v1.py tests/test_tech_bottleneck_v1.py
git commit -m "feat: use point-in-time tech snapshots for v1"
```

## Task 4: Formal Tech EOD Runner And Manifest Publication

**Files:**
- Create: `src/stock_research/tech_bottleneck_eod.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_tech_bottleneck_eod.py`

- [ ] **Step 1: Write failing EOD manifest tests**

Create `tests/test_tech_bottleneck_eod.py`:

```python
from __future__ import annotations

import pandas as pd

from stock_research.tech_bottleneck_eod import run_tech_bottleneck_eod_from_frames


def test_tech_bottleneck_eod_writes_candidate_and_strategy_manifest_entries(tmp_path) -> None:
    entries = []

    result = run_tech_bottleneck_eod_from_frames(
        base_candidates=pd.DataFrame(
            [
                {"asset_id": "A", "stock_name": "Alpha", "first_hit_date": "2025-01-01", "hit_count": 8},
                {"asset_id": "B", "stock_name": "Beta", "first_hit_date": "2025-01-01", "hit_count": 7},
            ]
        ),
        prices=_prices(),
        market_exposure=_market_exposure(),
        start_date="2025-01-01",
        end_date="2025-01-08",
        run_id="strategy-eod-20250108-local",
        output_dir=tmp_path,
        manifest_upsert=entries.append,
    )

    assert (tmp_path / "tech_bottleneck_daily_candidates.csv").exists()
    assert (tmp_path / "strategy_tech_bottleneck_review.csv").exists()
    assert {entry["module"] for entry in entries} == {"tech_bottleneck_candidates", "strategy_tech_bottleneck"}
    candidate_entry = next(entry for entry in entries if entry["module"] == "tech_bottleneck_candidates")
    strategy_entry = next(entry for entry in entries if entry["module"] == "strategy_tech_bottleneck")
    assert candidate_entry["latest_trade_date"] == "2025-01-08"
    assert candidate_entry["status"] == "success"
    assert strategy_entry["metadata"]["candidate_snapshot_latest_date"] == "2025-01-08"
    assert strategy_entry["metadata"]["summary"]["top_n"] == 5
    assert strategy_entry["metadata"]["summary"]["frequency"] == "biweekly"
    assert strategy_entry["metadata"]["summary"]["protection_name"] == "rank_exit_top10_1d"
    assert result["review_rows"] >= 1


def _prices() -> pd.DataFrame:
    rows = []
    for offset, trade_date in enumerate(pd.date_range("2025-01-01", periods=8, freq="D")):
        for asset_id, base in {"A": 10.0, "B": 20.0}.items():
            close = base + offset
            rows.append(
                {
                    "trade_date": trade_date.strftime("%Y-%m-%d"),
                    "asset_id": asset_id,
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                }
            )
    return pd.DataFrame(rows)


def _market_exposure() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": trade_date.strftime("%Y-%m-%d"), "target_exposure": 1.0}
            for trade_date in pd.date_range("2025-01-01", periods=8, freq="D")
        ]
    )
```

- [ ] **Step 2: Run EOD test and verify missing module failure**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_tech_bottleneck_eod.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'stock_research.tech_bottleneck_eod'
```

- [ ] **Step 3: Implement frame-level EOD runner**

Create `src/stock_research/tech_bottleneck_eod.py`:

```python
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stock_research.data_run_manifest import build_manifest_entry, upsert_data_run_manifest
from stock_research.tech_bottleneck_candidates import (
    TECH_BOTTLENECK_CANDIDATE_SOURCE,
    build_point_in_time_candidate_snapshots,
    write_candidate_snapshots,
)
from stock_research.tech_bottleneck_v1 import (
    TECH_BOTTLENECK_V1_ENGINE_VERSION,
    TECH_BOTTLENECK_V1_PROTECTION_NAME,
    build_tech_bottleneck_v1_from_rank_snapshots,
)


def run_tech_bottleneck_eod_from_frames(
    *,
    base_candidates: pd.DataFrame,
    prices: pd.DataFrame,
    market_exposure: pd.DataFrame,
    start_date: str,
    end_date: str,
    run_id: str,
    output_dir: str | Path,
    manifest_upsert: Callable[[dict[str, Any]], Any] = upsert_data_run_manifest,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    snapshots = build_point_in_time_candidate_snapshots(
        base_candidates=base_candidates,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        run_id=run_id,
    )
    snapshot_path = write_candidate_snapshots(snapshots, output / "tech_bottleneck_daily_candidates.csv")
    strategy = build_tech_bottleneck_v1_from_rank_snapshots(
        candidate_snapshots=snapshots,
        prices=prices,
        market_exposure=market_exposure,
        start_date=start_date,
        end_date=end_date,
        top_n=5,
        rebalance_frequency="biweekly",
        transaction_cost_bps=20.0,
        adjust_type="hfq",
    )
    review_path = output / "strategy_tech_bottleneck_review.csv"
    equity_path = output / "strategy_tech_bottleneck_equity.csv"
    positions_path = output / "strategy_tech_bottleneck_positions.csv"
    trades_path = output / "strategy_tech_bottleneck_trades.csv"
    pd.DataFrame(strategy["equity_curve"]).to_csv(equity_path, index=False)
    positions = pd.DataFrame(strategy["positions"])
    trades = pd.DataFrame(strategy["trades"])
    positions.to_csv(positions_path, index=False)
    trades.to_csv(trades_path, index=False)
    review = _review_rows_from_positions(positions, strategy_run_id=run_id)
    review.to_csv(review_path, index=False)
    ended_at = datetime.now(timezone.utc)

    candidate_entry = build_manifest_entry(
        run_id=run_id,
        run_date=date.today().isoformat(),
        trade_date=end_date,
        module="tech_bottleneck_candidates",
        source=TECH_BOTTLENECK_CANDIDATE_SOURCE,
        tier="tier1",
        status="success",
        started_at=started_at,
        ended_at=ended_at,
        row_count=int(len(snapshots)),
        asset_count=int(snapshots["asset_id"].nunique()) if not snapshots.empty else 0,
        latest_trade_date=end_date,
        artifact_path=snapshot_path,
        config_version=TECH_BOTTLENECK_V1_ENGINE_VERSION,
        metadata={
            "candidate_snapshot_latest_date": end_date,
            "candidate_source": TECH_BOTTLENECK_CANDIDATE_SOURCE,
        },
    )
    strategy_entry = build_manifest_entry(
        run_id=run_id,
        run_date=date.today().isoformat(),
        trade_date=end_date,
        module="strategy_tech_bottleneck",
        source="strategy_daily_eod",
        tier="tier1",
        status="success",
        started_at=started_at,
        ended_at=ended_at,
        row_count=int(len(review)),
        asset_count=int(review["asset_id"].nunique()) if not review.empty else 0,
        latest_trade_date=end_date,
        artifact_path=review_path,
        config_version=TECH_BOTTLENECK_V1_ENGINE_VERSION,
        metadata={
            "candidate_snapshot_latest_date": end_date,
            "candidate_source": TECH_BOTTLENECK_CANDIDATE_SOURCE,
            "candidate_snapshot_row_count": int(len(snapshots)),
            "equity_path": str(equity_path),
            "positions_path": str(positions_path),
            "trades_path": str(trades_path),
            "summary": strategy["summary"],
        },
    )
    manifest_upsert(candidate_entry)
    manifest_upsert(strategy_entry)
    return {
        "candidate_rows": int(len(snapshots)),
        "review_rows": int(len(review)),
        "snapshot_path": str(snapshot_path),
        "review_path": str(review_path),
    }


def _review_rows_from_positions(positions: pd.DataFrame, *, strategy_run_id: str) -> pd.DataFrame:
    if positions.empty:
        return pd.DataFrame(
            columns=[
                "trade_date",
                "asset_id",
                "rank",
                "score_total",
                "score_source",
                "score_explanation",
                "strategy_id",
                "strategy_name",
                "strategy_run_id",
                "source_type",
                "source_name",
                "source_rank",
                "review_tier",
            ]
        )
    latest_date = str(positions["trade_date"].dropna().astype(str).max())
    frame = positions[positions["trade_date"].astype(str) == latest_date].copy()
    frame["rank"] = pd.to_numeric(frame["bottleneck_rank"], errors="coerce").fillna(999).astype(int)
    frame["score_total"] = pd.to_numeric(frame["bottleneck_score"], errors="coerce") * 100.0
    frame["score_source"] = "bottleneck_score"
    frame["score_explanation"] = "Tech Bottleneck 点时态候选快照分数，按 0-100 展示"
    frame["strategy_id"] = "tech_bottleneck"
    frame["strategy_name"] = "Tech Bottleneck Combo"
    frame["strategy_run_id"] = strategy_run_id
    frame["source_type"] = "strategy_manifest"
    frame["source_name"] = "strategy_tech_bottleneck"
    frame["source_rank"] = frame["rank"]
    frame["review_tier"] = frame["rank"].map(lambda value: "top5_focus" if int(value) <= 5 else "top10_watch")
    return frame.sort_values("rank")[
        [
            "trade_date",
            "asset_id",
            "rank",
            "score_total",
            "score_source",
            "score_explanation",
            "strategy_id",
            "strategy_name",
            "strategy_run_id",
            "source_type",
            "source_name",
            "source_rank",
            "review_tier",
        ]
    ]
```

- [ ] **Step 4: Add CLI commands**

In `src/stock_research/cli.py`, add parser entries alongside existing strategy commands:

```python
tech_eod_parser = subparsers.add_parser("run-tech-bottleneck-eod")
tech_eod_parser.add_argument("--start-date", default="2025-01-01")
tech_eod_parser.add_argument("--end-date", required=True)
tech_eod_parser.add_argument("--output-dir", required=True)
tech_eod_parser.add_argument("--base-candidates-path", required=True)
tech_eod_parser.set_defaults(func=_cmd_run_tech_bottleneck_eod)
```

Add command handler:

```python
def _cmd_run_tech_bottleneck_eod(args: argparse.Namespace) -> int:
    from stock_research.tech_bottleneck_eod import run_tech_bottleneck_eod

    run_tech_bottleneck_eod(
        start_date=str(args.start_date),
        end_date=str(args.end_date),
        output_dir=str(args.output_dir),
        base_candidates_path=str(args.base_candidates_path),
    )
    return 0
```

Add file-backed formal `run_tech_bottleneck_eod(...)` in `src/stock_research/tech_bottleneck_eod.py` after the frame-level function. This command must not default to the old `2026-06-05` CSV. The caller must pass the latest strict candidate source produced by the upstream 20:00 data job; `read_base_candidate_source(...)` rejects stale source files before any strategy artifact is written:

```python
def run_tech_bottleneck_eod(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    base_candidates_path: str | Path,
) -> dict[str, Any]:
    from stock_research.tech_bottleneck_candidates import read_base_candidate_source
    from stock_research.tech_bottleneck_v1 import (
        TECH_BOTTLENECK_V1_MARKET_EXPOSURE_PATH,
        _load_prices,
    )

    base_candidates = read_base_candidate_source(base_candidates_path, end_date=end_date)
    market_exposure = pd.read_csv(TECH_BOTTLENECK_V1_MARKET_EXPOSURE_PATH, low_memory=False)
    asset_ids = sorted(base_candidates["asset_id"].dropna().astype(str).unique().tolist())
    prices = _load_prices(start_date=start_date, end_date=end_date, adjust_type="hfq", asset_ids=asset_ids)
    run_id = f"strategy-eod-{end_date}-local"
    return run_tech_bottleneck_eod_from_frames(
        base_candidates=base_candidates,
        prices=prices,
        market_exposure=market_exposure,
        start_date=start_date,
        end_date=end_date,
        run_id=run_id,
        output_dir=output_dir,
    )
```

- [ ] **Step 5: Run EOD tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_tech_bottleneck_eod.py tests/test_data_run_manifest.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit EOD runner**

```bash
git add src/stock_research/tech_bottleneck_eod.py src/stock_research/cli.py tests/test_tech_bottleneck_eod.py
git commit -m "feat: publish tech bottleneck eod manifest"
```

## Task 5: Readiness And Review Queue Trust Gates

**Files:**
- Modify: `src/stock_research/dashboard/display_date_gate.py`
- Modify: `src/stock_research/dashboard/review_queue.py`
- Test: `tests/test_dashboard_display_date_gate.py`
- Test: `tests/test_dashboard_review_queue.py`

- [ ] **Step 1: Write failing display gate test for missing Tech candidate snapshot**

Append to `tests/test_dashboard_display_date_gate.py`:

```python
def test_select_display_date_requires_tech_candidate_snapshot(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.display_date_gate.load_strategy_contracts",
        lambda profile="balanced": {},
    )
    modules = _ready_modules("2026-06-18")
    now = datetime(2026, 6, 18, 20, 40, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = select_display_date(modules, now=now, latest_market_date="2026-06-18")

    assert result["display_trade_date"] == ""
    assert result["candidate_status"] == "incomplete"
    assert "missing:tech_bottleneck_candidates" in result["blocking_reasons"]
```

Update `_ready_modules(...)` in the same file so normal ready fixtures include the new module:

```python
_module(trade_date, "tech_bottleneck_candidates"),
```

- [ ] **Step 2: Write failing Review Queue stale Tech test**

Append to `tests/test_dashboard_review_queue.py`:

```python
def test_review_queue_ignores_stale_tech_candidate_snapshot(monkeypatch, tmp_path):
    from stock_research.dashboard.review_queue import _load_manifest_strategy_rows

    artifact = tmp_path / "strategy_tech_bottleneck_review.csv"
    pd.DataFrame(
        [
            {
                "trade_date": "2026-06-18",
                "asset_id": "000001.SZ",
                "rank": 1,
                "score_total": 90,
                "strategy_id": "tech_bottleneck",
                "strategy_name": "Tech Bottleneck Combo",
            }
        ]
    ).to_csv(artifact, index=False)
    monkeypatch.setattr(
        "stock_research.dashboard.review_queue.load_latest_data_run_manifest",
        lambda trade_date=None: [
            {
                "run_id": "strategy-eod-20260618-local",
                "trade_date": "2026-06-18",
                "module": "strategy_tech_bottleneck",
                "status": "success",
                "artifact_path": str(artifact),
                "metadata": {
                    "candidate_snapshot_latest_date": "2026-06-17",
                    "summary": {},
                },
            }
        ],
    )

    assert _load_manifest_strategy_rows(trade_date="2026-06-18", limit=10) == []
```

- [ ] **Step 3: Run gate tests and verify failures**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_dashboard_display_date_gate.py::test_select_display_date_requires_tech_candidate_snapshot tests/test_dashboard_review_queue.py::test_review_queue_ignores_stale_tech_candidate_snapshot -q
```

Expected:

```text
failed
```

- [ ] **Step 4: Require candidate module in display gate**

In `src/stock_research/dashboard/display_date_gate.py`, add:

```python
REQUIRED_TECH_CANDIDATE_MODULES = {"tech_bottleneck_candidates"}
```

Change `_evaluate_run(...)`:

```python
required_modules = (
    REQUIRED_BASE_MODULES
    | REQUIRED_REVIEW_MODULES
    | REQUIRED_TECH_CANDIDATE_MODULES
    | set(REQUIRED_STRATEGY_MODULES)
)
```

Add Tech snapshot date validation after `contract_failures = _contract_failures(by_module)`:

```python
snapshot_failures = _tech_candidate_snapshot_failures(trade_date, by_module)
```

Change status condition:

```python
elif contract_failures or snapshot_failures:
    display_status = "contract_mismatch"
```

Change `blocking_reasons`:

```python
"blocking_reasons": [f"missing:{module}" for module in missing] + contract_failures + snapshot_failures,
```

Add helper:

```python
def _tech_candidate_snapshot_failures(trade_date: str, by_module: dict[str, dict[str, Any]]) -> list[str]:
    strategy = by_module.get("strategy_tech_bottleneck") or {}
    metadata = strategy.get("metadata") if isinstance(strategy.get("metadata"), dict) else {}
    snapshot_date = str(metadata.get("candidate_snapshot_latest_date") or "")[:10]
    if snapshot_date and snapshot_date != trade_date:
        return [f"tech_bottleneck:candidate_snapshot_stale:{snapshot_date}"]
    return []
```

- [ ] **Step 5: Reject stale Tech rows in Review Queue**

In `src/stock_research/dashboard/review_queue.py`, add this check near the top of `_manifest_strategy_contract_valid(...)` after `strategy_id` is computed:

```python
if strategy_id == "tech_bottleneck":
    trade_date = str(module.get("trade_date") or module.get("latest_trade_date") or "")[:10]
    metadata = module.get("metadata") if isinstance(module.get("metadata"), dict) else {}
    snapshot_date = str(metadata.get("candidate_snapshot_latest_date") or "")[:10]
    if snapshot_date != trade_date:
        return False
```

- [ ] **Step 6: Run readiness and Review Queue tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_dashboard_display_date_gate.py tests/test_dashboard_review_queue.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Commit trust gates**

```bash
git add src/stock_research/dashboard/display_date_gate.py src/stock_research/dashboard/review_queue.py tests/test_dashboard_display_date_gate.py tests/test_dashboard_review_queue.py
git commit -m "fix: gate tech readiness on candidate snapshots"
```

## Task 6: Full Verification And Backfill Command

**Files:**
- Modify only files changed in Tasks 1-5 if verification finds a test failure.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_tech_bottleneck_candidates.py \
  tests/test_serenity_tight3b_c2_experiment.py \
  tests/test_tech_bottleneck_v1.py \
  tests/test_tech_bottleneck_eod.py \
  tests/test_dashboard_display_date_gate.py \
  tests/test_dashboard_review_queue.py \
  tests/test_dashboard_backtests.py \
  tests/test_data_run_manifest.py \
  -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run dashboard build if `dashboard/src` changed during implementation**

Run:

```bash
pnpm --dir dashboard build
```

Expected:

```text
built
```

- [ ] **Step 3: Run a local full rebuild for current formal date**

Use the current platform latest market date from Home. For the June 2026 local baseline, run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli run-tech-bottleneck-eod \
  --start-date 2025-01-01 \
  --end-date 2026-06-17 \
  --base-candidates-path /Users/xiwei/stock_research/outputs/research/tech_bottleneck_candidate_source/2026-06-17/strict_153_st_only_financial_state_candidates.csv \
  --output-dir /Users/xiwei/stock_research/outputs/research/strategy_daily_eod/2026-06-17/tech_bottleneck
```

Expected files:

```text
/Users/xiwei/stock_research/outputs/research/strategy_daily_eod/2026-06-17/tech_bottleneck/tech_bottleneck_daily_candidates.csv
/Users/xiwei/stock_research/outputs/research/strategy_daily_eod/2026-06-17/tech_bottleneck/strategy_tech_bottleneck_review.csv
/Users/xiwei/stock_research/outputs/research/strategy_daily_eod/2026-06-17/tech_bottleneck/strategy_tech_bottleneck_equity.csv
/Users/xiwei/stock_research/outputs/research/strategy_daily_eod/2026-06-17/tech_bottleneck/strategy_tech_bottleneck_positions.csv
/Users/xiwei/stock_research/outputs/research/strategy_daily_eod/2026-06-17/tech_bottleneck/strategy_tech_bottleneck_trades.csv
```

- [ ] **Step 4: Inspect manifest freshness**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python - <<'PY'
from stock_research.data_run_manifest import load_latest_data_run_manifest
rows = load_latest_data_run_manifest(trade_date="2026-06-17")
for row in rows:
    if row["module"] in {"tech_bottleneck_candidates", "strategy_tech_bottleneck"}:
        print(row["module"], row["status"], row["latest_trade_date"], row["metadata"])
PY
```

Expected:

```text
tech_bottleneck_candidates success 2026-06-17 ...
strategy_tech_bottleneck success 2026-06-17 ...
```

The `strategy_tech_bottleneck` metadata must include:

```python
{
    "candidate_snapshot_latest_date": "2026-06-17",
    "candidate_source": "point_in_time_daily_candidates",
    "summary": {
        "engine_version": "tech_bottleneck_v1",
        "universe": "strict_153_st_only_financial_state",
        "frequency": "biweekly",
        "protection_name": "rank_exit_top10_1d",
        "top_n": 5,
        "transaction_cost_bps": 20.0,
        "adjust_type": "hfq",
    },
}
```

- [ ] **Step 5: Browser smoke test Home and Review Queue**

Open `http://127.0.0.1:5174/`.

Expected Home behavior:

```text
策略就绪 3/3
复盘就绪 3/3
Tech Bottleneck Combo appears under 启用策略表现
Tech candidate snapshot stale warnings are absent
```

Open Review Queue.

Expected Review Queue behavior:

```text
Tech Bottleneck rows only appear when strategy_tech_bottleneck metadata candidate_snapshot_latest_date equals the selected review date.
Tech score values come from score_total or bottleneck_score, not ranking placeholders.
```

- [ ] **Step 6: Final commit**

If Tasks 1-5 were committed separately and Task 6 made no code changes, skip this commit. If Task 6 required fixes, commit them:

```bash
git add src tests dashboard
git commit -m "test: verify tech bottleneck point-in-time eod"
```

## Self-Review

**Spec coverage:** This plan covers the confirmed spec requirements: daily point-in-time candidate rows, no future `first_hit_date`/as-of dates, full rebuild by date range, official contract `top_n=5` + `biweekly` + `rank_exit_top10_1d` + `20bps` + `hfq`, manifest module `tech_bottleneck_candidates`, manifest module `strategy_tech_bottleneck`, Home readiness rejection for stale snapshots, Review Queue rejection for stale snapshots, and Strategy Lab snapshot source labeling.

**Placeholder scan:** The plan avoids deferred-work markers and vague implementation language. Each code-changing step includes concrete code blocks or exact line-level replacements.

**Type consistency:** The plan consistently uses `candidate_snapshots`, `bottleneck_score`, `bottleneck_rank`, `candidate_snapshot_latest_date`, `TECH_BOTTLENECK_CANDIDATE_SOURCE`, `build_point_in_time_candidate_snapshots`, `build_serenity_tight3b_c2_experiment_from_rank_frames`, and `build_tech_bottleneck_v1_from_rank_snapshots` across tests and implementation steps.
