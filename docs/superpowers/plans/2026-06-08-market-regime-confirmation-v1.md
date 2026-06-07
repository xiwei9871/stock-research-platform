# Market Regime Confirmation V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a market regime confirmation layer that converts daily raw market emotion into a smoothed, hysteresis-aware regime signal for weekly mid-trend exposure and diagnostics.

**Architecture:** Create a new frame-first research module, `src/stock_research/market_regime_confirmation_v1.py`, that accepts `market_emotion_state_daily.csv` data and an optional policy-event frame. The module outputs confirmed regime states, exposure targets, segment diagnostics, and an optional backtest comparison using existing `market_style_switch_v1` helpers without changing existing v1 behavior.

**Tech Stack:** Python, pandas, pytest, existing `stock_research.cli`, existing `market_style_switch_v1` price/backtest helpers.

---

## File Structure

- Create `src/stock_research/market_regime_confirmation_v1.py`
  - Owns schema constants, emotion normalization, smoothed feature calculation, policy-event attachment, confirmed regime state machine, diagnostics, output writer, and backtest orchestration.
- Create `tests/test_market_regime_confirmation_v1.py`
  - Unit tests for smoothing, policy impulse confirmation, downgrade hysteresis, weekly exposure dates, diagnostics, output schemas, and backtest integration.
- Modify `src/stock_research/cli.py`
  - Add `market-regime-confirmation-v1-backtest` parser and command dispatch.
- No changes to `market_emotion_state_v1.py` or existing `market_style_switch_v1.py` behavior.

## Proposed Public API

```python
REGIME_COLUMNS = [
    "trade_date",
    "emotion_score",
    "emotion_state",
    "risk_state",
    "emotion_score_5d",
    "emotion_score_10d",
    "emotion_slope_5d",
    "risk_high_days_5d",
    "risk_high_days_10d",
    "hot_or_euphoria_days_5d",
    "panic_or_cold_days_5d",
    "score_rebound_from_20d_low",
    "score_drawdown_from_20d_high",
    "policy_impulse_candidate",
    "policy_strength",
    "market_regime_score",
    "raw_regime_state",
    "confirmed_regime_state",
    "days_since_regime_change",
    "target_exposure",
    "style_bias",
    "rebalance_allowed",
    "transition_reason",
]

def build_market_regime_confirmation_from_frames(
    emotion: pd.DataFrame,
    policy_events: pd.DataFrame | None = None,
    *,
    rebalance_weekday: int = 4,
) -> pd.DataFrame: ...

def run_market_regime_confirmation_v1_backtest(
    *,
    start_date: str,
    end_date: str,
    emotion_path: str | Path,
    funnel_detail_path: str | Path,
    output_dir: str | Path,
    policy_event_path: str | Path | None = None,
    top_n: int = 5,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]: ...
```

### Task 1: Smoothed Daily Regime Features

**Files:**
- Create: `src/stock_research/market_regime_confirmation_v1.py`
- Create: `tests/test_market_regime_confirmation_v1.py`

- [ ] **Step 1: Write failing tests for feature calculation**

Add this to `tests/test_market_regime_confirmation_v1.py`:

```python
import pandas as pd

from stock_research.market_regime_confirmation_v1 import (
    REGIME_COLUMNS,
    build_market_regime_confirmation_from_frames,
)


def _emotion_rows(scores: list[float], states: list[str] | None = None, risks: list[str] | None = None) -> pd.DataFrame:
    states = states or ["neutral"] * len(scores)
    risks = risks or ["medium"] * len(scores)
    return pd.DataFrame(
        [
            {
                "trade_date": f"2026-01-{index + 2:02d}",
                "emotion_score": score,
                "emotion_state": states[index],
                "risk_state": risks[index],
            }
            for index, score in enumerate(scores)
        ]
    )


def test_build_regime_features_smooths_daily_emotion_and_preserves_schema() -> None:
    emotion = _emotion_rows(
        [20, 30, 40, 50, 60, 70],
        states=["panic", "cold", "neutral", "neutral", "hot", "euphoria"],
        risks=["high", "high", "medium", "medium", "low", "low"],
    )

    result = build_market_regime_confirmation_from_frames(emotion)

    assert result.columns.tolist() == REGIME_COLUMNS
    assert result["trade_date"].tolist() == [
        "2026-01-02",
        "2026-01-03",
        "2026-01-04",
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
    ]
    last = result.iloc[-1]
    assert round(last["emotion_score_5d"], 2) == 50.00
    assert round(last["emotion_score_10d"], 2) == 45.00
    assert round(last["emotion_slope_5d"], 2) == 40.00
    assert int(last["risk_high_days_5d"]) == 1
    assert int(last["hot_or_euphoria_days_5d"]) == 2
    assert int(last["panic_or_cold_days_5d"]) == 1
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_market_regime_confirmation_v1.py::test_build_regime_features_smooths_daily_emotion_and_preserves_schema -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stock_research.market_regime_confirmation_v1'`.

- [ ] **Step 3: Implement schema, normalization, and smoothed features**

Create `src/stock_research/market_regime_confirmation_v1.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS


REGIME_COLUMNS = [
    "trade_date",
    "emotion_score",
    "emotion_state",
    "risk_state",
    "emotion_score_5d",
    "emotion_score_10d",
    "emotion_slope_5d",
    "risk_high_days_5d",
    "risk_high_days_10d",
    "hot_or_euphoria_days_5d",
    "panic_or_cold_days_5d",
    "score_rebound_from_20d_low",
    "score_drawdown_from_20d_high",
    "policy_impulse_candidate",
    "policy_strength",
    "market_regime_score",
    "raw_regime_state",
    "confirmed_regime_state",
    "days_since_regime_change",
    "target_exposure",
    "style_bias",
    "rebalance_allowed",
    "transition_reason",
]


def build_market_regime_confirmation_from_frames(
    emotion: pd.DataFrame,
    policy_events: pd.DataFrame | None = None,
    *,
    rebalance_weekday: int = 4,
) -> pd.DataFrame:
    frame = _normalize_emotion(emotion)
    if frame.empty:
        return pd.DataFrame(columns=REGIME_COLUMNS)
    frame = _attach_smoothed_features(frame)
    frame = _attach_policy_events(frame, policy_events)
    frame = _attach_raw_regime(frame)
    frame = _attach_confirmed_regime(frame)
    frame = _attach_trading_policy(frame, rebalance_weekday=rebalance_weekday)
    return frame[REGIME_COLUMNS].reset_index(drop=True)


def _normalize_emotion(emotion: pd.DataFrame) -> pd.DataFrame:
    frame = emotion.copy()
    for column, default in {
        "trade_date": pd.NA,
        "emotion_score": 50.0,
        "emotion_state": "neutral",
        "risk_state": "medium",
    }.items():
        if column not in frame.columns:
            frame[column] = default
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")
    frame["emotion_score"] = pd.to_numeric(frame["emotion_score"], errors="coerce").fillna(50.0).clip(0.0, 100.0)
    frame["emotion_state"] = frame["emotion_state"].fillna("neutral").astype(str)
    frame["risk_state"] = frame["risk_state"].fillna("medium").astype(str)
    frame = frame.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)
    return frame[["trade_date", "emotion_score", "emotion_state", "risk_state"]]


def _attach_smoothed_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    score = result["emotion_score"].astype(float)
    result["emotion_score_5d"] = score.rolling(5, min_periods=1).mean()
    result["emotion_score_10d"] = score.rolling(10, min_periods=1).mean()
    result["emotion_slope_5d"] = score - score.shift(5).fillna(score.iloc[0])
    result["risk_high_days_5d"] = result["risk_state"].eq("high").rolling(5, min_periods=1).sum().astype(int)
    result["risk_high_days_10d"] = result["risk_state"].eq("high").rolling(10, min_periods=1).sum().astype(int)
    result["hot_or_euphoria_days_5d"] = (
        result["emotion_state"].isin(["hot", "euphoria"]).rolling(5, min_periods=1).sum().astype(int)
    )
    result["panic_or_cold_days_5d"] = (
        result["emotion_state"].isin(["panic", "cold"]).rolling(5, min_periods=1).sum().astype(int)
    )
    low_20 = score.rolling(20, min_periods=1).min()
    high_20 = score.rolling(20, min_periods=1).max()
    result["score_rebound_from_20d_low"] = score - low_20
    result["score_drawdown_from_20d_high"] = score - high_20
    return result


def _attach_policy_events(frame: pd.DataFrame, policy_events: pd.DataFrame | None) -> pd.DataFrame:
    result = frame.copy()
    result["policy_impulse_candidate"] = False
    result["policy_strength"] = 0.0
    return result


def _attach_raw_regime(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["market_regime_score"] = result["emotion_score_10d"]
    result["raw_regime_state"] = result["market_regime_score"].map(_raw_regime_state)
    return result


def _raw_regime_state(score: float) -> str:
    if score < 35:
        return "bear"
    if score < 45:
        return "weak_repair"
    if score < 60:
        return "neutral"
    if score < 75:
        return "bull_trend"
    return "overheated"


def _attach_confirmed_regime(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["confirmed_regime_state"] = result["raw_regime_state"]
    result["days_since_regime_change"] = _days_since_change(result["confirmed_regime_state"])
    result["transition_reason"] = "raw_initial"
    return result


def _days_since_change(states: pd.Series) -> list[int]:
    days = []
    current = None
    count = 0
    for state in states.astype(str):
        if state != current:
            current = state
            count = 0
        days.append(count)
        count += 1
    return days


def _attach_trading_policy(frame: pd.DataFrame, *, rebalance_weekday: int) -> pd.DataFrame:
    result = frame.copy()
    result["target_exposure"] = result["confirmed_regime_state"].map(_target_exposure).astype(float)
    result["style_bias"] = result["confirmed_regime_state"].map(_style_bias)
    result["rebalance_allowed"] = pd.to_datetime(result["trade_date"]).dt.weekday.eq(rebalance_weekday)
    return result


def _target_exposure(state: str) -> float:
    return {
        "bear": 0.2,
        "weak_repair": 0.5,
        "neutral": 0.7,
        "bull_impulse": 1.0,
        "bull_trend": 1.0,
        "trend_decay": 0.7,
        "overheated": 0.8,
    }.get(state, 0.6)


def _style_bias(state: str) -> str:
    return {
        "bear": "cash_defensive",
        "weak_repair": "reduced_growth",
        "neutral": "balanced_mid_trend",
        "bull_impulse": "growth_fast_rerisk",
        "bull_trend": "growth_mid_trend",
        "trend_decay": "hold_leaders_reduce_new",
        "overheated": "growth_tight_risk",
    }.get(state, "balanced_mid_trend")
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```bash
.venv/bin/pytest tests/test_market_regime_confirmation_v1.py::test_build_regime_features_smooths_daily_emotion_and_preserves_schema -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/market_regime_confirmation_v1.py tests/test_market_regime_confirmation_v1.py
git commit -m "feat: add market regime smoothing features"
```

### Task 2: Policy Impulse And Regime Hysteresis

**Files:**
- Modify: `src/stock_research/market_regime_confirmation_v1.py`
- Modify: `tests/test_market_regime_confirmation_v1.py`

- [ ] **Step 1: Write failing tests for policy confirmation and downgrade hysteresis**

Append to `tests/test_market_regime_confirmation_v1.py`:

```python
def test_policy_impulse_requires_market_response_and_accelerates_rerisk() -> None:
    emotion = _emotion_rows(
        [25, 26, 28, 32, 45, 58, 64],
        states=["panic", "cold", "cold", "neutral", "hot", "hot", "euphoria"],
        risks=["high", "high", "high", "medium", "medium", "low", "low"],
    )
    policy = pd.DataFrame(
        [
            {
                "event_date": "2026-01-05",
                "event_type": "financial_policy",
                "policy_strength": 0.9,
                "description": "liquidity support",
                "source": "manual",
            }
        ]
    )

    result = build_market_regime_confirmation_from_frames(emotion, policy)

    impulse_rows = result[result["confirmed_regime_state"] == "bull_impulse"]
    assert impulse_rows["trade_date"].tolist() == ["2026-01-06", "2026-01-07"]
    assert impulse_rows["target_exposure"].tolist() == [1.0, 1.0]
    assert bool(result.loc[result["trade_date"] == "2026-01-05", "policy_impulse_candidate"].iloc[0]) is True


def test_confirmed_regime_does_not_downgrade_on_one_bad_day() -> None:
    emotion = _emotion_rows(
        [70, 72, 74, 75, 73, 71, 30, 68, 67],
        states=["hot", "hot", "euphoria", "euphoria", "hot", "hot", "panic", "hot", "hot"],
        risks=["low", "low", "low", "low", "low", "low", "high", "low", "low"],
    )

    result = build_market_regime_confirmation_from_frames(emotion)

    bad_day = result.loc[result["trade_date"] == "2026-01-08"].iloc[0]
    assert bad_day["raw_regime_state"] in {"neutral", "weak_repair", "bear"}
    assert bad_day["confirmed_regime_state"] in {"bull_trend", "overheated"}
    assert bad_day["transition_reason"] == "downgrade_wait_for_confirmation"
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_market_regime_confirmation_v1.py::test_policy_impulse_requires_market_response_and_accelerates_rerisk tests/test_market_regime_confirmation_v1.py::test_confirmed_regime_does_not_downgrade_on_one_bad_day -q
```

Expected: FAIL because policy events are ignored and confirmed regime equals raw regime.

- [ ] **Step 3: Implement policy attachment and confirmation state machine**

Replace `_attach_policy_events` and `_attach_confirmed_regime` in `src/stock_research/market_regime_confirmation_v1.py` with:

```python
REGIME_RANK = {
    "bear": 0,
    "weak_repair": 1,
    "neutral": 2,
    "trend_decay": 3,
    "bull_trend": 4,
    "bull_impulse": 5,
    "overheated": 6,
}


def _attach_policy_events(frame: pd.DataFrame, policy_events: pd.DataFrame | None) -> pd.DataFrame:
    result = frame.copy()
    result["policy_impulse_candidate"] = False
    result["policy_strength"] = 0.0
    if policy_events is None or policy_events.empty:
        return result

    events = policy_events.copy()
    events["event_date"] = pd.to_datetime(events["event_date"], errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")
    events["policy_strength"] = pd.to_numeric(events.get("policy_strength"), errors="coerce").fillna(0.0).clip(0.0, 1.0)
    events = events.dropna(subset=["event_date"])
    strength_by_date = events.groupby("event_date")["policy_strength"].max()
    for date, strength in strength_by_date.items():
        mask = result["trade_date"].between(date, _shift_trade_date(result, date, 2))
        result.loc[mask, "policy_impulse_candidate"] = strength >= 0.7
        result.loc[mask, "policy_strength"] = result.loc[mask, "policy_strength"].clip(lower=float(strength))
    return result


def _shift_trade_date(frame: pd.DataFrame, start_date: str, offset: int) -> str:
    dates = frame["trade_date"].tolist()
    if start_date not in dates:
        later = [date for date in dates if date >= start_date]
        return later[min(offset, len(later) - 1)] if later else start_date
    index = dates.index(start_date)
    return dates[min(index + offset, len(dates) - 1)]


def _attach_raw_regime(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    base = result["emotion_score_10d"] + result["emotion_slope_5d"].clip(-20, 20) * 0.35
    base = base - result["risk_high_days_5d"] * 2.0 + result["policy_strength"] * 8.0
    result["market_regime_score"] = base.clip(0.0, 100.0)
    result["raw_regime_state"] = result.apply(_raw_regime_state_from_row, axis=1)
    return result


def _raw_regime_state_from_row(row: pd.Series) -> str:
    if bool(row.get("policy_impulse_candidate")) and row.get("emotion_slope_5d", 0.0) >= 15 and row.get("emotion_score", 0.0) >= 45:
        return "bull_impulse"
    score = float(row.get("market_regime_score", 50.0))
    if score < 35:
        return "bear"
    if score < 45:
        return "weak_repair"
    if score < 60:
        return "neutral"
    if score < 75:
        return "bull_trend"
    return "overheated"


def _attach_confirmed_regime(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    confirmed = []
    reasons = []
    current = str(result.iloc[0]["raw_regime_state"])
    pending_state = current
    pending_count = 0

    for _, row in result.iterrows():
        raw = str(row["raw_regime_state"])
        if raw == current:
            pending_state = raw
            pending_count = 0
            confirmed.append(current)
            reasons.append("unchanged")
            continue

        raw_rank = REGIME_RANK.get(raw, 2)
        current_rank = REGIME_RANK.get(current, 2)
        if raw != pending_state:
            pending_state = raw
            pending_count = 1
        else:
            pending_count += 1

        if raw == "bull_impulse" and pending_count >= 1:
            current = "bull_impulse"
            pending_count = 0
            confirmed.append(current)
            reasons.append("policy_impulse_confirmed")
        elif raw_rank > current_rank and pending_count >= 2:
            current = "bull_trend" if current == "bull_impulse" and raw in {"bull_trend", "overheated"} else raw
            pending_count = 0
            confirmed.append(current)
            reasons.append("upgrade_confirmed")
        elif raw_rank < current_rank and pending_count >= 4:
            current = "trend_decay" if current in {"bull_impulse", "bull_trend", "overheated"} and raw_rank >= 1 else raw
            pending_count = 0
            confirmed.append(current)
            reasons.append("downgrade_confirmed")
        else:
            confirmed.append(current)
            reasons.append("downgrade_wait_for_confirmation" if raw_rank < current_rank else "upgrade_wait_for_confirmation")

    result["confirmed_regime_state"] = confirmed
    result["days_since_regime_change"] = _days_since_change(result["confirmed_regime_state"])
    result["transition_reason"] = reasons
    return result
```

- [ ] **Step 4: Run the regime tests and fix only behavior required by tests**

Run:

```bash
.venv/bin/pytest tests/test_market_regime_confirmation_v1.py -q
```

Expected: all tests in this file PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/market_regime_confirmation_v1.py tests/test_market_regime_confirmation_v1.py
git commit -m "feat: confirm market regime with policy hysteresis"
```

### Task 3: Diagnostics And Output Writer

**Files:**
- Modify: `src/stock_research/market_regime_confirmation_v1.py`
- Modify: `tests/test_market_regime_confirmation_v1.py`

- [ ] **Step 1: Write failing tests for diagnostic windows and CSV output**

Append:

```python
from pathlib import Path

from stock_research.market_regime_confirmation_v1 import write_market_regime_confirmation_outputs


def test_write_outputs_includes_segment_diagnostics_and_markdown_report(tmp_path: Path) -> None:
    regime = build_market_regime_confirmation_from_frames(
        pd.DataFrame(
            [
                {"trade_date": "2024-09-23", "emotion_score": 30, "emotion_state": "cold", "risk_state": "high"},
                {"trade_date": "2024-09-24", "emotion_score": 45, "emotion_state": "neutral", "risk_state": "medium"},
                {"trade_date": "2024-09-25", "emotion_score": 60, "emotion_state": "hot", "risk_state": "low"},
                {"trade_date": "2024-11-11", "emotion_score": 55, "emotion_state": "neutral", "risk_state": "medium"},
            ]
        ),
        pd.DataFrame([{"event_date": "2024-09-24", "policy_strength": 0.9}]),
    )

    paths = write_market_regime_confirmation_outputs(regime, output_dir=tmp_path)

    assert paths["regime_path"].name == "market_regime_confirmation_daily.csv"
    assert paths["segment_diagnostics_path"].name == "market_regime_segment_diagnostics.csv"
    assert paths["transition_path"].name == "market_regime_transitions.csv"
    assert paths["report_path"].name == "market_regime_confirmation_v1_report.md"
    assert pd.read_csv(paths["regime_path"]).columns.tolist() == REGIME_COLUMNS
    segment = pd.read_csv(paths["segment_diagnostics_path"])
    assert {"segment_name", "days", "avg_target_exposure"}.issubset(segment.columns)
    assert paths["report_path"].read_text(encoding="utf-8").startswith("# Market Regime Confirmation V1 Report")
```

- [ ] **Step 2: Run the output test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_market_regime_confirmation_v1.py::test_write_outputs_includes_segment_diagnostics_and_markdown_report -q
```

Expected: FAIL because `write_market_regime_confirmation_outputs` is missing.

- [ ] **Step 3: Implement diagnostics and writer**

Append to `src/stock_research/market_regime_confirmation_v1.py`:

```python
SEGMENT_WINDOWS = [
    ("pre_924_2024", "2024-01-01", "2024-09-23"),
    ("policy_rally_2024", "2024-09-24", "2024-11-08"),
    ("post_rally_2024", "2024-11-11", "2024-12-31"),
    ("post_2025", "2025-01-01", "2099-12-31"),
    ("full_period", "1900-01-01", "2099-12-31"),
]


def build_segment_diagnostics(regime: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, start, end in SEGMENT_WINDOWS:
        frame = regime[regime["trade_date"].between(start, end)].copy()
        if frame.empty:
            rows.append(
                {
                    "segment_name": name,
                    "start_date": start,
                    "end_date": end,
                    "days": 0,
                    "avg_target_exposure": 0.0,
                    "dominant_regime": "",
                    "regime_changes": 0,
                    "raw_confirmed_disagree_days": 0,
                }
            )
            continue
        rows.append(
            {
                "segment_name": name,
                "start_date": frame["trade_date"].min(),
                "end_date": frame["trade_date"].max(),
                "days": int(len(frame)),
                "avg_target_exposure": float(frame["target_exposure"].mean()),
                "dominant_regime": str(frame["confirmed_regime_state"].mode().iloc[0]),
                "regime_changes": int(frame["confirmed_regime_state"].ne(frame["confirmed_regime_state"].shift()).sum()),
                "raw_confirmed_disagree_days": int(frame["raw_regime_state"].ne(frame["confirmed_regime_state"]).sum()),
            }
        )
    return pd.DataFrame(rows)


def build_transition_diagnostics(regime: pd.DataFrame) -> pd.DataFrame:
    frame = regime.copy()
    changed = frame["confirmed_regime_state"].ne(frame["confirmed_regime_state"].shift())
    return frame.loc[
        changed,
        ["trade_date", "raw_regime_state", "confirmed_regime_state", "target_exposure", "style_bias", "transition_reason"],
    ].reset_index(drop=True)


def write_market_regime_confirmation_outputs(regime: pd.DataFrame, *, output_dir: str | Path) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    normalized = regime.copy()
    segment = build_segment_diagnostics(normalized)
    transitions = build_transition_diagnostics(normalized)
    paths = {
        "regime_path": output_path / "market_regime_confirmation_daily.csv",
        "segment_diagnostics_path": output_path / "market_regime_segment_diagnostics.csv",
        "transition_path": output_path / "market_regime_transitions.csv",
        "report_path": output_path / "market_regime_confirmation_v1_report.md",
    }
    normalized.to_csv(paths["regime_path"], index=False)
    segment.to_csv(paths["segment_diagnostics_path"], index=False)
    transitions.to_csv(paths["transition_path"], index=False)
    paths["report_path"].write_text(_render_report(normalized, segment, transitions), encoding="utf-8")
    return paths


def _render_report(regime: pd.DataFrame, segment: pd.DataFrame, transitions: pd.DataFrame) -> str:
    return "\n".join(
        [
            "# Market Regime Confirmation V1 Report",
            "",
            "## Segment Diagnostics",
            _frame_to_markdown(segment),
            "",
            "## Confirmed Regime Distribution",
            _frame_to_markdown(regime["confirmed_regime_state"].value_counts().rename_axis("state").reset_index(name="days")),
            "",
            "## Transitions",
            _frame_to_markdown(transitions),
            "",
        ]
    )


def _frame_to_markdown(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_No rows._"
    try:
        return frame.to_markdown(index=False)
    except ImportError:
        return frame.to_csv(index=False)
```

- [ ] **Step 4: Run tests for the module**

Run:

```bash
.venv/bin/pytest tests/test_market_regime_confirmation_v1.py -q
```

Expected: all tests in this file PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/market_regime_confirmation_v1.py tests/test_market_regime_confirmation_v1.py
git commit -m "feat: write market regime diagnostics"
```

### Task 4: Backtest Integration

**Files:**
- Modify: `src/stock_research/market_regime_confirmation_v1.py`
- Modify: `tests/test_market_regime_confirmation_v1.py`

- [ ] **Step 1: Write failing test for backtest integration with fixed and regime exposure strategies**

Append:

```python
from stock_research.market_regime_confirmation_v1 import run_regime_confirmation_backtest_from_frames


def _funnel_for_dates(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": date,
                "asset_id": "G1",
                "stock_name": "科技A",
                "industry_name": "软件",
                "mid_trend_funnel_score": 90,
                "shadow_top10_rank": 1,
                "volatility_20_score": 60,
                "max_drawdown_20_score": 60,
                "ma60_slope_score": 80,
                "score_total": 90,
            }
            for date in dates
        ]
    )


def test_regime_backtest_applies_confirmed_exposure_to_mid_trend_returns() -> None:
    emotion = _emotion_rows(
        [20, 20, 20, 70, 72],
        states=["panic", "panic", "panic", "hot", "hot"],
        risks=["high", "high", "high", "low", "low"],
    )
    dates = emotion["trade_date"].tolist()
    prices = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": "G1", "close": 100.0},
            {"trade_date": "2026-01-03", "asset_id": "G1", "close": 90.0},
            {"trade_date": "2026-01-04", "asset_id": "G1", "close": 81.0},
            {"trade_date": "2026-01-05", "asset_id": "G1", "close": 89.1},
            {"trade_date": "2026-01-06", "asset_id": "G1", "close": 98.01},
            {"trade_date": "2026-01-07", "asset_id": "G1", "close": 107.811},
        ]
    )

    result = run_regime_confirmation_backtest_from_frames(
        emotion=emotion,
        funnel=_funnel_for_dates(dates),
        prices=prices,
        start_date="2026-01-02",
        end_date="2026-01-06",
        top_n=1,
    )

    summary = result["summary"].set_index("strategy_family")
    assert "fixed_mid_trend" in summary.index
    assert "regime_confirmed_exposure" in summary.index
    assert summary.loc["regime_confirmed_exposure", "max_drawdown"] > summary.loc["fixed_mid_trend", "max_drawdown"]
```

- [ ] **Step 2: Run the backtest test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_market_regime_confirmation_v1.py::test_regime_backtest_applies_confirmed_exposure_to_mid_trend_returns -q
```

Expected: FAIL because `run_regime_confirmation_backtest_from_frames` is missing.

- [ ] **Step 3: Implement backtest orchestration**

Append:

```python
def run_regime_confirmation_backtest_from_frames(
    *,
    emotion: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    policy_events: pd.DataFrame | None = None,
    top_n: int = 5,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    from stock_research.market_style_switch_v1 import (
        build_growth_momentum_candidates,
        _build_strategy_selection,
        _filter_date_range,
        _simulate_equal_weight_daily,
        _summarize_equity,
    )

    regime = build_market_regime_confirmation_from_frames(emotion, policy_events)
    regime = regime[regime["trade_date"].between(start_date, end_date)].reset_index(drop=True)
    growth = _filter_date_range(build_growth_momentum_candidates(funnel, top_n=max(top_n, 10)), start_date, end_date)

    style_state = regime.rename(
        columns={
            "confirmed_regime_state": "style_state",
        }
    )[["trade_date", "emotion_state", "risk_state", "emotion_score"]].copy()
    style_state["style_state"] = "growth_momentum"
    style_state["position_budget_hint"] = "full"
    empty = pd.DataFrame(columns=growth.columns)
    fixed_selection = _build_strategy_selection(style_state, growth, empty, empty, "fixed_mid_trend", top_n)
    regime_selection = fixed_selection.copy()
    exposure_by_date = regime.set_index("trade_date")["target_exposure"].to_dict()
    regime_selection["strategy_family"] = "regime_confirmed_exposure"
    regime_selection["invested_weight"] = regime_selection["trade_date"].map(exposure_by_date).fillna(0.6)

    equity = pd.concat(
        [
            _simulate_equal_weight_daily(prices, fixed_selection, strategy_family="fixed_mid_trend"),
            _simulate_equal_weight_daily(prices, regime_selection, strategy_family="regime_confirmed_exposure"),
        ],
        ignore_index=True,
    )
    summary = _summarize_equity(equity)
    paths = {}
    if output_dir is not None:
        paths = write_market_regime_confirmation_outputs(regime, output_dir=output_dir)
        equity.to_csv(Path(output_dir) / "market_regime_backtest_equity.csv", index=False)
        summary.to_csv(Path(output_dir) / "market_regime_backtest_summary.csv", index=False)
    return {"regime": regime, "equity": equity, "summary": summary, "paths": paths}
```

- [ ] **Step 4: Run the module tests and existing dependent tests**

Run:

```bash
.venv/bin/pytest tests/test_market_regime_confirmation_v1.py tests/test_market_style_switch_v1.py -q
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/market_regime_confirmation_v1.py tests/test_market_regime_confirmation_v1.py
git commit -m "feat: backtest confirmed market regime exposure"
```

### Task 5: CLI And Full-Range Research Run

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/market_regime_confirmation_v1.py`
- Modify: `tests/test_market_regime_confirmation_v1.py`

- [ ] **Step 1: Add failing CLI parser test**

Append:

```python
def test_cli_help_includes_market_regime_confirmation_command() -> None:
    import subprocess

    result = subprocess.run(
        [".venv/bin/python", "-m", "stock_research.cli", "market-regime-confirmation-v1-backtest", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--emotion-path" in result.stdout
    assert "--policy-event-path" in result.stdout
```

- [ ] **Step 2: Run CLI help test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_market_regime_confirmation_v1.py::test_cli_help_includes_market_regime_confirmation_command -q
```

Expected: FAIL because the CLI command is missing.

- [ ] **Step 3: Implement file-level backtest runner**

Append to `src/stock_research/market_regime_confirmation_v1.py`:

```python
def run_market_regime_confirmation_v1_backtest(
    *,
    start_date: str,
    end_date: str,
    emotion_path: str | Path,
    funnel_detail_path: str | Path,
    output_dir: str | Path,
    policy_event_path: str | Path | None = None,
    top_n: int = 5,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    from stock_research.market_style_switch_v1 import load_style_switch_prices

    emotion = pd.read_csv(emotion_path, low_memory=False)
    funnel = pd.read_csv(funnel_detail_path, low_memory=False)
    policy_events = pd.read_csv(policy_event_path) if policy_event_path else None
    prices = load_style_switch_prices(start_date, end_date, adjust_type=adjust_type, service=service)
    return run_regime_confirmation_backtest_from_frames(
        emotion=emotion,
        funnel=funnel,
        prices=prices,
        policy_events=policy_events,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        top_n=top_n,
    )
```

- [ ] **Step 4: Add CLI parser and dispatch**

In `src/stock_research/cli.py`, add imports inside the dispatch branch to avoid startup cost. Add parser near `market-style-switch-v1-backtest` or `market-emotion-state-v1-backfill`:

```python
    market_regime_confirmation = subparsers.add_parser("market-regime-confirmation-v1-backtest")
    market_regime_confirmation.add_argument("--start-date", required=True)
    market_regime_confirmation.add_argument("--end-date", required=True)
    market_regime_confirmation.add_argument("--emotion-path", required=True)
    market_regime_confirmation.add_argument("--funnel-detail-path", required=True)
    market_regime_confirmation.add_argument("--output-dir", required=True)
    market_regime_confirmation.add_argument("--policy-event-path")
    market_regime_confirmation.add_argument("--top-n", type=int, default=5)
    market_regime_confirmation.add_argument("--adjust-type", default="hfq")
```

Add dispatch:

```python
    elif args.command == "market-regime-confirmation-v1-backtest":
        from stock_research.market_regime_confirmation_v1 import run_market_regime_confirmation_v1_backtest

        result = run_market_regime_confirmation_v1_backtest(
            start_date=args.start_date,
            end_date=args.end_date,
            emotion_path=args.emotion_path,
            funnel_detail_path=args.funnel_detail_path,
            output_dir=args.output_dir,
            policy_event_path=args.policy_event_path,
            top_n=args.top_n,
            adjust_type=args.adjust_type,
        )
        print(f"market_regime_confirmation|summary|{result['paths'].get('regime_path')}")
        print(f"market_regime_confirmation|regime_rows|{len(result['regime'])}")
        print(f"market_regime_confirmation|equity_rows|{len(result['equity'])}")
        print(f"market_regime_confirmation|output_dir|{args.output_dir}")
```

- [ ] **Step 5: Run CLI help test and full test set for touched modules**

Run:

```bash
.venv/bin/pytest tests/test_market_regime_confirmation_v1.py tests/test_market_style_switch_v1.py tests/test_market_emotion_state_v1.py -q
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/market_regime_confirmation_v1.py src/stock_research/cli.py tests/test_market_regime_confirmation_v1.py
git commit -m "feat: add market regime confirmation cli"
```

- [ ] **Step 7: Run full 2023-present research backtest**

Create a manual policy event CSV if one does not already exist:

```bash
mkdir -p data/manual
printf "event_date,event_type,policy_strength,description,source\n2024-09-24,financial_policy,0.9,924 financial policy support,manual\n" > data/manual/policy_events_market_regime_v1.csv
```

Run:

```bash
.venv/bin/python -m stock_research.cli market-regime-confirmation-v1-backtest \
  --start-date 2023-01-03 \
  --end-date 2026-06-05 \
  --emotion-path outputs/research/market_emotion_state_v1_20230103_20260605/market_emotion_state_daily.csv \
  --funnel-detail-path outputs/research/mid_trend_watch_funnel_20230103_20260605_aligned/mid_trend_watch_funnel_detail.csv \
  --policy-event-path data/manual/policy_events_market_regime_v1.csv \
  --output-dir outputs/research/market_regime_confirmation_v1_20230103_20260605 \
  --top-n 5 \
  --adjust-type hfq
```

Expected output includes:

```text
market_regime_confirmation|summary|outputs/research/market_regime_confirmation_v1_20230103_20260605/market_regime_confirmation_daily.csv
market_regime_confirmation|regime_rows|
market_regime_confirmation|equity_rows|
market_regime_confirmation|output_dir|outputs/research/market_regime_confirmation_v1_20230103_20260605
```

- [ ] **Step 8: Inspect full-run outputs**

Run:

```bash
sed -n '1,80p' outputs/research/market_regime_confirmation_v1_20230103_20260605/market_regime_backtest_summary.csv
sed -n '1,120p' outputs/research/market_regime_confirmation_v1_20230103_20260605/market_regime_segment_diagnostics.csv
sed -n '1,120p' outputs/research/market_regime_confirmation_v1_20230103_20260605/market_regime_transitions.csv
```

Expected: summary contains `fixed_mid_trend` and `regime_confirmed_exposure`; segment diagnostics contain `pre_924_2024`, `policy_rally_2024`, `post_rally_2024`, `post_2025`, and `full_period`.

## Self-Review

Spec coverage:

- Raw daily emotion is preserved as observational data in Task 1.
- 5d/10d smoothing, slope, rolling risk counts, rebound/drawdown features are implemented in Task 1.
- Policy event modifier and market-response confirmation are implemented in Task 2.
- Hysteresis and downgrade/upgrade confirmation are implemented in Task 2.
- Weekly rebalance marker and target exposure/style bias are implemented in Task 1 and used in later diagnostics.
- Segment diagnostics for the requested 2024 and 2025-present windows are implemented in Task 3.
- Backtest comparison against fixed mid trend and confirmed-exposure overlay is implemented in Task 4.
- CLI and full-range run are implemented in Task 5.

Scope control:

- The plan does not optimize defensive stock sleeves.
- The plan does not add machine learning.
- The plan does not make policy events alone sufficient to buy.
- The plan does not alter stock-level sell rules.
- The plan does not force daily portfolio-level rebalance.

Type consistency:

- All tasks use `confirmed_regime_state`, `target_exposure`, `style_bias`, and `policy_impulse_candidate` consistently.
- Output filenames are consistent across writer, CLI output, and inspection commands.
