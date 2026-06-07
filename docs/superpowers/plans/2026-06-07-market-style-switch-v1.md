# Market Style Switch V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a research-layer style switching framework that uses market emotion state to choose growth, balanced, defensive-proxy, or wait/cash-like selection style without mixing this decision with position sizing.

**Architecture:** Add one focused `market_style_switch_v1` research module with pure frame-based functions, a database/file-backed runner, and a CLI command. Reuse existing mid-trend candidates as the growth sleeve, build a defensive/yield proxy sleeve from industry and low-risk technical features, then run comparative attribution families that isolate style switching from exposure control.

**Tech Stack:** Python, pandas, existing `stock_research.db`, existing portfolio simulation helpers where practical, argparse CLI, pytest.

---

## File Structure

- Create `src/stock_research/market_style_switch_v1.py`
  - Style-state mapping.
  - Growth candidate normalization.
  - Defensive proxy candidate scoring.
  - Rotation balanced candidate composition.
  - Anchor diagnostics.
  - Lightweight comparative backtest/attribution writer.
- Create `tests/test_market_style_switch_v1.py`
  - Unit tests for style mapping, defensive candidate scoring, rotation composition, anchor diagnostics, and output writing.
- Modify `src/stock_research/cli.py`
  - Add `market-style-switch-v1-backtest`.
  - Dispatch to `run_market_style_switch_v1_backtest`.
- Generated research outputs:
  - `outputs/research/market_style_switch_v1_20230103_20260605/market_style_state_daily.csv`
  - `outputs/research/market_style_switch_v1_20230103_20260605/growth_momentum_candidates.csv`
  - `outputs/research/market_style_switch_v1_20230103_20260605/defensive_yield_proxy_candidates.csv`
  - `outputs/research/market_style_switch_v1_20230103_20260605/rotation_balanced_candidates.csv`
  - `outputs/research/market_style_switch_v1_20230103_20260605/anchor_diagnostics.csv`
  - `outputs/research/market_style_switch_v1_20230103_20260605/style_switch_backtest_summary.csv`
  - `outputs/research/market_style_switch_v1_20230103_20260605/style_switch_year_breakdown.csv`
  - `outputs/research/market_style_switch_v1_20230103_20260605/style_switch_emotion_breakdown.csv`
  - `outputs/research/market_style_switch_v1_20230103_20260605/market_style_switch_v1_report.md`

---

### Task 1: Style State Mapping

**Files:**
- Create: `src/stock_research/market_style_switch_v1.py`
- Test: `tests/test_market_style_switch_v1.py`

- [ ] **Step 1: Write failing style mapping tests**

Create `tests/test_market_style_switch_v1.py`:

```python
import pandas as pd

from stock_research.market_style_switch_v1 import build_style_state_daily


def test_build_style_state_daily_maps_emotion_and_risk_to_style() -> None:
    emotion = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "emotion_state": "euphoria", "risk_state": "low", "emotion_score": 85.0},
            {"trade_date": "2026-01-03", "emotion_state": "hot", "risk_state": "medium", "emotion_score": 70.0},
            {"trade_date": "2026-01-04", "emotion_state": "neutral", "risk_state": "high", "emotion_score": 50.0},
            {"trade_date": "2026-01-05", "emotion_state": "panic", "risk_state": "high", "emotion_score": 25.0},
        ]
    )

    result = build_style_state_daily(emotion)

    assert result[["trade_date", "style_state"]].to_dict("records") == [
        {"trade_date": "2026-01-02", "style_state": "growth_momentum"},
        {"trade_date": "2026-01-03", "style_state": "rotation_balanced"},
        {"trade_date": "2026-01-04", "style_state": "defensive_yield_proxy"},
        {"trade_date": "2026-01-05", "style_state": "cash_or_wait"},
    ]
    assert set(result["position_budget_hint"]) <= {"full", "reduced", "light"}
```

- [ ] **Step 2: Run test and verify expected failure**

```bash
.venv/bin/pytest tests/test_market_style_switch_v1.py -q
```

Expected: import failure because `stock_research.market_style_switch_v1` does not exist.

- [ ] **Step 3: Implement style mapping**

Create `src/stock_research/market_style_switch_v1.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


STYLE_STATE_COLUMNS = [
    "trade_date",
    "emotion_state",
    "risk_state",
    "emotion_score",
    "style_state",
    "style_reason",
    "position_budget_hint",
]


STYLE_MAPPING = {
    ("euphoria", "low"): "growth_momentum",
    ("euphoria", "medium"): "growth_momentum",
    ("euphoria", "high"): "rotation_balanced",
    ("hot", "low"): "growth_momentum",
    ("hot", "medium"): "rotation_balanced",
    ("hot", "high"): "cash_or_wait",
    ("neutral", "low"): "rotation_balanced",
    ("neutral", "medium"): "rotation_balanced",
    ("neutral", "high"): "defensive_yield_proxy",
    ("cold", "medium"): "defensive_yield_proxy",
    ("cold", "high"): "defensive_yield_proxy",
    ("panic", "high"): "cash_or_wait",
}


def build_style_state_daily(emotion: pd.DataFrame) -> pd.DataFrame:
    frame = emotion.copy()
    if frame.empty:
        return pd.DataFrame(columns=STYLE_STATE_COLUMNS)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.date.astype(str)
    frame["emotion_state"] = frame["emotion_state"].fillna("neutral").astype(str)
    frame["risk_state"] = frame["risk_state"].fillna("medium").astype(str)
    frame["emotion_score"] = pd.to_numeric(frame.get("emotion_score"), errors="coerce")
    frame["style_state"] = frame.apply(
        lambda row: STYLE_MAPPING.get((row["emotion_state"], row["risk_state"]), "rotation_balanced"),
        axis=1,
    )
    frame["style_reason"] = frame["emotion_state"] + "|" + frame["risk_state"]
    frame["position_budget_hint"] = frame.apply(_position_budget_hint, axis=1)
    return frame[STYLE_STATE_COLUMNS].sort_values("trade_date").reset_index(drop=True)
```

- [ ] **Step 4: Run test and commit**

```bash
.venv/bin/pytest tests/test_market_style_switch_v1.py -q
git add src/stock_research/market_style_switch_v1.py tests/test_market_style_switch_v1.py
git commit -m "feat: add market style state mapping"
```

---

### Task 2: Growth, Defensive, and Rotation Candidate Sleeves

**Files:**
- Modify: `src/stock_research/market_style_switch_v1.py`
- Modify: `tests/test_market_style_switch_v1.py`

- [ ] **Step 1: Write failing candidate sleeve tests**

Append:

```python
from stock_research.market_style_switch_v1 import (
    build_defensive_yield_proxy_candidates,
    build_growth_momentum_candidates,
    build_rotation_balanced_candidates,
)


def _funnel() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": "G1", "stock_name": "科技A", "mid_trend_funnel_score": 95, "shadow_top10_rank": 1, "industry_name": "软件和信息技术服务业", "volatility_20_score": 30, "max_drawdown_20_score": 60, "ma60_slope_score": 90, "score_total": 95},
            {"trade_date": "2026-01-02", "asset_id": "D1", "stock_name": "长江电力", "mid_trend_funnel_score": 80, "shadow_top10_rank": 5, "industry_name": "电力、热力生产和供应业", "volatility_20_score": 95, "max_drawdown_20_score": 95, "ma60_slope_score": 70, "score_total": 80},
            {"trade_date": "2026-01-02", "asset_id": "D2", "stock_name": "农业银行", "mid_trend_funnel_score": 75, "shadow_top10_rank": 7, "industry_name": "货币金融服务", "volatility_20_score": 90, "max_drawdown_20_score": 90, "ma60_slope_score": 65, "score_total": 75},
            {"trade_date": "2026-01-02", "asset_id": "X1", "stock_name": "地产弱势", "mid_trend_funnel_score": 70, "shadow_top10_rank": 9, "industry_name": "房地产业", "volatility_20_score": 20, "max_drawdown_20_score": 30, "ma60_slope_score": 20, "score_total": 70},
        ]
    )


def test_candidate_sleeves_rank_growth_and_defensive_separately() -> None:
    growth = build_growth_momentum_candidates(_funnel(), top_n=2)
    defensive = build_defensive_yield_proxy_candidates(_funnel(), top_n=2)
    rotation = build_rotation_balanced_candidates(growth, defensive, top_n=4)

    assert growth.iloc[0]["asset_id"] == "G1"
    assert defensive["asset_id"].tolist() == ["D1", "D2"]
    assert rotation["style_sleeve"].tolist() == [
        "growth_momentum",
        "defensive_yield_proxy",
        "growth_momentum",
        "defensive_yield_proxy",
    ]
```

- [ ] **Step 2: Implement candidate sleeve builders**

Implement:

```python
DEFAULT_DEFENSIVE_INDUSTRY_KEYWORDS = ("电力", "热力", "煤炭", "银行", "金融", "食品", "饮料", "酒", "家电", "公用")


def build_growth_momentum_candidates(funnel: pd.DataFrame, *, top_n: int = 5) -> pd.DataFrame:
    frame = _normalize_funnel(funnel)
    if frame.empty:
        return pd.DataFrame()
    frame["growth_rank_score"] = (
        frame["mid_trend_funnel_score"].fillna(frame["score_total"]).fillna(0)
        - frame["shadow_top10_rank"].fillna(999) * 0.5
    )
    return _rank_by_date(frame, "growth_rank_score", top_n, "growth_momentum")


def build_defensive_yield_proxy_candidates(
    funnel: pd.DataFrame,
    *,
    top_n: int = 5,
    defensive_industry_keywords: tuple[str, ...] = DEFAULT_DEFENSIVE_INDUSTRY_KEYWORDS,
) -> pd.DataFrame:
    frame = _normalize_funnel(funnel)
    if frame.empty:
        return pd.DataFrame()
    industry_match = frame["industry_name"].fillna("").astype(str).apply(
        lambda value: any(keyword in value for keyword in defensive_industry_keywords)
    )
    frame = frame[industry_match].copy()
    frame["defensive_rank_score"] = (
        0.35 * frame["volatility_20_score"].fillna(50)
        + 0.35 * frame["max_drawdown_20_score"].fillna(50)
        + 0.20 * frame["ma60_slope_score"].fillna(50)
        + 0.10 * frame["score_total"].fillna(frame["mid_trend_funnel_score"]).fillna(50)
    )
    return _rank_by_date(frame, "defensive_rank_score", top_n, "defensive_yield_proxy")
```

- [ ] **Step 3: Run tests and commit**

```bash
.venv/bin/pytest tests/test_market_style_switch_v1.py -q
git add src/stock_research/market_style_switch_v1.py tests/test_market_style_switch_v1.py
git commit -m "feat: build market style candidate sleeves"
```

---

### Task 3: Anchor Diagnostics and Output Writer

**Files:**
- Modify: `src/stock_research/market_style_switch_v1.py`
- Modify: `tests/test_market_style_switch_v1.py`

- [ ] **Step 1: Add output tests**

Append:

```python
from stock_research.market_style_switch_v1 import build_anchor_diagnostics, write_market_style_switch_outputs


def test_anchor_diagnostics_and_writer(tmp_path) -> None:
    style = build_style_state_daily(pd.DataFrame([{"trade_date": "2026-01-02", "emotion_state": "neutral", "risk_state": "high", "emotion_score": 40}]))
    growth = build_growth_momentum_candidates(_funnel(), top_n=2)
    defensive = build_defensive_yield_proxy_candidates(_funnel(), top_n=3)
    rotation = build_rotation_balanced_candidates(growth, defensive, top_n=4)
    anchors = build_anchor_diagnostics(defensive)

    paths = write_market_style_switch_outputs(
        style_state=style,
        growth_candidates=growth,
        defensive_candidates=defensive,
        rotation_candidates=rotation,
        anchor_diagnostics=anchors,
        summary=pd.DataFrame([{"strategy_family": "fixed_mid_trend", "total_return": 0.0}]),
        year_breakdown=pd.DataFrame([{"year": "2026", "strategy_family": "fixed_mid_trend", "total_return": 0.0}]),
        emotion_breakdown=pd.DataFrame([{"emotion_state": "neutral", "risk_state": "high", "strategy_family": "fixed_mid_trend", "total_return": 0.0}]),
        output_dir=tmp_path,
    )

    assert paths["style_state_path"].exists()
    assert paths["report_path"].exists()
    assert anchors["anchor_present"].any()
```

- [ ] **Step 2: Implement diagnostics and writer**

Implement:

```python
ANCHOR_NAMES = ("长江电力", "中国神华", "农业银行", "伊利股份", "贵州茅台")


def build_anchor_diagnostics(defensive_candidates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    frame = defensive_candidates.copy()
    for trade_date, day in frame.groupby("trade_date", sort=True):
        names = set(day.get("stock_name", pd.Series(dtype=object)).fillna("").astype(str))
        assets = set(day.get("asset_id", pd.Series(dtype=object)).fillna("").astype(str))
        for anchor in ANCHOR_NAMES:
            rows.append({"trade_date": trade_date, "anchor_name": anchor, "anchor_present": anchor in names or anchor in assets})
    return pd.DataFrame(rows)


def write_market_style_switch_outputs(
    *,
    style_state: pd.DataFrame,
    growth_candidates: pd.DataFrame,
    defensive_candidates: pd.DataFrame,
    rotation_candidates: pd.DataFrame,
    anchor_diagnostics: pd.DataFrame,
    summary: pd.DataFrame,
    year_breakdown: pd.DataFrame,
    emotion_breakdown: pd.DataFrame,
    output_dir: str | Path,
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    paths = {
        "style_state_path": output_path / "market_style_state_daily.csv",
        "growth_candidates_path": output_path / "growth_momentum_candidates.csv",
        "defensive_candidates_path": output_path / "defensive_yield_proxy_candidates.csv",
        "rotation_candidates_path": output_path / "rotation_balanced_candidates.csv",
        "anchor_diagnostics_path": output_path / "anchor_diagnostics.csv",
        "summary_path": output_path / "style_switch_backtest_summary.csv",
        "year_breakdown_path": output_path / "style_switch_year_breakdown.csv",
        "emotion_breakdown_path": output_path / "style_switch_emotion_breakdown.csv",
        "report_path": output_path / "market_style_switch_v1_report.md",
    }
    style_state.to_csv(paths["style_state_path"], index=False)
    growth_candidates.to_csv(paths["growth_candidates_path"], index=False)
    defensive_candidates.to_csv(paths["defensive_candidates_path"], index=False)
    rotation_candidates.to_csv(paths["rotation_candidates_path"], index=False)
    anchor_diagnostics.to_csv(paths["anchor_diagnostics_path"], index=False)
    summary.to_csv(paths["summary_path"], index=False)
    year_breakdown.to_csv(paths["year_breakdown_path"], index=False)
    emotion_breakdown.to_csv(paths["emotion_breakdown_path"], index=False)
    paths["report_path"].write_text(
        _render_market_style_switch_report(summary, year_breakdown, emotion_breakdown),
        encoding="utf-8",
    )
    return paths
```

- [ ] **Step 3: Run tests and commit**

```bash
.venv/bin/pytest tests/test_market_style_switch_v1.py -q
git add src/stock_research/market_style_switch_v1.py tests/test_market_style_switch_v1.py
git commit -m "feat: write market style switch outputs"
```

---

### Task 4: Comparative Research Backtest

**Files:**
- Modify: `src/stock_research/market_style_switch_v1.py`
- Modify: `tests/test_market_style_switch_v1.py`

- [ ] **Step 1: Add comparative backtest smoke test**

Append:

```python
from stock_research.market_style_switch_v1 import run_style_switch_backtest_from_frames


def test_run_style_switch_backtest_from_frames_returns_three_strategy_families(tmp_path) -> None:
    emotion = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "emotion_state": "euphoria", "risk_state": "low", "emotion_score": 85},
            {"trade_date": "2026-01-03", "emotion_state": "neutral", "risk_state": "high", "emotion_score": 40},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": "G1", "close": 10.0},
            {"trade_date": "2026-01-03", "asset_id": "G1", "close": 9.0},
            {"trade_date": "2026-01-02", "asset_id": "D1", "close": 10.0},
            {"trade_date": "2026-01-03", "asset_id": "D1", "close": 10.2},
        ]
    )

    result = run_style_switch_backtest_from_frames(
        emotion=emotion,
        funnel=_funnel(),
        prices=prices,
        start_date="2026-01-02",
        end_date="2026-01-03",
        output_dir=tmp_path,
        top_n=1,
    )

    assert set(result["summary"]["strategy_family"]) == {"fixed_mid_trend", "emotion_budget_only", "emotion_style_switch"}
    assert result["paths"]["summary_path"].exists()
```

- [ ] **Step 2: Implement lightweight comparative backtest**

Implement a simple daily close-to-close equal-weight simulator:

- Select candidates by date and style.
- `fixed_mid_trend`: always growth candidates.
- `emotion_budget_only`: growth candidates with invested weight from style state hints.
- `emotion_style_switch`: growth, defensive, rotation, or cash candidate behavior based on `style_state`.
- Keep transaction-cost modeling out of V1 unless existing helpers are easy to reuse.

Use this helper signature:

```python
def run_style_switch_backtest_from_frames(
    *,
    emotion: pd.DataFrame,
    funnel: pd.DataFrame,
    prices: pd.DataFrame,
    start_date: str,
    end_date: str,
    output_dir: str | Path | None = None,
    top_n: int = 5,
    defensive_industry_keywords: tuple[str, ...] = DEFAULT_DEFENSIVE_INDUSTRY_KEYWORDS,
) -> dict[str, Any]:
    style_state = build_style_state_daily(emotion)
    growth = build_growth_momentum_candidates(funnel, top_n=max(top_n, 10))
    defensive = build_defensive_yield_proxy_candidates(
        funnel,
        top_n=max(top_n, 10),
        defensive_industry_keywords=defensive_industry_keywords,
    )
    rotation = build_rotation_balanced_candidates(growth, defensive, top_n=max(top_n, 10))
    anchor_diagnostics = build_anchor_diagnostics(defensive)
    selections = {
        "fixed_mid_trend": _build_strategy_selection(style_state, growth, defensive, rotation, "fixed_mid_trend", top_n),
        "emotion_budget_only": _build_strategy_selection(style_state, growth, defensive, rotation, "emotion_budget_only", top_n),
        "emotion_style_switch": _build_strategy_selection(style_state, growth, defensive, rotation, "emotion_style_switch", top_n),
    }
    equity = pd.concat(
        [_simulate_equal_weight_daily(prices, selected, strategy_family=name) for name, selected in selections.items()],
        ignore_index=True,
    )
    summary = _summarize_equity(equity)
    year_breakdown = _breakdown_equity(equity, style_state, group_cols=["year"])
    emotion_breakdown = _breakdown_equity(equity, style_state, group_cols=["emotion_state", "risk_state", "style_state"])
    paths = {}
    if output_dir is not None:
        paths = write_market_style_switch_outputs(
            style_state=style_state,
            growth_candidates=growth,
            defensive_candidates=defensive,
            rotation_candidates=rotation,
            anchor_diagnostics=anchor_diagnostics,
            summary=summary,
            year_breakdown=year_breakdown,
            emotion_breakdown=emotion_breakdown,
            output_dir=output_dir,
        )
    return {"style_state": style_state, "summary": summary, "equity": equity, "paths": paths}
```

- [ ] **Step 3: Run tests and commit**

```bash
.venv/bin/pytest tests/test_market_style_switch_v1.py -q
git add src/stock_research/market_style_switch_v1.py tests/test_market_style_switch_v1.py
git commit -m "feat: compare market style switch strategies"
```

---

### Task 5: Loader, CLI, and Full 2023-2026 Run

**Files:**
- Modify: `src/stock_research/market_style_switch_v1.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_market_style_switch_v1.py`

- [ ] **Step 1: Add loader/runner**

Implement:

```python
def run_market_style_switch_v1_backtest(
    *,
    start_date: str,
    end_date: str,
    emotion_path: str | Path,
    funnel_detail_path: str | Path,
    output_dir: str | Path,
    top_n: int = 5,
    defensive_industry_keywords: tuple[str, ...] = DEFAULT_DEFENSIVE_INDUSTRY_KEYWORDS,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    emotion = pd.read_csv(emotion_path, low_memory=False)
    funnel = pd.read_csv(funnel_detail_path, low_memory=False)
    prices = load_style_switch_prices(start_date, end_date, adjust_type=adjust_type, service=service)
    return run_style_switch_backtest_from_frames(
        emotion=emotion,
        funnel=funnel,
        prices=prices,
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        top_n=top_n,
        defensive_industry_keywords=defensive_industry_keywords,
    )
```

- [ ] **Step 2: Add CLI parser and dispatch**

Add parser:

```python
    market_style_switch = subparsers.add_parser("market-style-switch-v1-backtest")
    market_style_switch.add_argument("--start-date", required=True)
    market_style_switch.add_argument("--end-date", required=True)
    market_style_switch.add_argument("--emotion-path", required=True)
    market_style_switch.add_argument("--funnel-detail-path", required=True)
    market_style_switch.add_argument("--output-dir", required=True)
    market_style_switch.add_argument("--top-n", type=int, default=5)
    market_style_switch.add_argument("--defensive-industry-keywords")
    market_style_switch.add_argument("--adjust-type", choices=["raw", "qfq", "hfq"], default="hfq")
```

Add dispatch:

```python
    elif args.command == "market-style-switch-v1-backtest":
        from stock_research.market_style_switch_v1 import (
            DEFAULT_DEFENSIVE_INDUSTRY_KEYWORDS,
            run_market_style_switch_v1_backtest,
        )

        keywords = tuple(args.defensive_industry_keywords.split(",")) if args.defensive_industry_keywords else DEFAULT_DEFENSIVE_INDUSTRY_KEYWORDS
        result = run_market_style_switch_v1_backtest(
            start_date=args.start_date,
            end_date=args.end_date,
            emotion_path=args.emotion_path,
            funnel_detail_path=args.funnel_detail_path,
            output_dir=args.output_dir,
            top_n=args.top_n,
            defensive_industry_keywords=keywords,
            adjust_type=args.adjust_type,
        )
        print(f"market_style_switch|summary|{result['paths']['summary_path']}")
```

- [ ] **Step 3: Run full backtest**

```bash
.venv/bin/python -m stock_research.cli market-style-switch-v1-backtest \
  --start-date 2023-01-03 \
  --end-date 2026-06-05 \
  --emotion-path outputs/research/market_emotion_state_v1_20230103_20260605/market_emotion_state_daily.csv \
  --funnel-detail-path outputs/research/mid_trend_watch_funnel_20230103_20260605_aligned/mid_trend_watch_funnel_detail.csv \
  --output-dir outputs/research/market_style_switch_v1_20230103_20260605 \
  --top-n 5 \
  --adjust-type hfq
```

- [ ] **Step 4: Verify and summarize**

```bash
.venv/bin/pytest tests/test_market_style_switch_v1.py tests/test_market_emotion_state_v1.py -q
cat outputs/research/market_style_switch_v1_20230103_20260605/style_switch_backtest_summary.csv
cat outputs/research/market_style_switch_v1_20230103_20260605/style_switch_year_breakdown.csv
```

Expected:

- Tests pass.
- Summary contains `fixed_mid_trend`, `emotion_budget_only`, and `emotion_style_switch`.
- Report discusses whether style switching adds value beyond exposure control.

Commit only clean task files and leave unrelated `cli.py` changes untouched by hunk-staging if necessary.
