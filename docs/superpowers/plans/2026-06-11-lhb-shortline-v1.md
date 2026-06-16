# LHB Shortline V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new `lhb_shortline_v1` backtest engine that recomputes LHB candidate selection, scoring, execution, exits, and account results from database base data on every web run, while using legacy Phase research only as benchmark evidence.

**Architecture:** Add a focused `stock_research.lhb_shortline_v1` module with pure DataFrame functions plus database loaders, then route Dashboard Backtest Lab LHB runs through that engine. Legacy Phase artifacts are not runtime inputs; they are loaded only by a benchmark adapter that reports prior best metrics for comparison.

**Tech Stack:** Python, pandas, psycopg-backed database access through `stock_research.db`, FastAPI dashboard service, existing Dashboard React client, pytest.

---

## File Structure

- Create `src/stock_research/lhb_shortline_v1.py`
  - Owns the executable strategy: config, source loading, candidate scoring, execution simulation, summaries, and artifact writing.
- Modify `src/stock_research/dashboard/backtests.py`
  - Routes `strategy_id == "lhb_shortline"` fresh runs to `lhb_shortline_v1`.
  - Removes the default fresh dependency on Phase14C/Phase18B CSV inputs.
- Modify `src/stock_research/dashboard/strategy_catalog.py`
  - Keeps the visible strategy as LHB Shortline Combo but exposes implementation/version metadata as `lhb_shortline_v1`.
- Modify `dashboard/src/components/BacktestResultDetail.tsx`
  - Shows the engine version, DB coverage, and legacy benchmark comparison.
- Modify `dashboard/src/api/types.ts`
  - Adds typed optional fields for benchmark and data coverage.
- Create `tests/test_lhb_shortline_v1.py`
  - Unit tests for scoring, candidate filtering, execution, exits, costs, position sizing, and benchmark comparison.
- Modify `tests/test_dashboard_backtests.py`
  - Verifies LHB fresh run calls `lhb_shortline_v1` and does not call Phase artifact preparation.
- Modify `dashboard/tests/backtest-lab-workspace.test.tsx`
  - Verifies the UI sends user parameters and renders v1 result metadata.

---

### Task 1: Define V1 Config And Result Contracts

**Files:**
- Create: `src/stock_research/lhb_shortline_v1.py`
- Test: `tests/test_lhb_shortline_v1.py`

- [ ] **Step 1: Write the failing test**

```python
from stock_research.lhb_shortline_v1 import LHBShortlineV1Config


def test_lhb_shortline_v1_config_normalizes_web_parameters():
    config = LHBShortlineV1Config(
        start_date="2026-01-01",
        end_date="2026-06-08",
        top_n=5,
        rebalance_frequency="daily",
        transaction_cost_bps=10,
        max_position_weight=0.2,
        adjust_type="hfq",
    )

    assert config.engine_version == "lhb_shortline_v1"
    assert config.top_n == 5
    assert config.candidate_pool_n == 10
    assert config.position_weight == 0.2
    assert config.round_trip_cost_return == 0.002
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_lhb_shortline_v1.py::test_lhb_shortline_v1_config_normalizes_web_parameters -q`

Expected: FAIL with `ModuleNotFoundError` or missing `LHBShortlineV1Config`.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LHBShortlineV1Config:
    start_date: str
    end_date: str
    top_n: int
    rebalance_frequency: str = "daily"
    transaction_cost_bps: float = 0.0
    max_position_weight: float | None = None
    adjust_type: str = "hfq"
    engine_version: str = "lhb_shortline_v1"

    @property
    def candidate_pool_n(self) -> int:
        return max(int(self.top_n), 10)

    @property
    def position_weight(self) -> float:
        if self.max_position_weight is not None:
            return float(self.max_position_weight)
        return min(1.0 / max(int(self.top_n), 1), 0.10)

    @property
    def round_trip_cost_return(self) -> float:
        return float(self.transaction_cost_bps) * 2.0 / 10000.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_lhb_shortline_v1.py::test_lhb_shortline_v1_config_normalizes_web_parameters -q`

Expected: PASS.

---

### Task 2: Build Candidate Score From Base Tables

**Files:**
- Modify: `src/stock_research/lhb_shortline_v1.py`
- Test: `tests/test_lhb_shortline_v1.py`

- [ ] **Step 1: Write the failing test**

```python
import pandas as pd

from stock_research.lhb_shortline_v1 import build_lhb_shortline_v1_candidates


def test_build_lhb_shortline_v1_candidates_scores_and_filters_lhb_events():
    lhb = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "ts_code": "000001.SZ",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.35,
                "lhb_net_buy_amount": 120_000_000,
                "institution_net_buy": 20_000_000,
                "repeat_on_list_count_3d": 2,
                "lhb_after_reversal": True,
                "lhb_one_day_pump_risk": 0.20,
            },
            {
                "trade_date": "2026-01-05",
                "ts_code": "000002.SZ",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.10,
                "lhb_net_buy_amount": 10_000_000,
                "institution_net_buy": 0,
                "repeat_on_list_count_3d": 0,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": 0.90,
            },
        ]
    )
    technical = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-05",
                "ts_code": "000001.SZ",
                "amount_vs_20d": 1.8,
                "high_to_close_drawdown": -0.01,
            },
            {
                "trade_date": "2026-01-05",
                "ts_code": "000002.SZ",
                "amount_vs_20d": 0.6,
                "high_to_close_drawdown": -0.08,
            },
        ]
    )

    result = build_lhb_shortline_v1_candidates(lhb, technical, candidate_pool_n=10)

    assert list(result["ts_code"]) == ["000001.SZ"]
    assert result.iloc[0]["rank"] == 1
    assert result.iloc[0]["score_total"] > 70
    assert result.iloc[0]["candidate_reason"] == "lhb_capital_plus_structure"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_lhb_shortline_v1.py::test_build_lhb_shortline_v1_candidates_scores_and_filters_lhb_events -q`

Expected: FAIL because `build_lhb_shortline_v1_candidates` is missing.

- [ ] **Step 3: Implement candidate scoring**

```python
import pandas as pd


def _num(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def build_lhb_shortline_v1_candidates(
    lhb_features: pd.DataFrame,
    technical_features: pd.DataFrame,
    *,
    candidate_pool_n: int,
) -> pd.DataFrame:
    if lhb_features.empty:
        return pd.DataFrame(
            columns=["trade_date", "ts_code", "rank", "score_total", "candidate_reason"]
        )
    lhb = lhb_features.copy()
    tech = technical_features.copy()
    lhb["trade_date"] = pd.to_datetime(lhb["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    tech["trade_date"] = pd.to_datetime(tech["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    lhb["ts_code"] = lhb["ts_code"].astype(str).str.upper().str.strip()
    tech["ts_code"] = tech["ts_code"].astype(str).str.upper().str.strip()
    frame = lhb.merge(tech, on=["trade_date", "ts_code"], how="left")

    net_ratio = _num(frame["lhb_net_buy_ratio"]).clip(-1, 1)
    net_amount = (_num(frame["lhb_net_buy_amount"]) / 100_000_000.0).clip(-1, 3)
    inst_buy = (_num(frame["institution_net_buy"]) / 100_000_000.0).clip(-1, 2)
    repeat = _num(frame["repeat_on_list_count_3d"]).clip(0, 5)
    reversal = frame["lhb_after_reversal"].fillna(False).astype(bool).astype(float)
    amount_confirm = _num(frame.get("amount_vs_20d", pd.Series(index=frame.index)), 1.0).clip(0, 3)
    pump_risk = _num(frame["lhb_one_day_pump_risk"]).clip(0, 1)
    drawdown = _num(frame.get("high_to_close_drawdown", pd.Series(index=frame.index))).clip(-1, 0).abs()

    frame["score_total"] = (
        50.0
        + net_ratio * 35.0
        + net_amount * 8.0
        + inst_buy * 6.0
        + repeat * 2.5
        + reversal * 6.0
        + amount_confirm * 2.0
        - pump_risk * 25.0
        - drawdown * 40.0
    )
    eligible = frame["on_lhb"].fillna(False).astype(bool) & pump_risk.lt(0.75)
    frame = frame[eligible].copy()
    frame["candidate_reason"] = "lhb_capital_plus_structure"
    frame = frame.sort_values(["trade_date", "score_total", "ts_code"], ascending=[True, False, True], kind="stable")
    frame["rank"] = frame.groupby("trade_date").cumcount() + 1
    frame = frame[frame["rank"].le(int(candidate_pool_n))]
    return frame.reset_index(drop=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_lhb_shortline_v1.py::test_build_lhb_shortline_v1_candidates_scores_and_filters_lhb_events -q`

Expected: PASS.

---

### Task 3: Add Auction And Intraday Confirmation Score

**Files:**
- Modify: `src/stock_research/lhb_shortline_v1.py`
- Test: `tests/test_lhb_shortline_v1.py`

- [ ] **Step 1: Write the failing test**

```python
import pandas as pd

from stock_research.lhb_shortline_v1 import apply_lhb_shortline_v1_confirmations


def test_apply_lhb_shortline_v1_confirmations_rewards_strong_open_and_intraday():
    candidates = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "ts_code": "000001.SZ", "score_total": 80.0, "rank": 1},
            {"trade_date": "2026-01-05", "ts_code": "000002.SZ", "score_total": 82.0, "rank": 2},
        ]
    )
    auction = pd.DataFrame(
        [
            {"trade_date": "2026-01-06", "ts_code": "000001.SZ", "auction_phase": "open_call", "open": 11.0, "close": 11.0, "prev_close": 10.0, "amount": 30_000_000},
            {"trade_date": "2026-01-06", "ts_code": "000002.SZ", "auction_phase": "open_call", "open": 9.8, "close": 9.8, "prev_close": 10.0, "amount": 1_000_000},
        ]
    )
    intraday = pd.DataFrame(
        [
            {"trade_date": "2026-01-06", "ts_code": "000001.SZ", "first_60m_return": 0.02, "close_to_vwap": 0.01, "intraday_return": 0.03},
            {"trade_date": "2026-01-06", "ts_code": "000002.SZ", "first_60m_return": -0.03, "close_to_vwap": -0.02, "intraday_return": -0.04},
        ]
    )

    result = apply_lhb_shortline_v1_confirmations(candidates, auction, intraday)

    assert list(result.sort_values("final_score", ascending=False)["ts_code"]) == ["000001.SZ", "000002.SZ"]
    assert result.loc[result["ts_code"].eq("000001.SZ"), "confirmation_action"].iloc[0] == "confirm_follow"
    assert result.loc[result["ts_code"].eq("000002.SZ"), "confirmation_action"].iloc[0] == "reject_follow"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_lhb_shortline_v1.py::test_apply_lhb_shortline_v1_confirmations_rewards_strong_open_and_intraday -q`

Expected: FAIL because `apply_lhb_shortline_v1_confirmations` is missing.

- [ ] **Step 3: Implement confirmation scoring**

```python
def apply_lhb_shortline_v1_confirmations(
    candidates: pd.DataFrame,
    auction_open: pd.DataFrame,
    intraday_confirmation: pd.DataFrame,
) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()
    frame = candidates.copy()
    frame["entry_trade_date"] = (pd.to_datetime(frame["trade_date"]) + pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d")
    auction = auction_open.copy()
    auction["trade_date"] = pd.to_datetime(auction["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    auction["ts_code"] = auction["ts_code"].astype(str).str.upper().str.strip()
    auction = auction[auction["auction_phase"].eq("open_call")].copy()
    auction["open_gap"] = _num(auction["open"]) / _num(auction["prev_close"]).replace(0, pd.NA) - 1.0
    auction = auction.rename(columns={"trade_date": "entry_trade_date"})

    intra = intraday_confirmation.copy()
    intra["trade_date"] = pd.to_datetime(intra["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    intra["ts_code"] = intra["ts_code"].astype(str).str.upper().str.strip()
    intra = intra.rename(columns={"trade_date": "entry_trade_date"})

    frame = frame.merge(auction[["entry_trade_date", "ts_code", "open_gap", "amount"]], on=["entry_trade_date", "ts_code"], how="left")
    frame = frame.merge(intra[["entry_trade_date", "ts_code", "first_60m_return", "close_to_vwap", "intraday_return"]], on=["entry_trade_date", "ts_code"], how="left")

    open_gap = _num(frame["open_gap"])
    first_60m = _num(frame["first_60m_return"])
    close_to_vwap = _num(frame["close_to_vwap"])
    intraday = _num(frame["intraday_return"])
    penalty = first_60m.lt(-0.02) | close_to_vwap.lt(-0.015) | intraday.lt(-0.03)
    confirm = first_60m.ge(0.0) & close_to_vwap.ge(0.0) & intraday.ge(0.0)

    frame["confirmation_action"] = "watch_only"
    frame.loc[confirm, "confirmation_action"] = "confirm_follow"
    frame.loc[penalty, "confirmation_action"] = "reject_follow"
    frame["final_score"] = _num(frame["score_total"]) + open_gap.clip(-0.05, 0.08) * 250.0
    frame.loc[confirm, "final_score"] += 12.0
    frame.loc[penalty, "final_score"] -= 60.0
    return frame.sort_values(["trade_date", "final_score", "ts_code"], ascending=[True, False, True], kind="stable").reset_index(drop=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_lhb_shortline_v1.py::test_apply_lhb_shortline_v1_confirmations_rewards_strong_open_and_intraday -q`

Expected: PASS.

---

### Task 4: Implement Executable Backtest Engine

**Files:**
- Modify: `src/stock_research/lhb_shortline_v1.py`
- Test: `tests/test_lhb_shortline_v1.py`

- [ ] **Step 1: Write the failing test**

```python
import pandas as pd
import pytest

from stock_research.lhb_shortline_v1 import LHBShortlineV1Config, run_lhb_shortline_v1_from_frames


def test_run_lhb_shortline_v1_from_frames_applies_topn_weight_cost_and_exit():
    config = LHBShortlineV1Config(
        start_date="2026-01-05",
        end_date="2026-01-10",
        top_n=1,
        transaction_cost_bps=10,
        max_position_weight=0.2,
    )
    candidates = pd.DataFrame(
        [
            {"trade_date": "2026-01-05", "ts_code": "000001.SZ", "final_score": 100.0, "confirmation_action": "confirm_follow"},
            {"trade_date": "2026-01-05", "ts_code": "000002.SZ", "final_score": 90.0, "confirmation_action": "confirm_follow"},
        ]
    )
    daily = pd.DataFrame(
        [
            {"trade_date": "2026-01-06", "ts_code": "000001.SZ", "open": 10.0, "close": 10.5},
            {"trade_date": "2026-01-07", "ts_code": "000001.SZ", "open": 10.6, "close": 11.0},
            {"trade_date": "2026-01-08", "ts_code": "000001.SZ", "open": 11.0, "close": 11.0},
        ]
    )

    result = run_lhb_shortline_v1_from_frames(config=config, scored_candidates=candidates, daily_bars=daily)

    assert result.summary["filled_trade_count"] == 1
    assert result.trades.iloc[0]["ts_code"] == "000001.SZ"
    assert result.trades.iloc[0]["position_weight"] == 0.2
    assert result.trades.iloc[0]["realized_return"] == pytest.approx(0.098)
    assert result.summary["final_equity"] == pytest.approx(1.0196)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_lhb_shortline_v1.py::test_run_lhb_shortline_v1_from_frames_applies_topn_weight_cost_and_exit -q`

Expected: FAIL because `run_lhb_shortline_v1_from_frames` is missing.

- [ ] **Step 3: Implement minimal daily execution engine**

```python
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LHBShortlineV1Result:
    summary: dict[str, Any]
    equity_curve: pd.DataFrame
    positions: pd.DataFrame
    trades: pd.DataFrame


def run_lhb_shortline_v1_from_frames(
    *,
    config: LHBShortlineV1Config,
    scored_candidates: pd.DataFrame,
    daily_bars: pd.DataFrame,
) -> LHBShortlineV1Result:
    if scored_candidates.empty:
        empty = pd.DataFrame()
        return LHBShortlineV1Result(
            summary={"final_equity": 1.0, "total_return": 0.0, "filled_trade_count": 0},
            equity_curve=empty,
            positions=empty,
            trades=empty,
        )
    bars = daily_bars.copy()
    bars["trade_date"] = pd.to_datetime(bars["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    bars["ts_code"] = bars["ts_code"].astype(str).str.upper().str.strip()
    bars = bars.sort_values(["ts_code", "trade_date"], kind="stable")
    by_code = {code: group.reset_index(drop=True) for code, group in bars.groupby("ts_code", sort=False)}

    selected = scored_candidates[~scored_candidates["confirmation_action"].eq("reject_follow")].copy()
    selected = selected.sort_values(["trade_date", "final_score", "ts_code"], ascending=[True, False, True], kind="stable")
    selected = selected.groupby("trade_date", group_keys=False).head(config.top_n)

    trades = []
    for row in selected.to_dict("records"):
        signal_date = str(row["trade_date"])
        code = str(row["ts_code"])
        asset_bars = by_code.get(code, pd.DataFrame())
        future = asset_bars[asset_bars["trade_date"].gt(signal_date)].head(3).reset_index(drop=True)
        if len(future) < 2:
            continue
        entry = float(future.iloc[0]["open"])
        exit_price = float(future.iloc[-1]["close"])
        raw_return = exit_price / entry - 1.0
        realized = raw_return - config.round_trip_cost_return
        trades.append(
            {
                "trade_date": signal_date,
                "ts_code": code,
                "entry_trade_date": future.iloc[0]["trade_date"],
                "exit_trade_date": future.iloc[-1]["trade_date"],
                "entry_price": entry,
                "exit_price": exit_price,
                "raw_return": raw_return,
                "realized_return": realized,
                "position_weight": config.position_weight,
            }
        )
    trade_frame = pd.DataFrame(trades)
    if trade_frame.empty:
        empty = pd.DataFrame()
        return LHBShortlineV1Result(
            summary={"final_equity": 1.0, "total_return": 0.0, "filled_trade_count": 0},
            equity_curve=empty,
            positions=empty,
            trades=trade_frame,
        )
    trade_frame["portfolio_return"] = trade_frame["realized_return"] * trade_frame["position_weight"]
    curve = (
        trade_frame.groupby("exit_trade_date", as_index=False)
        .agg(daily_return=("portfolio_return", "sum"), closed_trade_count=("ts_code", "size"))
        .rename(columns={"exit_trade_date": "trade_date"})
        .sort_values("trade_date", kind="stable")
    )
    curve["equity"] = (1.0 + curve["daily_return"]).cumprod()
    curve["drawdown"] = curve["equity"] / curve["equity"].cummax() - 1.0
    summary = {
        "engine_version": config.engine_version,
        "final_equity": float(curve["equity"].iloc[-1]),
        "total_return": float(curve["equity"].iloc[-1] - 1.0),
        "max_drawdown": float(curve["drawdown"].min()),
        "filled_trade_count": int(len(trade_frame)),
        "win_rate": float((trade_frame["realized_return"] > 0).mean()),
    }
    return LHBShortlineV1Result(summary=summary, equity_curve=curve, positions=trade_frame.copy(), trades=trade_frame)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_lhb_shortline_v1.py::test_run_lhb_shortline_v1_from_frames_applies_topn_weight_cost_and_exit -q`

Expected: PASS.

---

### Task 5: Add Database Loader And Artifact Writer

**Files:**
- Modify: `src/stock_research/lhb_shortline_v1.py`
- Test: `tests/test_lhb_shortline_v1.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

import pandas as pd

from stock_research.lhb_shortline_v1 import LHBShortlineV1Config, write_lhb_shortline_v1_artifacts


def test_write_lhb_shortline_v1_artifacts_writes_reproducible_run_files(tmp_path: Path):
    config = LHBShortlineV1Config(start_date="2026-01-01", end_date="2026-06-08", top_n=5)
    summary = {"engine_version": "lhb_shortline_v1", "final_equity": 1.2}
    candidates = pd.DataFrame([{"trade_date": "2026-01-05", "ts_code": "000001.SZ"}])
    trades = pd.DataFrame([{"trade_date": "2026-01-05", "ts_code": "000001.SZ", "realized_return": 0.1}])
    curve = pd.DataFrame([{"trade_date": "2026-01-06", "equity": 1.02}])

    paths = write_lhb_shortline_v1_artifacts(
        output_dir=tmp_path,
        config=config,
        summary=summary,
        candidates=candidates,
        trades=trades,
        equity_curve=curve,
    )

    assert Path(paths["summary"]).exists()
    assert Path(paths["candidates"]).exists()
    assert Path(paths["trades"]).exists()
    assert Path(paths["equity_curve"]).exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_lhb_shortline_v1.py::test_write_lhb_shortline_v1_artifacts_writes_reproducible_run_files -q`

Expected: FAIL because `write_lhb_shortline_v1_artifacts` is missing.

- [ ] **Step 3: Implement artifact writer**

```python
import json
from pathlib import Path


def write_lhb_shortline_v1_artifacts(
    *,
    output_dir: Path,
    config: LHBShortlineV1Config,
    summary: dict[str, Any],
    candidates: pd.DataFrame,
    trades: pd.DataFrame,
    equity_curve: pd.DataFrame,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": str(output_dir / "lhb_shortline_v1_summary.json"),
        "candidates": str(output_dir / "lhb_shortline_v1_candidates.csv"),
        "trades": str(output_dir / "lhb_shortline_v1_trades.csv"),
        "equity_curve": str(output_dir / "lhb_shortline_v1_equity_curve.csv"),
    }
    Path(paths["summary"]).write_text(
        json.dumps({"config": config.__dict__, "summary": summary}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    candidates.to_csv(paths["candidates"], index=False)
    trades.to_csv(paths["trades"], index=False)
    equity_curve.to_csv(paths["equity_curve"], index=False)
    return paths
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_lhb_shortline_v1.py::test_write_lhb_shortline_v1_artifacts_writes_reproducible_run_files -q`

Expected: PASS.

---

### Task 6: Wire Dashboard Fresh LHB To V1 Engine

**Files:**
- Modify: `src/stock_research/dashboard/backtests.py`
- Test: `tests/test_dashboard_backtests.py`

- [ ] **Step 1: Write the failing test**

```python
def test_run_fresh_backtest_routes_lhb_to_shortline_v1(monkeypatch):
    calls = {}

    def fake_run(payload):
        calls["payload"] = payload
        return {
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline Combo",
            "source_kind": "lhb_shortline_v1",
            "config": {"engine_version": "lhb_shortline_v1", "top_n": 5},
            "summary": {"engine_version": "lhb_shortline_v1", "final_equity": 1.23},
            "equity_curve": [],
            "positions": [],
            "trades": [],
        }

    monkeypatch.setattr(backtests, "run_lhb_shortline_v1_backtest_for_dashboard", fake_run)
    monkeypatch.setattr(
        backtests,
        "_prepare_lhb_phase18c_cli_inputs",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not read legacy Phase CSV")),
    )

    result = backtests.run_fresh_backtest(
        {
            "strategy_id": "lhb_shortline",
            "start_date": "2026-01-01",
            "end_date": "2026-06-08",
            "top_n": 5,
            "rebalance_frequency": "daily",
            "transaction_cost_bps": 10,
            "max_position_weight": 0.2,
        }
    )

    assert result["result_source"] == "lhb_shortline_v1"
    assert result["summary"]["engine_version"] == "lhb_shortline_v1"
    assert calls["payload"]["top_n"] == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_backtests.py::test_run_fresh_backtest_routes_lhb_to_shortline_v1 -q`

Expected: FAIL because `run_lhb_shortline_v1_backtest_for_dashboard` is not wired.

- [ ] **Step 3: Implement routing**

In `src/stock_research/dashboard/backtests.py`, import:

```python
from stock_research.lhb_shortline_v1 import run_lhb_shortline_v1_backtest_for_dashboard
```

Change the LHB branch in `run_fresh_backtest` to:

```python
if strategy_id == "lhb_shortline":
    result = run_lhb_shortline_v1_backtest_for_dashboard(
        {
            "start_date": params.start_date,
            "end_date": params.end_date,
            **run_config,
        }
    )
    return _with_execution_metadata(
        to_json_safe(result),
        mode="fresh",
        source=str(result.get("source_kind") or "lhb_shortline_v1"),
        started_at=started_at,
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_backtests.py::test_run_fresh_backtest_routes_lhb_to_shortline_v1 -q`

Expected: PASS.

---

### Task 7: Add Legacy Benchmark Comparison

**Files:**
- Modify: `src/stock_research/lhb_shortline_v1.py`
- Test: `tests/test_lhb_shortline_v1.py`

- [ ] **Step 1: Write the failing test**

```python
from stock_research.lhb_shortline_v1 import compare_with_legacy_lhb_benchmark


def test_compare_with_legacy_lhb_benchmark_reports_deltas():
    current = {"total_return": 0.50, "final_equity": 1.50, "max_drawdown": -0.20, "filled_trade_count": 20}
    legacy = {"total_return": 0.40, "final_equity": 1.40, "max_drawdown": -0.25, "filled_trade_count": 18}

    result = compare_with_legacy_lhb_benchmark(current, legacy)

    assert result["benchmark_name"] == "legacy_best_lhb_research"
    assert result["total_return_delta"] == 0.10
    assert result["max_drawdown_delta"] == 0.05
    assert result["trade_count_delta"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_lhb_shortline_v1.py::test_compare_with_legacy_lhb_benchmark_reports_deltas -q`

Expected: FAIL because `compare_with_legacy_lhb_benchmark` is missing.

- [ ] **Step 3: Implement benchmark comparison**

```python
def compare_with_legacy_lhb_benchmark(
    current_summary: dict[str, Any],
    legacy_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "benchmark_name": "legacy_best_lhb_research",
        "legacy_total_return": legacy_summary.get("total_return"),
        "legacy_final_equity": legacy_summary.get("final_equity"),
        "legacy_max_drawdown": legacy_summary.get("max_drawdown"),
        "legacy_filled_trade_count": legacy_summary.get("filled_trade_count"),
        "total_return_delta": round(float(current_summary.get("total_return", 0.0)) - float(legacy_summary.get("total_return", 0.0)), 10),
        "final_equity_delta": round(float(current_summary.get("final_equity", 0.0)) - float(legacy_summary.get("final_equity", 0.0)), 10),
        "max_drawdown_delta": round(float(current_summary.get("max_drawdown", 0.0)) - float(legacy_summary.get("max_drawdown", 0.0)), 10),
        "trade_count_delta": int(current_summary.get("filled_trade_count", 0)) - int(legacy_summary.get("filled_trade_count", 0)),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/xiwei/stock_research/.venv/bin/pytest tests/test_lhb_shortline_v1.py::test_compare_with_legacy_lhb_benchmark_reports_deltas -q`

Expected: PASS.

---

### Task 8: Show V1 Metadata In Backtest Lab

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/components/BacktestResultDetail.tsx`
- Test: `dashboard/tests/backtest-lab-workspace.test.tsx`

- [ ] **Step 1: Write the failing frontend test**

```tsx
it('renders LHB shortline v1 engine metadata and benchmark comparison', async () => {
  const result = makeRunResult('lhb_shortline', 'LHB Shortline Combo');
  result.result_source = 'lhb_shortline_v1';
  result.summary = {
    ...result.summary,
    engine_version: 'lhb_shortline_v1',
    final_equity: 1.5,
    legacy_benchmark: {
      benchmark_name: 'legacy_best_lhb_research',
      legacy_final_equity: 1.4,
      final_equity_delta: 0.1,
    },
  };
  render(<BacktestResultDetail result={result} />);

  expect(screen.getByText(/lhb_shortline_v1/i)).toBeInTheDocument();
  expect(screen.getByText(/legacy_best_lhb_research/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd dashboard && pnpm test -- backtest-lab-workspace.test.tsx`

Expected: FAIL because metadata is not rendered.

- [ ] **Step 3: Implement UI display**

Add optional fields to `dashboard/src/api/types.ts`:

```ts
export interface LegacyBenchmarkSummary {
  benchmark_name: string;
  legacy_final_equity?: number;
  final_equity_delta?: number;
  legacy_total_return?: number;
  total_return_delta?: number;
}
```

In `BacktestResultDetail.tsx`, render when present:

```tsx
const engineVersion = getMetric(result, ['engine_version']);
const legacyBenchmark = getMetric(result, ['legacy_benchmark']);
```

Show compact rows:

```tsx
{engineVersion ? <MetricRow label="Engine" value={String(engineVersion)} /> : null}
{legacyBenchmark && typeof legacyBenchmark === 'object' ? (
  <MetricRow label="Benchmark" value={String((legacyBenchmark as { benchmark_name?: string }).benchmark_name ?? 'legacy')} />
) : null}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd dashboard && pnpm test -- backtest-lab-workspace.test.tsx`

Expected: PASS.

---

### Task 9: Full Verification Against User Parameters

**Files:**
- No code change unless verification exposes defects.

- [ ] **Step 1: Run backend unit tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_lhb_shortline_v1.py \
  tests/test_dashboard_backtests.py \
  tests/test_vectorized_topn_backtest.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests and build**

Run:

```bash
cd dashboard
pnpm test -- backtest-lab-workspace.test.tsx client.test.ts
pnpm build
```

Expected: tests PASS and build succeeds.

- [ ] **Step 3: Run real dashboard API benchmark command**

Run:

```bash
curl -sS -X POST http://127.0.0.1:8765/api/backtests/run-fresh \
  -H 'Content-Type: application/json' \
  -d '{
    "strategy_id":"lhb_shortline",
    "start_date":"2026-01-01",
    "end_date":"2026-06-08",
    "top_n":5,
    "rebalance_frequency":"daily",
    "transaction_cost_bps":10,
    "max_positions":null,
    "max_position_weight":0.2,
    "score_version":"manual_v1",
    "adjust_type":"hfq"
  }' | jq '{result_source, elapsed_ms, summary}'
```

Expected:
- `result_source` is `lhb_shortline_v1`.
- `summary.engine_version` is `lhb_shortline_v1`.
- `summary.data_coverage` has nonzero candidate, daily, and minute rows.
- Runtime is not instant replay; elapsed time should reflect real DB loading and strategy computation.

- [ ] **Step 4: Compare against legacy benchmark**

Inspect the API response:

```bash
jq '.summary.legacy_benchmark' /tmp/lhb_shortline_v1_response.json
```

Expected:
- Benchmark object is present.
- Delta fields are present.
- If v1 underperforms materially, create a follow-up tuning task rather than changing benchmark semantics.
