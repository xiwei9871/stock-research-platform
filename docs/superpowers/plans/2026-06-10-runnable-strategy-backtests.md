# Runnable Strategy Backtests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all Backtest Lab catalog strategies runnable and add a `Run Comparison` workflow that compares every runnable strategy under identical parameters.

**Architecture:** Add a backend strategy score adapter registry that converts each strategy into the existing vectorized TopN score frame contract. Keep `POST /api/backtests/run` as the execution endpoint, route by `strategy_id`, and reuse `run_vectorized_topn_backtest`. Add frontend comparison state that calls the existing run endpoint once per runnable strategy and renders a comparison table without blocking single-strategy runs.

**Tech Stack:** Python, pandas, pytest, FastAPI TestClient, React, TypeScript, Vitest, Testing Library, Playwright, existing `stock_research.vectorized_topn_backtest`.

---

## File Structure

- Create `src/stock_research/dashboard/strategy_backtest_adapters.py`
  - Owns adapter contract, strategy registry, database loaders, and pure frame-to-score builders.
- Modify `src/stock_research/dashboard/backtests.py`
  - Parses request parameters, resolves adapter by `strategy_id`, loads scores and prices, runs vectorized TopN, serializes result.
- Modify `src/stock_research/dashboard/strategy_catalog.py`
  - Marks all five strategies `runnable` and adds default backtest parameters.
- Modify `tests/test_dashboard_backtests.py`
  - Updates routing tests from single hard-coded strategy to registry-driven strategies.
- Create `tests/test_strategy_backtest_adapters.py`
  - Per-strategy unit tests for score construction, ranking, and empty-data behavior.
- Modify `dashboard/src/components/BacktestLabWorkspace.tsx`
  - Adds `Run Comparison`, comparison state, partial failure rows, and selectable detail result.
- Modify `dashboard/src/styles.css`
  - Adds comparison table and action layout styles.
- Modify `dashboard/tests/backtest-lab-workspace.test.tsx`
  - Verifies all strategies are runnable, single runs work for LHB, and comparison calls all runnable strategies with identical parameters.
- Modify `dashboard/tests/platform-full-flow.spec.ts`
  - Adds Playwright coverage for Backtest Lab single run and `Run Comparison`.

---

### Task 1: Add Strategy Adapter Contract And Shared Builders

**Files:**
- Create: `src/stock_research/dashboard/strategy_backtest_adapters.py`
- Test: `tests/test_strategy_backtest_adapters.py`

- [ ] **Step 1: Write failing tests for normalization helpers and adapter registry**

Add this initial test file:

```python
import pandas as pd
import pytest

from stock_research.dashboard.strategy_backtest_adapters import (
    STRATEGY_BACKTEST_REGISTRY,
    StrategyBacktestParams,
    normalize_strategy_scores,
)


def test_registry_contains_all_backtest_lab_strategies():
    assert set(STRATEGY_BACKTEST_REGISTRY) == {
        "manual_v1_topn_rotation",
        "lhb_shortline",
        "mid_trend",
        "tech_bottleneck",
        "position_control",
    }


def test_normalize_strategy_scores_ranks_high_scores_first():
    raw = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 80.0},
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 90.0},
            {"trade_date": "2026-01-02", "asset_id": "A", "score_total": 70.0},
        ]
    )

    scores = normalize_strategy_scores(raw, strategy_id="unit_strategy")

    assert list(scores["trade_date"]) == ["2026-01-01", "2026-01-01", "2026-01-02"]
    assert list(scores["asset_id"]) == ["A", "B", "A"]
    assert list(scores["rank"]) == [1, 2, 1]
    assert list(scores["strategy_id"].unique()) == ["unit_strategy"]


def test_normalize_strategy_scores_rejects_empty_signal_set():
    with pytest.raises(ValueError, match="no unit_strategy strategy scores found"):
        normalize_strategy_scores(pd.DataFrame(), strategy_id="unit_strategy")


def test_strategy_backtest_params_defaults():
    params = StrategyBacktestParams(start_date="2026-01-01", end_date="2026-06-08")

    assert params.score_version == "manual_v1"
    assert params.adjust_type == "hfq"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_strategy_backtest_adapters.py -q
```

Expected: FAIL with `ModuleNotFoundError` or missing symbols from `strategy_backtest_adapters`.

- [ ] **Step 3: Implement adapter contract and normalization**

Create `src/stock_research/dashboard/strategy_backtest_adapters.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


@dataclass(frozen=True)
class StrategyBacktestParams:
    start_date: str
    end_date: str
    score_version: str = "manual_v1"
    adjust_type: str = "hfq"


class StrategyBacktestAdapter(Protocol):
    strategy_id: str

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        ...


def normalize_strategy_scores(frame: pd.DataFrame, strategy_id: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError(f"no {strategy_id} strategy scores found for selected range")
    required = {"trade_date", "asset_id", "score_total"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{strategy_id} scores missing columns: {', '.join(sorted(missing))}")

    normalized = frame.copy()
    normalized["trade_date"] = normalized["trade_date"].astype(str)
    normalized["asset_id"] = normalized["asset_id"].astype(str)
    normalized["score_total"] = pd.to_numeric(normalized["score_total"], errors="coerce")
    normalized = normalized.dropna(subset=["trade_date", "asset_id", "score_total"])
    if normalized.empty:
        raise ValueError(f"no {strategy_id} strategy scores found for selected range")

    normalized = normalized.sort_values(
        ["trade_date", "score_total", "asset_id"],
        ascending=[True, False, True],
    ).reset_index(drop=True)
    normalized["rank"] = normalized.groupby("trade_date").cumcount() + 1
    normalized["strategy_id"] = strategy_id
    if "score_components" not in normalized.columns:
        normalized["score_components"] = [{} for _ in range(len(normalized))]
    if "eligibility" not in normalized.columns:
        normalized["eligibility"] = True
    if "eligibility_reason" not in normalized.columns:
        normalized["eligibility_reason"] = "eligible"
    if "exposure_scale" not in normalized.columns:
        normalized["exposure_scale"] = 1.0
    return normalized[
        [
            "trade_date",
            "asset_id",
            "rank",
            "score_total",
            "score_components",
            "strategy_id",
            "eligibility",
            "eligibility_reason",
            "exposure_scale",
        ]
    ]


def _fetch_frame(sql: str, params: list[object], service: str = SETTINGS.research_service) -> pd.DataFrame:
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return pd.DataFrame(rows)
```

Append stub adapter classes and registry so the registry test can pass; their `load_scores` methods can raise until specific strategy tests drive implementation:

```python
class ManualV1TopNAdapter:
    strategy_id = "manual_v1_topn_rotation"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        raise NotImplementedError


class LHBShortlineAdapter:
    strategy_id = "lhb_shortline"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        raise NotImplementedError


class MidTrendAdapter:
    strategy_id = "mid_trend"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        raise NotImplementedError


class TechBottleneckAdapter:
    strategy_id = "tech_bottleneck"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        raise NotImplementedError


class PositionControlAdapter:
    strategy_id = "position_control"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        raise NotImplementedError


STRATEGY_BACKTEST_REGISTRY: dict[str, StrategyBacktestAdapter] = {
    "manual_v1_topn_rotation": ManualV1TopNAdapter(),
    "lhb_shortline": LHBShortlineAdapter(),
    "mid_trend": MidTrendAdapter(),
    "tech_bottleneck": TechBottleneckAdapter(),
    "position_control": PositionControlAdapter(),
}
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_strategy_backtest_adapters.py -q
```

Expected: PASS for the four initial tests.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/strategy_backtest_adapters.py tests/test_strategy_backtest_adapters.py
git commit -m "test: add strategy backtest adapter contract"
```

---

### Task 2: Implement Manual V1 And LHB Adapters With Unit Tests

**Files:**
- Modify: `src/stock_research/dashboard/strategy_backtest_adapters.py`
- Modify: `tests/test_strategy_backtest_adapters.py`

- [ ] **Step 1: Add failing tests for Manual V1 and LHB score builders**

Append to `tests/test_strategy_backtest_adapters.py`:

```python
from stock_research.dashboard.strategy_backtest_adapters import (
    build_lhb_shortline_scores_from_frames,
    build_manual_v1_scores_from_frame,
)


def test_manual_v1_builder_preserves_manual_score_order():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "rank": 2, "score_total": 80.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "rank": 1, "score_total": 90.0},
        ]
    )

    scores = build_manual_v1_scores_from_frame(manual)

    assert list(scores["asset_id"]) == ["B", "A"]
    assert list(scores["rank"]) == [1, 2]


def test_lhb_shortline_builder_ranks_positive_support_above_risky_rows():
    lhb = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-01",
                "asset_id": "A",
                "on_lhb": True,
                "lhb_net_buy_ratio": 0.22,
                "lhb_net_buy_amount": 80_000_000,
                "institution_net_buy": 20_000_000,
                "repeat_on_list_count_3d": 2,
                "lhb_after_reversal": True,
                "lhb_one_day_pump_risk": 0.10,
            },
            {
                "trade_date": "2026-01-01",
                "asset_id": "B",
                "on_lhb": True,
                "lhb_net_buy_ratio": -0.05,
                "lhb_net_buy_amount": -5_000_000,
                "institution_net_buy": -2_000_000,
                "repeat_on_list_count_3d": 1,
                "lhb_after_reversal": False,
                "lhb_one_day_pump_risk": 0.90,
            },
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "amount_vs_20d": 1.5, "high_to_close_drawdown": 0.03},
            {"trade_date": "2026-01-01", "asset_id": "B", "amount_vs_20d": 0.3, "high_to_close_drawdown": 0.16},
        ]
    )

    scores = build_lhb_shortline_scores_from_frames(lhb, technical)

    assert list(scores["asset_id"]) == ["A", "B"]
    assert scores.iloc[0]["score_total"] > scores.iloc[1]["score_total"]
    assert scores.iloc[1]["eligibility"] is False
    assert "pump_risk" in scores.iloc[1]["eligibility_reason"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_strategy_backtest_adapters.py -q
```

Expected: FAIL with missing `build_manual_v1_scores_from_frame` and `build_lhb_shortline_scores_from_frames`.

- [ ] **Step 3: Implement Manual V1 and LHB builders**

Add these helpers to `strategy_backtest_adapters.py`:

```python
def _num(series: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def _bool(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(bool)


def build_manual_v1_scores_from_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return normalize_strategy_scores(
        frame[["trade_date", "asset_id", "score_total"]].copy(),
        strategy_id="manual_v1_topn_rotation",
    )


def build_lhb_shortline_scores_from_frames(lhb: pd.DataFrame, technical: pd.DataFrame | None = None) -> pd.DataFrame:
    if lhb is None or lhb.empty:
        return normalize_strategy_scores(pd.DataFrame(), strategy_id="lhb_shortline")
    frame = lhb.copy()
    if technical is not None and not technical.empty:
        frame = frame.merge(
            technical[["trade_date", "asset_id", "amount_vs_20d", "high_to_close_drawdown"]],
            on=["trade_date", "asset_id"],
            how="left",
        )
    net_ratio = _num(frame.get("lhb_net_buy_ratio", pd.Series(index=frame.index)))
    net_amount = _num(frame.get("lhb_net_buy_amount", pd.Series(index=frame.index))) / 100_000_000.0
    inst_buy = _num(frame.get("institution_net_buy", pd.Series(index=frame.index))) / 100_000_000.0
    repeat = _num(frame.get("repeat_on_list_count_3d", pd.Series(index=frame.index)))
    reversal = _bool(frame.get("lhb_after_reversal", pd.Series(index=frame.index))).astype(float)
    amount_confirmation = _num(frame.get("amount_vs_20d", pd.Series(index=frame.index)), 1.0).clip(0, 3)
    pump_risk = _num(frame.get("lhb_one_day_pump_risk", pd.Series(index=frame.index)))
    high_drawdown = _num(frame.get("high_to_close_drawdown", pd.Series(index=frame.index)))

    frame["score_total"] = (
        50.0
        + net_ratio.clip(-1, 1) * 35.0
        + net_amount.clip(-1, 3) * 8.0
        + inst_buy.clip(-1, 2) * 6.0
        + repeat.clip(0, 5) * 2.5
        + reversal * 6.0
        + amount_confirmation * 2.0
        - pump_risk.clip(0, 1) * 25.0
        - high_drawdown.clip(0, 1) * 40.0
    )
    eligible = _bool(frame.get("on_lhb", pd.Series(index=frame.index))) & (pump_risk < 0.75)
    frame["eligibility"] = eligible
    frame["eligibility_reason"] = eligible.map({True: "lhb_support", False: "pump_risk_or_missing_lhb"})
    frame["score_components"] = [
        {
            "lhb_net_buy_ratio": float(net_ratio.iloc[index]),
            "lhb_net_buy_amount": float(net_amount.iloc[index]),
            "institution_net_buy": float(inst_buy.iloc[index]),
            "lhb_one_day_pump_risk": float(pump_risk.iloc[index]),
        }
        for index in range(len(frame))
    ]
    return normalize_strategy_scores(frame, strategy_id="lhb_shortline")
```

- [ ] **Step 4: Implement database loaders for Manual V1 and LHB**

Replace the two stub `load_scores` methods with:

```python
class ManualV1TopNAdapter:
    strategy_id = "manual_v1_topn_rotation"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        sql = """
        SELECT trade_date, asset_id, rank, score_total
        FROM factor.stock_score_daily
        WHERE score_version = %s
          AND trade_date BETWEEN %s AND %s
        ORDER BY trade_date, rank, asset_id
        """
        return build_manual_v1_scores_from_frame(
            _fetch_frame(sql, [params.score_version, params.start_date, params.end_date])
        )


class LHBShortlineAdapter:
    strategy_id = "lhb_shortline"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        lhb_sql = """
        SELECT
            l.trade_date,
            COALESCE(a.asset_id, l.ts_code) AS asset_id,
            l.on_lhb,
            l.lhb_net_buy_ratio,
            l.lhb_net_buy_amount,
            l.institution_net_buy,
            l.repeat_on_list_count_3d,
            l.lhb_after_reversal,
            l.lhb_one_day_pump_risk
        FROM factor.lhb_event_features_daily l
        LEFT JOIN core.asset_master a ON a.ts_code = l.ts_code
        WHERE l.trade_date BETWEEN %s AND %s
        """
        technical_sql = """
        SELECT trade_date, asset_id, amount_vs_20d, high_to_close_drawdown
        FROM factor.stock_technical_features_daily
        WHERE adjust_type = %s
          AND trade_date BETWEEN %s AND %s
        """
        lhb = _fetch_frame(lhb_sql, [params.start_date, params.end_date])
        technical = _fetch_frame(technical_sql, [params.adjust_type, params.start_date, params.end_date])
        return build_lhb_shortline_scores_from_frames(lhb, technical)
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/test_strategy_backtest_adapters.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/dashboard/strategy_backtest_adapters.py tests/test_strategy_backtest_adapters.py
git commit -m "feat: add manual and lhb backtest adapters"
```

---

### Task 3: Implement Mid Trend, Tech Bottleneck, And Position Control Adapters

**Files:**
- Modify: `src/stock_research/dashboard/strategy_backtest_adapters.py`
- Modify: `tests/test_strategy_backtest_adapters.py`

- [ ] **Step 1: Add failing tests for the three remaining adapters**

Append:

```python
from stock_research.dashboard.strategy_backtest_adapters import (
    build_mid_trend_scores_from_frames,
    build_position_control_scores_from_frames,
    build_tech_bottleneck_scores_from_frames,
)


def test_mid_trend_builder_prefers_stronger_trend_and_penalizes_risk():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 70.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 78.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "ret_20d": 0.18, "high_to_close_drawdown": 0.02, "amount_vs_20d": 1.2},
            {"trade_date": "2026-01-01", "asset_id": "B", "ret_20d": -0.03, "high_to_close_drawdown": 0.18, "amount_vs_20d": 0.5},
        ]
    )
    factors = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "factor_name": "trend_r2_20", "factor_value": 0.85},
            {"trade_date": "2026-01-01", "asset_id": "B", "factor_name": "trend_r2_20", "factor_value": 0.25},
        ]
    )

    scores = build_mid_trend_scores_from_frames(manual, technical, factors)

    assert list(scores["asset_id"]) == ["A", "B"]
    assert scores.iloc[0]["score_total"] > scores.iloc[1]["score_total"]


def test_tech_bottleneck_builder_prefers_continuation_and_volume_confirmation():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 65.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 86.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "ret_20d": 0.16, "amount_vs_20d": 2.4, "close_position_in_day": 0.86, "high_to_close_drawdown": 0.02},
            {"trade_date": "2026-01-01", "asset_id": "B", "ret_20d": 0.01, "amount_vs_20d": 0.7, "close_position_in_day": 0.45, "high_to_close_drawdown": 0.12},
        ]
    )

    scores = build_tech_bottleneck_scores_from_frames(manual, technical)

    assert list(scores["asset_id"]) == ["A", "B"]
    assert scores.iloc[0]["score_total"] > scores.iloc[1]["score_total"]


def test_position_control_builder_reranks_risky_base_candidates():
    manual = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "score_total": 90.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "score_total": 88.0},
        ]
    )
    technical = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "high_to_close_drawdown": 0.22, "amount_vs_20d": 3.0},
            {"trade_date": "2026-01-01", "asset_id": "B", "high_to_close_drawdown": 0.02, "amount_vs_20d": 1.0},
        ]
    )

    scores = build_position_control_scores_from_frames(manual, technical)

    assert list(scores["asset_id"]) == ["B", "A"]
    assert scores.iloc[0]["exposure_scale"] == 1.0
    assert scores.iloc[1]["exposure_scale"] < 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_strategy_backtest_adapters.py -q
```

Expected: FAIL with missing builder functions.

- [ ] **Step 3: Implement factor pivot and strategy builders**

Add:

```python
def _factor_pivot(factors: pd.DataFrame | None) -> pd.DataFrame:
    if factors is None or factors.empty:
        return pd.DataFrame(columns=["trade_date", "asset_id"])
    pivot = factors.pivot_table(
        index=["trade_date", "asset_id"],
        columns="factor_name",
        values="factor_value",
        aggfunc="last",
    ).reset_index()
    pivot.columns = [str(column) for column in pivot.columns]
    return pivot


def _merge_manual_technical_factors(
    manual: pd.DataFrame,
    technical: pd.DataFrame | None,
    factors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    base = manual[["trade_date", "asset_id", "score_total"]].copy()
    base = base.rename(columns={"score_total": "manual_score"})
    if technical is not None and not technical.empty:
        base = base.merge(technical, on=["trade_date", "asset_id"], how="left")
    factor_wide = _factor_pivot(factors)
    if not factor_wide.empty:
        base = base.merge(factor_wide, on=["trade_date", "asset_id"], how="left")
    return base


def build_mid_trend_scores_from_frames(
    manual: pd.DataFrame,
    technical: pd.DataFrame | None,
    factors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    frame = _merge_manual_technical_factors(manual, technical, factors)
    trend = _num(frame.get("trend_r2_20", pd.Series(index=frame.index))).clip(0, 1)
    ret_20d = _num(frame.get("ret_20d", pd.Series(index=frame.index))).clip(-0.3, 0.5)
    amount = _num(frame.get("amount_vs_20d", pd.Series(index=frame.index)), 1.0).clip(0, 3)
    drawdown = _num(frame.get("high_to_close_drawdown", pd.Series(index=frame.index))).clip(0, 1)
    manual_score = _num(frame.get("manual_score", pd.Series(index=frame.index)), 50.0)
    frame["score_total"] = manual_score * 0.35 + trend * 35.0 + ret_20d * 80.0 + amount * 3.0 - drawdown * 45.0
    frame["eligibility"] = (trend >= 0.30) | (ret_20d > 0)
    frame["eligibility_reason"] = frame["eligibility"].map({True: "trend_candidate", False: "weak_trend"})
    frame["score_components"] = [
        {"manual_score": float(manual_score.iloc[index]), "trend_r2_20": float(trend.iloc[index]), "ret_20d": float(ret_20d.iloc[index])}
        for index in range(len(frame))
    ]
    return normalize_strategy_scores(frame, strategy_id="mid_trend")


def build_tech_bottleneck_scores_from_frames(manual: pd.DataFrame, technical: pd.DataFrame | None) -> pd.DataFrame:
    frame = _merge_manual_technical_factors(manual, technical)
    manual_score = _num(frame.get("manual_score", pd.Series(index=frame.index)), 50.0)
    ret_20d = _num(frame.get("ret_20d", pd.Series(index=frame.index))).clip(-0.3, 0.5)
    amount = _num(frame.get("amount_vs_20d", pd.Series(index=frame.index)), 1.0).clip(0, 4)
    close_position = _num(frame.get("close_position_in_day", pd.Series(index=frame.index)), 0.5).clip(0, 1)
    drawdown = _num(frame.get("high_to_close_drawdown", pd.Series(index=frame.index))).clip(0, 1)
    frame["score_total"] = manual_score * 0.20 + ret_20d * 95.0 + amount * 8.0 + close_position * 18.0 - drawdown * 35.0
    frame["eligibility"] = amount >= 0.5
    frame["eligibility_reason"] = frame["eligibility"].map({True: "technical_confirmation", False: "weak_volume_price"})
    frame["score_components"] = [
        {"manual_score": float(manual_score.iloc[index]), "ret_20d": float(ret_20d.iloc[index]), "amount_vs_20d": float(amount.iloc[index])}
        for index in range(len(frame))
    ]
    return normalize_strategy_scores(frame, strategy_id="tech_bottleneck")


def build_position_control_scores_from_frames(manual: pd.DataFrame, technical: pd.DataFrame | None) -> pd.DataFrame:
    frame = _merge_manual_technical_factors(manual, technical)
    manual_score = _num(frame.get("manual_score", pd.Series(index=frame.index)), 50.0)
    drawdown = _num(frame.get("high_to_close_drawdown", pd.Series(index=frame.index))).clip(0, 1)
    amount = _num(frame.get("amount_vs_20d", pd.Series(index=frame.index)), 1.0).clip(0, 5)
    risk_penalty = drawdown * 120.0 + (amount - 2.5).clip(lower=0) * 8.0
    frame["score_total"] = manual_score - risk_penalty
    frame["exposure_scale"] = (1.0 - drawdown * 2.0).clip(lower=0.25, upper=1.0)
    frame["eligibility"] = frame["exposure_scale"] >= 0.25
    frame["eligibility_reason"] = frame["eligibility"].map({True: "risk_scaled", False: "risk_excluded"})
    frame["score_components"] = [
        {"manual_score": float(manual_score.iloc[index]), "risk_penalty": float(risk_penalty.iloc[index]), "exposure_scale": float(frame["exposure_scale"].iloc[index])}
        for index in range(len(frame))
    ]
    return normalize_strategy_scores(frame, strategy_id="position_control")
```

- [ ] **Step 4: Implement database loaders for the three adapters**

Add reusable loaders:

```python
def _load_manual_scores(params: StrategyBacktestParams) -> pd.DataFrame:
    return _fetch_frame(
        """
        SELECT trade_date, asset_id, rank, score_total
        FROM factor.stock_score_daily
        WHERE score_version = %s
          AND trade_date BETWEEN %s AND %s
        ORDER BY trade_date, rank, asset_id
        """,
        [params.score_version, params.start_date, params.end_date],
    )


def _load_technical_features(params: StrategyBacktestParams) -> pd.DataFrame:
    return _fetch_frame(
        """
        SELECT
            trade_date,
            asset_id,
            ret_20d,
            amount_vs_20d,
            close_position_in_day,
            high_to_close_drawdown
        FROM factor.stock_technical_features_daily
        WHERE adjust_type = %s
          AND trade_date BETWEEN %s AND %s
        """,
        [params.adjust_type, params.start_date, params.end_date],
    )


def _load_factor_values(params: StrategyBacktestParams, factor_names: list[str]) -> pd.DataFrame:
    return _fetch_frame(
        """
        SELECT trade_date, asset_id, factor_name, factor_value
        FROM factor.factor_daily
        WHERE trade_date BETWEEN %s AND %s
          AND factor_name = ANY(%s)
        """,
        [params.start_date, params.end_date, factor_names],
    )
```

Then replace stub load methods:

```python
class MidTrendAdapter:
    strategy_id = "mid_trend"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        return build_mid_trend_scores_from_frames(
            _load_manual_scores(params),
            _load_technical_features(params),
            _load_factor_values(params, ["trend_r2_20", "ma20_slope", "ma60_slope"]),
        )


class TechBottleneckAdapter:
    strategy_id = "tech_bottleneck"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        return build_tech_bottleneck_scores_from_frames(
            _load_manual_scores(params),
            _load_technical_features(params),
        )


class PositionControlAdapter:
    strategy_id = "position_control"

    def load_scores(self, params: StrategyBacktestParams) -> pd.DataFrame:
        return build_position_control_scores_from_frames(
            _load_manual_scores(params),
            _load_technical_features(params),
        )
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/test_strategy_backtest_adapters.py -q
```

Expected: PASS, including all per-strategy builder tests.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/dashboard/strategy_backtest_adapters.py tests/test_strategy_backtest_adapters.py
git commit -m "feat: add trend bottleneck and position adapters"
```

---

### Task 4: Wire Backend Backtest Routing To Strategy Registry

**Files:**
- Modify: `src/stock_research/dashboard/backtests.py`
- Modify: `src/stock_research/dashboard/strategy_catalog.py`
- Modify: `tests/test_dashboard_backtests.py`

- [ ] **Step 1: Update failing backend tests**

Change `test_list_backtest_strategies_returns_strategy_catalog_rows`:

```python
def test_list_backtest_strategies_returns_strategy_catalog_rows():
    rows = backtests.list_backtest_strategies()

    by_id = {row["strategy_id"]: row for row in rows}
    assert set(by_id) >= {
        "manual_v1_topn_rotation",
        "lhb_shortline",
        "mid_trend",
        "tech_bottleneck",
        "position_control",
    }
    assert {by_id[key]["status"] for key in by_id if key in {
        "manual_v1_topn_rotation",
        "lhb_shortline",
        "mid_trend",
        "tech_bottleneck",
        "position_control",
    }} == {"runnable"}
```

Replace `test_run_backtest_rejects_unsupported_strategy`:

```python
def test_run_backtest_rejects_unknown_strategy():
    try:
        backtests.run_backtest(
            {
                "strategy_id": "unknown_strategy",
                "start_date": "2026-06-01",
                "end_date": "2026-06-05",
            }
        )
    except ValueError as exc:
        assert "unsupported strategy" in str(exc)
    else:
        raise AssertionError("expected unknown strategy to raise ValueError")
```

Add a registry-driven test:

```python
def test_run_backtest_routes_lhb_strategy_through_adapter(monkeypatch):
    calls = {}
    result = VectorizedTopNResult(
        config=VectorizedTopNConfig(start_date="2026-06-01", end_date="2026-06-05", top_n=2),
        equity_curve=pd.DataFrame([{"date": "2026-06-02", "equity": 1.01, "drawdown": 0.0}]),
        positions=pd.DataFrame([{"rebalance_date": "2026-06-01", "asset_id": "A", "rank": 1, "score_total": 90.0, "weight": 0.5}]),
        trades=pd.DataFrame([{"execution_date": "2026-06-02", "asset_id": "A", "side": "buy"}]),
        summary={"total_return": 0.01, "max_drawdown": 0.0},
    )

    class FakeAdapter:
        strategy_id = "lhb_shortline"

        def load_scores(self, params):
            calls["params"] = params
            return pd.DataFrame([{"trade_date": "2026-06-01", "asset_id": "A", "rank": 1, "score_total": 90.0}])

    monkeypatch.setitem(backtests.STRATEGY_BACKTEST_REGISTRY, "lhb_shortline", FakeAdapter())
    monkeypatch.setattr(backtests, "load_vectorized_topn_prices", lambda **kwargs: pd.DataFrame())
    monkeypatch.setattr(backtests, "run_vectorized_topn_backtest", lambda scores, prices, config: result)

    payload = backtests.run_backtest(
        {
            "strategy_id": "lhb_shortline",
            "start_date": "2026-06-01",
            "end_date": "2026-06-05",
            "top_n": 2,
            "rebalance_frequency": "daily",
            "transaction_cost_bps": 10,
            "max_positions": 2,
            "score_version": "manual_v1",
            "adjust_type": "hfq",
        }
    )

    assert calls["params"].start_date == "2026-06-01"
    assert payload["strategy_id"] == "lhb_shortline"
    assert payload["strategy_name"] == "LHB Shortline"
```

- [ ] **Step 2: Run backend tests to verify failures**

Run:

```bash
pytest tests/test_dashboard_backtests.py -q
```

Expected: FAIL because catalog still marks replay-only and backend still hard-codes Manual V1.

- [ ] **Step 3: Update price loader and registry routing**

In `backtests.py`, import:

```python
from stock_research.dashboard.strategy_backtest_adapters import (
    STRATEGY_BACKTEST_REGISTRY,
    StrategyBacktestParams,
)
```

Remove `RUNNABLE_STRATEGY_ID`. Add:

```python
def load_vectorized_topn_prices(start_date: str, end_date: str, adjust_type: str) -> pd.DataFrame:
    _, prices = load_vectorized_topn_inputs(
        start_date=start_date,
        end_date=end_date,
        score_version="manual_v1",
        adjust_type=adjust_type,
    )
    return prices
```

Update `run_backtest` routing:

```python
strategy_id = _required_text(payload, "strategy_id")
adapter = STRATEGY_BACKTEST_REGISTRY.get(strategy_id)
if adapter is None:
    raise ValueError(f"unsupported strategy: {strategy_id}")

start_date = _required_text(payload, "start_date")
end_date = _required_text(payload, "end_date")
score_version = _optional_text(payload.get("score_version"), "manual_v1")
adjust_type = _optional_text(payload.get("adjust_type"), "hfq")
top_n = _positive_int(payload.get("top_n"), "top_n", 20)
max_positions = _optional_positive_int(payload.get("max_positions"), "max_positions")
rebalance_frequency = _rebalance_frequency(payload.get("rebalance_frequency"))
transaction_cost_bps = _finite_float(payload.get("transaction_cost_bps"), "transaction_cost_bps", 0.0)

params = StrategyBacktestParams(
    start_date=start_date,
    end_date=end_date,
    score_version=score_version,
    adjust_type=adjust_type,
)
scores = adapter.load_scores(params)
prices = load_vectorized_topn_prices(start_date=start_date, end_date=end_date, adjust_type=adjust_type)
```

Keep the existing `VectorizedTopNConfig`, `run_vectorized_topn_backtest`, and serialization code.

- [ ] **Step 4: Mark all strategy catalog rows runnable**

In `strategy_catalog.py`, update LHB, Mid Trend, Tech Bottleneck, and Position Control:

```python
"status": "runnable",
"default_parameters": {
    "score_version": "manual_v1",
    "top_n": 20,
    "rebalance_frequency": "weekly",
    "max_positions": 20,
    "transaction_cost_bps": 10,
    "adjust_type": "hfq",
},
"primary_action": "Run backtest",
```

Keep `latest_evidence: "strategy_validation"` so users can still inspect evidence.

- [ ] **Step 5: Run backend tests**

Run:

```bash
pytest tests/test_dashboard_backtests.py tests/test_strategy_backtest_adapters.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/dashboard/backtests.py src/stock_research/dashboard/strategy_catalog.py tests/test_dashboard_backtests.py
git commit -m "feat: route backtests through strategy adapters"
```

---

### Task 5: Update Backtest Lab Tests For Runnable Strategies And Comparison

**Files:**
- Modify: `dashboard/tests/backtest-lab-workspace.test.tsx`

- [ ] **Step 1: Update test fixtures to make all strategies runnable**

Change `makeStrategies()` LHB fixture:

```typescript
{
  strategy_id: 'lhb_shortline',
  strategy_name: 'LHB Shortline',
  status: 'runnable',
  description: 'Research-grade LHB shortline backtest.',
  factor_groups: [],
  signal_inputs: ['lhb_events', 'operator_review'],
  default_parameters: { top_n: 20 },
  latest_evidence: 'strategy_validation',
  primary_action: 'Run backtest'
}
```

Add at least one more runnable fixture:

```typescript
{
  strategy_id: 'mid_trend',
  strategy_name: 'Mid Trend Shortline',
  status: 'runnable',
  description: 'Research-grade mid trend backtest.',
  factor_groups: ['trend', 'risk'],
  signal_inputs: ['factor.factor_daily'],
  default_parameters: { top_n: 20 },
  latest_evidence: 'strategy_validation',
  primary_action: 'Run backtest'
}
```

- [ ] **Step 2: Replace replay-only disabled test with LHB runnable test**

Replace the old replay-only test:

```typescript
it('runs LHB Shortline with the selected date range and risk parameters', async () => {
  render(<BacktestLabWorkspace />);

  const strategySelect = await screen.findByLabelText('strategy');
  fireEvent.change(strategySelect, { target: { value: 'lhb_shortline' } });
  fireEvent.click(screen.getByRole('button', { name: 'Run Backtest' }));

  await waitFor(() =>
    expect(apiMocks.runBacktest).toHaveBeenCalledWith({
      strategy_id: 'lhb_shortline',
      start_date: '2026-01-01',
      end_date: '2026-06-08',
      score_version: 'manual_v1',
      top_n: 20,
      rebalance_frequency: 'weekly',
      transaction_cost_bps: 10,
      max_positions: 20,
      adjust_type: 'hfq'
    })
  );
});
```

- [ ] **Step 3: Add failing comparison test**

Add:

```typescript
it('runs comparison across every runnable strategy with identical parameters', async () => {
  apiMocks.runBacktest.mockImplementation((request) =>
    Promise.resolve({
      ...makeRunResult(),
      strategy_id: request.strategy_id,
      strategy_name:
        request.strategy_id === 'lhb_shortline'
          ? 'LHB Shortline'
          : request.strategy_id === 'mid_trend'
            ? 'Mid Trend Shortline'
            : 'Manual V1 TopN Rotation',
      summary: { total_return: request.strategy_id === 'lhb_shortline' ? 0.08 : 0.12, max_drawdown: -0.05, turnover: 1.4 }
    })
  );

  render(<BacktestLabWorkspace />);
  await screen.findAllByText('Manual V1 TopN Rotation');

  fireEvent.click(screen.getByRole('button', { name: 'Run Comparison' }));

  await waitFor(() => expect(apiMocks.runBacktest).toHaveBeenCalledTimes(3));
  const requests = apiMocks.runBacktest.mock.calls.map((call) => call[0]);
  expect(requests.map((request) => request.strategy_id)).toEqual([
    'manual_v1_topn_rotation',
    'lhb_shortline',
    'mid_trend'
  ]);
  expect(requests.map(({ strategy_id, ...rest }) => rest)).toEqual([
    {
      start_date: '2026-01-01',
      end_date: '2026-06-08',
      score_version: 'manual_v1',
      top_n: 20,
      rebalance_frequency: 'weekly',
      transaction_cost_bps: 10,
      max_positions: 20,
      adjust_type: 'hfq'
    },
    {
      start_date: '2026-01-01',
      end_date: '2026-06-08',
      score_version: 'manual_v1',
      top_n: 20,
      rebalance_frequency: 'weekly',
      transaction_cost_bps: 10,
      max_positions: 20,
      adjust_type: 'hfq'
    },
    {
      start_date: '2026-01-01',
      end_date: '2026-06-08',
      score_version: 'manual_v1',
      top_n: 20,
      rebalance_frequency: 'weekly',
      transaction_cost_bps: 10,
      max_positions: 20,
      adjust_type: 'hfq'
    }
  ]);
  expect(await screen.findByRole('heading', { name: 'Strategy Comparison' })).toBeInTheDocument();
  expect(screen.getByRole('cell', { name: 'LHB Shortline' })).toBeInTheDocument();
  expect(screen.getByRole('cell', { name: 'Mid Trend Shortline' })).toBeInTheDocument();
});
```

- [ ] **Step 4: Run test to verify failure**

Run:

```bash
pnpm vitest run tests/backtest-lab-workspace.test.tsx
```

Expected: FAIL because `Run Comparison` does not exist and LHB is not currently runnable in the fixture expectations.

- [ ] **Step 5: Commit failing tests only if the team accepts red commits**

Default for this repository is commit after green. Do not commit at this red step unless explicitly requested.

---

### Task 6: Implement Frontend Run Comparison

**Files:**
- Modify: `dashboard/src/components/BacktestLabWorkspace.tsx`
- Modify: `dashboard/src/styles.css`
- Modify: `dashboard/tests/backtest-lab-workspace.test.tsx`

- [ ] **Step 1: Add comparison types and state**

In `BacktestLabWorkspace.tsx`, add:

```typescript
type ComparisonRow = {
  strategyId: string;
  strategyName: string;
  status: 'passed' | 'failed';
  result: BacktestRunResult | null;
  error: string | null;
};
```

Inside the component add:

```typescript
const [comparisonRows, setComparisonRows] = useState<ComparisonRow[]>([]);
const [isComparing, setIsComparing] = useState(false);
```

Update `invalidateRun()` to clear comparison state:

```typescript
setComparisonRows([]);
setIsComparing(false);
```

- [ ] **Step 2: Add shared request builder**

Add inside the component:

```typescript
const buildBacktestRequest = (nextStrategyId: string) => ({
  strategy_id: nextStrategyId,
  start_date: startDate,
  end_date: endDate,
  score_version: 'manual_v1',
  top_n: topN,
  rebalance_frequency: rebalanceFrequency,
  transaction_cost_bps: transactionCostBps,
  max_positions: maxPositions,
  adjust_type: 'hfq'
});
```

Use it in `submitBacktest()`:

```typescript
runBacktest(buildBacktestRequest(strategyId))
```

- [ ] **Step 3: Implement comparison action**

Add:

```typescript
const runnableStrategies = strategies.filter((strategy) => strategy.status === 'runnable');
const canCompare = runnableStrategies.length > 0 && hasValidConfig && !isRunning && !isComparing;

const submitComparison = () => {
  if (!canCompare) {
    return;
  }
  const requestId = runRequestIdRef.current + 1;
  runRequestIdRef.current = requestId;
  setIsComparing(true);
  setRunError(null);
  setResult(null);
  setComparisonRows([]);

  Promise.all(
    runnableStrategies.map((strategy) =>
      runBacktest(buildBacktestRequest(strategy.strategy_id))
        .then((payload): ComparisonRow => ({
          strategyId: strategy.strategy_id,
          strategyName: payload.strategy_name,
          status: 'passed',
          result: payload,
          error: null
        }))
        .catch((err: unknown): ComparisonRow => ({
          strategyId: strategy.strategy_id,
          strategyName: strategy.strategy_name,
          status: 'failed',
          result: null,
          error: err instanceof Error ? err.message : String(err)
        }))
    )
  ).then((rows) => {
    if (!mountedRef.current || runRequestIdRef.current !== requestId) {
      return;
    }
    setComparisonRows(rows);
    setIsComparing(false);
    const firstPassed = rows.find((row) => row.result)?.result ?? null;
    setResult(firstPassed);
  });
};
```

- [ ] **Step 4: Add button and comparison table**

Add a button beside `Run Backtest`:

```tsx
<button type="button" disabled={!canCompare} onClick={submitComparison}>
  {isComparing ? 'Comparing...' : 'Run Comparison'}
</button>
```

Render comparison before detailed result:

```tsx
{comparisonRows.length > 0 ? (
  <section className="workspace-band backtest-comparison">
    <div className="section-heading">
      <h2>Strategy Comparison</h2>
      <span className="muted">{startDate} to {endDate}</span>
    </div>
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Strategy</th>
            <th>Status</th>
            <th>Total Return</th>
            <th>Max Drawdown</th>
            <th>Turnover</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {comparisonRows.map((row) => (
            <tr key={row.strategyId}>
              <td>{row.strategyName}</td>
              <td>{row.status}</td>
              <td>{formatValue(row.result?.summary.total_return)}</td>
              <td>{formatValue(row.result?.summary.max_drawdown)}</td>
              <td>{formatValue(row.result?.summary.turnover ?? row.result?.summary.average_turnover)}</td>
              <td>{row.error ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </section>
) : null}
```

- [ ] **Step 5: Update replay-only note**

Change disabled reason text to be generic:

```typescript
Backtest Lab runs runnable research strategies only. Use Strategy Validation to inspect replay evidence.
```

With all catalog strategies runnable this note will only appear for future planned or replay-only rows.

- [ ] **Step 6: Add styles**

In `styles.css`:

```css
.backtest-comparison {
  display: grid;
  gap: 10px;
}

.backtest-controls button + button {
  margin-left: 0;
}
```

Keep both buttons in the existing grid; do not nest controls in cards.

- [ ] **Step 7: Run frontend component tests**

Run:

```bash
pnpm vitest run tests/backtest-lab-workspace.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add dashboard/src/components/BacktestLabWorkspace.tsx dashboard/src/styles.css dashboard/tests/backtest-lab-workspace.test.tsx
git commit -m "feat: add backtest strategy comparison"
```

---

### Task 7: Add Playwright Full Flow Coverage

**Files:**
- Modify: `dashboard/tests/platform-full-flow.spec.ts`

- [ ] **Step 1: Add mocked API route coverage for comparison**

If using the mocked smoke spec, add strategy fixtures where all five strategy rows have `status: 'runnable'`. Add a `/api/backtests/run` route that returns the posted `strategy_id` in the result:

```typescript
await page.route('/api/backtests/run', async (route) => {
  const request = route.request().postDataJSON();
  await route.fulfill({
    json: {
      strategy_id: request.strategy_id,
      strategy_name: request.strategy_id,
      read_only: true,
      config: request,
      summary: {
        total_return: request.strategy_id === 'lhb_shortline' ? 0.08 : 0.12,
        max_drawdown: -0.05,
        turnover: 1.2
      },
      equity_curve: [{ date: '2026-06-08', equity: 1.08, drawdown: -0.02 }],
      positions: [{ rebalance_date: '2026-06-05', asset_id: 'CN:SZ:300951', weight: 0.05 }],
      trades: [{ execution_date: '2026-06-08', asset_id: 'CN:SZ:300951', side: 'buy' }]
    }
  });
});
```

- [ ] **Step 2: Add browser steps**

Add:

```typescript
await page.getByRole('button', { name: 'Open Backtest Lab workspace' }).click();
await page.getByLabel('strategy', { exact: true }).selectOption('lhb_shortline');
await page.getByRole('button', { name: 'Run Backtest' }).click();
await expect(page.getByRole('heading', { name: 'Read-only backtest' })).toBeVisible();
await expect(page.getByText('lhb_shortline')).toBeVisible();

await page.getByRole('button', { name: 'Run Comparison' }).click();
await expect(page.getByRole('heading', { name: 'Strategy Comparison' })).toBeVisible();
await expect(page.getByRole('cell', { name: 'lhb_shortline' })).toBeVisible();
await expect(page.getByRole('cell', { name: 'manual_v1_topn_rotation' })).toBeVisible();
```

- [ ] **Step 3: Run Playwright spec**

Run:

```bash
pnpm test:e2e
```

Expected: PASS for all configured Playwright tests.

- [ ] **Step 4: Commit**

```bash
git add dashboard/tests/platform-full-flow.spec.ts
git commit -m "test: cover backtest comparison flow"
```

---

### Task 8: Full Verification Against Local API And Dashboard

**Files:**
- No source edits expected.

- [ ] **Step 1: Run backend tests**

Run:

```bash
pytest tests/test_dashboard_backtests.py tests/test_strategy_backtest_adapters.py tests/test_vectorized_topn_backtest.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 2: Run full dashboard unit tests**

Run:

```bash
cd dashboard && pnpm test
```

Expected: all Vitest files PASS.

- [ ] **Step 3: Run dashboard build**

Run:

```bash
cd dashboard && pnpm build
```

Expected: TypeScript and Vite build complete with exit code 0.

- [ ] **Step 4: Run Playwright**

Run:

```bash
cd dashboard && pnpm test:e2e
```

Expected: all Playwright tests PASS.

- [ ] **Step 5: Run live API smoke for every strategy**

With the API on `http://127.0.0.1:8765`, run:

```bash
for strategy in manual_v1_topn_rotation lhb_shortline mid_trend tech_bottleneck position_control; do
  curl -sS http://127.0.0.1:8765/api/backtests/run \
    -H 'Content-Type: application/json' \
    -d "{\"strategy_id\":\"$strategy\",\"start_date\":\"2026-01-01\",\"end_date\":\"2026-06-08\",\"top_n\":20,\"rebalance_frequency\":\"weekly\",\"transaction_cost_bps\":10,\"max_positions\":20,\"score_version\":\"manual_v1\",\"adjust_type\":\"hfq\"}" \
    | /Users/xiwei/stock_research/.venv/bin/python -m json.tool \
    | rg '\"strategy_id\"|\"summary\"|\"equity_curve\"|\"positions\"|\"trades\"'
done
```

Expected: each strategy returns `strategy_id`, `summary`, `equity_curve`, `positions`, and `trades`. If a strategy has no selected-range signals, fix the adapter fallback or empty-data handling before marking the work complete.

- [ ] **Step 6: Run live Playwright comparison smoke**

Run a small browser check:

```bash
cd dashboard
node <<'JS'
const { chromium } = require('@playwright/test');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 980 } });
  await page.goto('http://127.0.0.1:5174/', { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'Open Backtest Lab workspace' }).click();
  await page.getByRole('button', { name: 'Run Comparison' }).click();
  await page.getByRole('heading', { name: 'Strategy Comparison' }).waitFor();
  const rows = await page.locator('.backtest-comparison tbody tr').count();
  console.log(JSON.stringify({ rows }, null, 2));
  await browser.close();
})();
JS
```

Expected output includes:

```json
{
  "rows": 5
}
```

- [ ] **Step 7: Final git status**

Run:

```bash
git status --short
```

Expected: clean working tree.

---

## Self-Review

- Spec coverage: The plan covers adapter registry, every strategy runnable, per-strategy unit tests, `Run Comparison`, frontend tests, Playwright flow, and live API smoke.
- Placeholder scan: Checked for incomplete markers and unspecified implementation steps; none remain.
- Type consistency: Backend adapter names match the spec and tests. Frontend request fields match `BacktestRunRequest`. Comparison rows reuse `BacktestRunResult`.
