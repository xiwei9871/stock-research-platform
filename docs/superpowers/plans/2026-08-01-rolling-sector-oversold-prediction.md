# Rolling Sector Oversold Prediction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a database-only, daily rolling system that identifies oversold and repairable industries/concepts, ranks consumer-facing and other sector stocks for a 1/3/5-trading-day rebound, freezes an auditable snapshot at every anchor date, and evaluates each prediction without future leakage.

**Architecture:** Add a focused `stock_research.rolling_oversold` package rather than changing the existing consumer V2 defaults. The package loads point-in-time market, sector, membership, status, finance, and valuation data from the database, computes market regime and sector gates, scores stocks only inside gated sectors, writes immutable anchor snapshots, and evaluates delayed outcomes. Existing `strategy_data_policy` and `DataGap`/backfill-request behavior remain the single source of truth when required database coverage is absent.

**Tech Stack:** Python 3.11, pandas, psycopg database helpers, dataclasses/enums, the existing `stock_research.consumer_oversold` feature components, pytest, atomic CSV/JSON/Markdown artifacts, and the existing `stock-research` CLI.

---

## File map

Create the following focused package files:

- `src/stock_research/rolling_oversold/__init__.py` — public exports and package version.
- `src/stock_research/rolling_oversold/contracts.py` — immutable configuration, enum values, required snapshot columns, and validation.
- `src/stock_research/rolling_oversold/loaders.py` — DB-only loaders for calendar, index bars, stock bars/status, industry/concept bars, memberships, and PIT finance/valuation inputs.
- `src/stock_research/rolling_oversold/preflight.py` — coverage checks, gap classification, and backfill-request persistence.
- `src/stock_research/rolling_oversold/market_regime.py` — market-wide breadth, trend, liquidity, dispersion, and regime state.
- `src/stock_research/rolling_oversold/sector_scoring.py` — industry/concept oversold, repairability, direction, recovery state, and gate status.
- `src/stock_research/rolling_oversold/stock_scoring.py` — stock feature adapter, score composition, residual-space logic, and lifecycle state.
- `src/stock_research/rolling_oversold/snapshots.py` — immutable anchor snapshot construction, comparison to the prior snapshot, and atomic artifact writes.
- `src/stock_research/rolling_oversold/outcomes.py` — 1/3/5-trading-day forward returns, pending windows, and calibration summaries.
- `src/stock_research/rolling_oversold/pipeline.py` — replay and daily orchestration with stage timings and runtime budget enforcement.
- `src/stock_research/rolling_oversold/reporting.py` — CSV/JSON/Markdown report rendering.

Add the following tests:

- `tests/test_rolling_oversold_contracts.py`
- `tests/test_rolling_oversold_loaders_preflight.py`
- `tests/test_rolling_oversold_market_regime.py`
- `tests/test_rolling_oversold_sector_scoring.py`
- `tests/test_rolling_oversold_stock_scoring.py`
- `tests/test_rolling_oversold_snapshots.py`
- `tests/test_rolling_oversold_outcomes.py`
- `tests/test_rolling_oversold_cli.py`
- `tests/test_rolling_oversold_pipeline.py`

Modify only these existing integration points:

- `src/stock_research/cli.py` — register replay, daily, and focused-report commands and dispatch to the new package.
- The new `tests/test_rolling_oversold_cli.py` file — assert command parsing without touching a database; no existing consumer CLI test is modified.

Do not modify the scoring defaults or outputs of `stock_research.consumer_oversold` while this plan is implemented. The new package may import its generic feature functions through an adapter, but it must pass an explicit rolling configuration and preserve the consumer pipeline's current tests.

## Task 1: Freeze the rolling data contract

**Files:**
- Create: `src/stock_research/rolling_oversold/__init__.py`
- Create: `src/stock_research/rolling_oversold/contracts.py`
- Test: `tests/test_rolling_oversold_contracts.py`

- [ ] **Step 1: Write the failing tests for configuration, states, and snapshot columns.**

```python
from datetime import date

import pytest

from stock_research.rolling_oversold.contracts import (
    GateStatus,
    RecoveryState,
    RollingOversoldConfig,
    StockLifecycle,
    validate_snapshot_columns,
)


def test_config_accepts_20260721_anchor_without_hardcoding_the_date():
    config = RollingOversoldConfig(anchor_start_date=date(2026, 7, 21))

    assert config.anchor_start_date == date(2026, 7, 21)
    assert config.forecast_horizons == (1, 3, 5)
    assert config.score_version == "rolling_oversold_v1"


def test_config_rejects_non_forward_or_duplicate_horizons():
    with pytest.raises(ValueError, match="forecast_horizons"):
        RollingOversoldConfig(
            anchor_start_date=date(2026, 7, 21),
            forecast_horizons=(5, 3, 3),
        )


def test_state_values_are_stable_strings():
    assert GateStatus.CONFIRMED.value == "confirmed"
    assert RecoveryState.REPAIR_WITH_RESIDUAL_SPACE.value == "repair_with_residual_space"
    assert StockLifecycle.INVALIDATED.value == "invalidated"


def test_snapshot_validation_reports_missing_required_fields():
    errors = validate_snapshot_columns({"anchor_date", "asset_id"})

    assert "data_cutoff_date" in errors
    assert "sector_gate_status" in errors
    assert "stock_lifecycle" in errors
```

- [ ] **Step 2: Run the contract tests to verify the new package is absent.**

Run: `rtk pytest tests/test_rolling_oversold_contracts.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'stock_research.rolling_oversold'`.

- [ ] **Step 3: Implement the immutable contract and validation surface.**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from collections.abc import Sequence


class GateStatus(str, Enum):
    CONFIRMED = "confirmed"
    WATCH = "watch"
    BLOCKED = "blocked"


class RecoveryState(str, Enum):
    FRESH_OVERSOLD = "fresh_oversold"
    REPAIRING = "repairing"
    REPAIRED = "repaired"
    STRUCTURALLY_WEAK = "structurally_weak"
    UNKNOWN = "unknown"


class StockLifecycle(str, Enum):
    NEW_OVERSOLD = "new_oversold"
    EXPECTED_REPAIR = "expected_repair"
    CONFIRMED_REPAIR = "confirmed_repair"
    REPAIR_WITH_RESIDUAL_SPACE = "repair_with_residual_space"
    INVALIDATED = "invalidated"


REQUIRED_SNAPSHOT_COLUMNS = frozenset(
    {
        "snapshot_id",
        "anchor_date",
        "data_cutoff_date",
        "score_version",
        "market_regime",
        "sector_system",
        "sector_code",
        "sector_name",
        "sector_oversold_score",
        "sector_repairability_score",
        "sector_direction_score",
        "sector_recovery_state",
        "sector_gate_status",
        "asset_id",
        "stock_score",
        "stock_rank",
        "stock_lifecycle",
        "previous_snapshot_id",
        "rank_delta",
        "lifecycle_delta",
    }
)


@dataclass(frozen=True)
class RollingOversoldConfig:
    anchor_start_date: date
    anchor_end_date: date | None = None
    forecast_horizons: Sequence[int] = (1, 3, 5)
    industry_systems: Sequence[str] | None = None
    concept_systems: Sequence[str] | None = None
    index_ids: Sequence[str] = (
        "SSE_COMPOSITE",
        "SZSE_COMPONENT",
        "CSI_300",
        "STAR_50",
        "BSE_50",
    )
    sector_top_n: int = 30
    stock_top_n: int = 20
    repair_trigger_return: float = 0.10
    residual_high_distance: float = 0.20
    score_version: str = "rolling_oversold_v1"
    adjust_type: str = "qfq"
    runtime_budget_seconds: int = 3600

    def __post_init__(self) -> None:
        if self.anchor_end_date is not None and self.anchor_end_date < self.anchor_start_date:
            raise ValueError("anchor_end_date must be on or after anchor_start_date")
        if tuple(sorted(set(self.forecast_horizons))) != self.forecast_horizons:
            raise ValueError("forecast_horizons must be unique and sorted")
        if not self.forecast_horizons or any(h <= 0 for h in self.forecast_horizons):
            raise ValueError("forecast_horizons must contain positive trading-day horizons")
        if self.sector_top_n <= 0 or self.stock_top_n <= 0:
            raise ValueError("sector_top_n and stock_top_n must be positive")
        if not 0 < self.repair_trigger_return < 1:
            raise ValueError("repair_trigger_return must be between zero and one")
        if not 0 < self.residual_high_distance < 1:
            raise ValueError("residual_high_distance must be between zero and one")
        if self.adjust_type not in {"qfq", "hfq", "raw"}:
            raise ValueError("adjust_type must be qfq, hfq, or raw")
        if self.runtime_budget_seconds <= 0:
            raise ValueError("runtime_budget_seconds must be positive")


def validate_snapshot_columns(columns: set[str] | list[str]) -> list[str]:
    return sorted(REQUIRED_SNAPSHOT_COLUMNS.difference(columns))
```

- [ ] **Step 4: Run the contract tests to verify they pass.**

Run: `rtk pytest tests/test_rolling_oversold_contracts.py -q`

Expected: `4 passed`.

- [ ] **Step 5: Commit the contract surface.**

```bash
rtk git add src/stock_research/rolling_oversold/__init__.py src/stock_research/rolling_oversold/contracts.py tests/test_rolling_oversold_contracts.py
rtk git commit -m "feat: define rolling oversold contracts"
```

## Task 2: Add DB-only loaders and point-in-time preflight

**Files:**
- Create: `src/stock_research/rolling_oversold/loaders.py`
- Create: `src/stock_research/rolling_oversold/preflight.py`
- Test: `tests/test_rolling_oversold_loaders_preflight.py`
- Modify: `src/stock_research/strategy_data_policy.py` only if a small import adapter is required; preserve its public behavior.

- [ ] **Step 1: Write failing loader and preflight tests.**

```python
from datetime import date

import pandas as pd

from stock_research.rolling_oversold.contracts import RollingOversoldConfig
from stock_research.rolling_oversold.loaders import load_rolling_inputs
from stock_research.rolling_oversold.preflight import run_rolling_preflight


def test_loader_uses_anchor_cutoff_and_pit_membership(monkeypatch):
    calls = []

    def fake_query(service, sql, params):
        calls.append((sql, params))
        if "market.trading_calendar" in sql:
            return pd.DataFrame({"trade_date": [date(2026, 7, 21)]})
        if "core.industry_membership" in sql:
            return pd.DataFrame(
                {
                    "asset_id": ["A"],
                    "industry_system": ["csrc"],
                    "industry_code": ["C1"],
                    "industry_name": ["消费"],
                    "level": [1],
                    "start_date": [date(2026, 1, 1)],
                    "end_date": [None],
                }
            )
        return pd.DataFrame()

    monkeypatch.setattr("stock_research.rolling_oversold.loaders.query_dataframe", fake_query)
    config = RollingOversoldConfig(anchor_start_date=date(2026, 7, 21))
    result = load_rolling_inputs(anchor_date=date(2026, 7, 21), config=config, service="research")

    assert result.anchor_date == date(2026, 7, 21)
    membership_sql = next(sql for sql, _ in calls if "core.industry_membership" in sql)
    assert "start_date <= %s" in membership_sql
    assert "end_date IS NULL OR end_date > %s" in membership_sql


def test_preflight_blocks_missing_sector_bars_and_writes_a_gap(monkeypatch, tmp_path):
    inputs = {
        "industry_membership": pd.DataFrame(
            [{"industry_system": "csrc", "industry_code": "C1", "asset_id": "A"}]
        ),
        "industry_bars": pd.DataFrame(
            columns=["industry_system", "industry_code", "trade_date", "close"]
        ),
    }
    written = []
    monkeypatch.setattr(
        "stock_research.rolling_oversold.preflight.write_backfill_request",
        lambda gap, **kwargs: written.append((gap, kwargs)),
    )

    result = run_rolling_preflight(
        inputs,
        anchor_date=date(2026, 7, 21),
        output_dir=tmp_path,
    )

    assert result.blocked is True
    assert any(g.dataset == "market.industry_daily_bar" for g in result.gaps)
    assert written
```

- [ ] **Step 2: Run the new tests and verify they fail before the loaders exist.**

Run: `rtk pytest tests/test_rolling_oversold_loaders_preflight.py -q`

Expected: FAIL with an import error for `stock_research.rolling_oversold.loaders`.

- [ ] **Step 3: Implement DB-only queries with explicit cutoff and coverage metadata.**

Implement these exact interfaces:

```python
@dataclass(frozen=True)
class RollingInputs:
    anchor_date: date
    data_cutoff_date: date
    trading_dates: pd.DataFrame
    index_bars: pd.DataFrame
    stock_bars: pd.DataFrame
    stock_status: pd.DataFrame
    industry_membership: pd.DataFrame
    concept_membership: pd.DataFrame
    industry_bars: pd.DataFrame
    concept_bars: pd.DataFrame
    finance: pd.DataFrame
    valuation: pd.DataFrame


def load_rolling_inputs(
    *,
    anchor_date: date,
    config: RollingOversoldConfig,
    service: str,
) -> RollingInputs:
    """Read all strategy inputs from the configured database, never from a network source."""
```

The loader must issue these queries, each filtered by `trade_date <= anchor_date` or by a PIT interval:

- `market.trading_calendar` for the last completed session and all trading dates needed by the 252-session lookback and 5-session outcome windows.
- `market.index_daily_bar` for `config.index_ids`, with `index_id`, `trade_date`, `close`, `preclose`, `volume`, and `amount`.
- `market_daily_bar` for `asset_id`, `trade_date`, `close`, `high`, `low`, `pct_chg`, `volume`, `amount`, and `adjust_type = config.adjust_type`.
- `core.asset_status_daily` for tradability, ST, suspension, and limit flags.
- `core.industry_membership` with `start_date <= anchor_date AND (end_date IS NULL OR end_date > anchor_date)`.
- `core.concept_membership` with the same PIT interval.
- `market.industry_daily_bar` and `market.concept_daily_bar` through the anchor date.
- The existing PIT finance and valuation loaders used by consumer V2, constrained to information published on or before `anchor_date`.

The loader must return `data_cutoff_date` equal to the latest `is_open = true` calendar date not later than `anchor_date`, and the preflight must record `DataGap` through the existing policy after classifying the missing dataset. It must not import or invoke `akshare`, `baostock`, or any ingestion function.

Implement `run_rolling_preflight(inputs, anchor_date, output_dir) -> PreflightResult` with these checks:

1. Every requested index has at least 252 prior sessions or produces a named `market.index_daily_bar` gap.
2. Every active industry/concept membership key has a sector bar on the anchor cutoff or produces a named sector-bar gap.
3. Every selected asset has a stock bar and tradability status on the cutoff or produces an asset-history/status gap.
4. Finance and valuation coverage is reported separately; a missing row never becomes a zero score.
5. Any gap writes one backfill request through `strategy_data_policy.write_backfill_request` and sets `blocked = True` for the scoring pipeline.

The preflight output must contain `blocked`, `data_cutoff_date`, `checked_datasets`, `coverage_rows`, and a list of `DataGap` objects. Persist `backfill_requests.csv` and `preflight.json` in the run directory.

- [ ] **Step 4: Run the loader and preflight tests.**

Run: `rtk pytest tests/test_rolling_oversold_loaders_preflight.py -q`

Expected: `2 passed`.

- [ ] **Step 5: Commit the DB-only boundary.**

```bash
rtk git add src/stock_research/rolling_oversold/loaders.py src/stock_research/rolling_oversold/preflight.py tests/test_rolling_oversold_loaders_preflight.py
rtk git commit -m "feat: add db-only rolling oversold inputs"
```

## Task 3: Compute market regime and sector state

**Files:**
- Create: `src/stock_research/rolling_oversold/market_regime.py`
- Create: `src/stock_research/rolling_oversold/sector_scoring.py`
- Test: `tests/test_rolling_oversold_market_regime.py`
- Test: `tests/test_rolling_oversold_sector_scoring.py`

- [ ] **Step 1: Write deterministic synthetic-frame tests before implementation.**

```python
def test_market_regime_labels_panic_rebound_watch_after_breadth_shock_and_rebound():
    frame = make_index_and_stock_frame(
        dates=["2026-07-17", "2026-07-20", "2026-07-21"],
        index_returns=[-0.03, -0.04, 0.02],
        stock_returns=[[-0.08, -0.06], [-0.07, -0.05], [0.04, 0.03]],
    )

    result = compute_market_regime_features(frame, anchor_date=date(2026, 7, 21))

    assert result["market_regime"] == "panic_rebound_watch"
    assert result["breadth_below_ma20"] > 0.5
    assert result["data_cutoff_date"] == date(2026, 7, 21)


def test_sector_score_marks_deep_drawdown_with_positive_repairability_as_confirmed():
    bars = make_sector_bars(
        sector_code="C1",
        closes=[100, 96, 92, 88, 84, 86],
        dates=["2026-07-14", "2026-07-15", "2026-07-16", "2026-07-17", "2026-07-20", "2026-07-21"],
    )

    result = score_sector_states(
        bars,
        membership=make_membership("C1", assets=["A", "B"]),
        market_regime={"market_regime": "neutral", "market_direction_score": 0.4},
        anchor_date=date(2026, 7, 21),
    )

    row = result.iloc[0]
    assert row["sector_oversold_score"] >= 70
    assert row["sector_repairability_score"] >= 60
    assert row["sector_gate_status"] == "confirmed"
    assert row["sector_recovery_state"] == "repairing"


def test_sector_near_high_is_repaired_not_fresh_oversold():
    bars = make_sector_bars(
        sector_code="C2",
        closes=[100, 101, 102, 103, 104, 105],
        dates=["2026-07-14", "2026-07-15", "2026-07-16", "2026-07-17", "2026-07-20", "2026-07-21"],
    )

    result = score_sector_states(
        bars,
        membership=make_membership("C2", assets=["A", "B"]),
        market_regime={"market_regime": "risk_on", "market_direction_score": 0.8},
        anchor_date=date(2026, 7, 21),
    )

    assert result.iloc[0]["sector_recovery_state"] == "repaired"
    assert result.iloc[0]["sector_gate_status"] != "confirmed"
```

- [ ] **Step 2: Run the two test files to verify the functions do not exist.**

Run: `rtk pytest tests/test_rolling_oversold_market_regime.py tests/test_rolling_oversold_sector_scoring.py -q`

Expected: FAIL with import errors for `compute_market_regime_features` and `score_sector_states`.

- [ ] **Step 3: Implement the vectorized feature calculations and hard gates.**

Implement these signatures:

```python
def compute_market_regime_features(
    source: MarketRegimeSource,
    *,
    anchor_date: date,
) -> dict[str, object]:
    """Return one frozen market-state record for the anchor cutoff."""


def score_sector_states(
    sector_bars: pd.DataFrame,
    *,
    membership: pd.DataFrame,
    market_regime: dict[str, object],
    anchor_date: date,
) -> pd.DataFrame:
    """Return one row per industry or concept sector represented in sector_bars."""
```

For each sector calculate, using only rows through `anchor_date`, these columns:

- `ret_5d`, `ret_10d`, `ret_20d`, `relative_ret_20d`.
- `drawdown_60d`, `drawdown_120d`, `drawdown_252d`, `price_position_252d`.
- `below_ma20_ratio`, `below_ma60_ratio`, `new_low_60d_ratio`, `up_ratio_20d`.
- `amount_ratio_5_20`, `turnover_or_activity_score`, `dispersion_20d`, `recent_recovery_ratio`.
- `fundamental_quality_score`, `valuation_support_score`, `risk_concentration_score`.
- `sector_oversold_score`, `sector_repairability_score`, `sector_direction_score`.
- `sector_recovery_state` with values from `RecoveryState` and `sector_gate_status` with values from `GateStatus`.

Use a 0–100 percentile/rank scale clipped to the 5th and 95th percentiles for size/activity so microcaps cannot receive a mechanical maximum. Set `sector_gate_status = blocked` when history, membership, or sector bar coverage is incomplete; set `watch` for repaired/structurally weak sectors or insufficient direction confirmation; set `confirmed` only when oversold and repairability exceed their configured gates and direction is not negative. Market regime modifies the gate threshold but never bypasses a blocked data state.

Compute market state from index bars plus stock breadth, status flags, aggregate amount, 20-day dispersion, and recent rebound breadth. Emit exactly one of `risk_on`, `neutral`, `risk_off`, or `panic_rebound_watch`, plus `market_direction_score`, `breadth_below_ma20`, `breadth_below_ma60`, `amount_ratio_5_20`, and `data_cutoff_date`.

- [ ] **Step 4: Run the deterministic tests and inspect the result columns.**

Run: `rtk pytest tests/test_rolling_oversold_market_regime.py tests/test_rolling_oversold_sector_scoring.py -q`

Expected: `3 passed`, with no NaN in any required state or gate column for the complete synthetic fixtures.

- [ ] **Step 5: Commit the regime and sector scorer.**

```bash
rtk git add src/stock_research/rolling_oversold/market_regime.py src/stock_research/rolling_oversold/sector_scoring.py tests/test_rolling_oversold_market_regime.py tests/test_rolling_oversold_sector_scoring.py
rtk git commit -m "feat: score rolling market and sector states"
```

## Task 4: Rank stocks inside gated sectors and model repair lifecycle

**Files:**
- Create: `src/stock_research/rolling_oversold/stock_scoring.py`
- Test: `tests/test_rolling_oversold_stock_scoring.py`

- [ ] **Step 1: Write failing tests for gated selection, residual space, and invalidation.**

```python
def test_stock_scoring_excludes_blocked_sectors_and_ranks_by_actual_score():
    candidates = make_stock_features(
        [
            {"asset_id": "A", "sector_code": "C1", "close": 10, "high_252d": 20, "ret_20d": -0.30},
            {"asset_id": "B", "sector_code": "C2", "close": 10, "high_252d": 20, "ret_20d": -0.28},
        ]
    )
    sectors = make_sector_states(
        [
            {"sector_code": "C1", "sector_gate_status": "confirmed", "sector_repairability_score": 80},
            {"sector_code": "C2", "sector_gate_status": "blocked", "sector_repairability_score": 95},
        ]
    )

    result = score_rolling_stock_candidates(
        candidates,
        sectors,
        top_n=20,
        config=RollingOversoldConfig(anchor_start_date=date(2026, 7, 21)),
    )

    assert result["asset_id"].tolist() == ["A"]
    assert result.iloc[0]["stock_rank"] == 1


def test_twelve_percent_rebound_is_retained_when_residual_space_remains():
    result = classify_stock_lifecycle(
        anchor_return=0.12,
        distance_to_252d_high=0.25,
        sector_recovery_state="repairing",
        sector_gate_status="confirmed",
        repair_trigger_return=0.10,
        residual_high_distance=0.20,
    )

    assert result == "repair_with_residual_space"


def test_rebound_near_high_is_confirmed_repair_and_not_a_new_oversold_candidate():
    result = classify_stock_lifecycle(
        anchor_return=0.12,
        distance_to_252d_high=0.05,
        sector_recovery_state="repaired",
        sector_gate_status="watch",
        repair_trigger_return=0.10,
        residual_high_distance=0.20,
    )

    assert result == "confirmed_repair"
```

- [ ] **Step 2: Run the stock tests to verify they fail.**

Run: `rtk pytest tests/test_rolling_oversold_stock_scoring.py -q`

Expected: FAIL with import errors for `score_rolling_stock_candidates` and `classify_stock_lifecycle`.

- [ ] **Step 3: Implement the adapter and lifecycle classifier.**

Implement these interfaces:

```python
def classify_stock_lifecycle(
    *,
    anchor_return: float,
    distance_to_252d_high: float,
    sector_recovery_state: str,
    sector_gate_status: str,
    repair_trigger_return: float,
    residual_high_distance: float,
) -> str:
    if sector_gate_status == "blocked":
        return "invalidated"
    if anchor_return >= repair_trigger_return:
        if distance_to_252d_high >= residual_high_distance and sector_recovery_state in {
            "fresh_oversold",
            "repairing",
        }:
            return "repair_with_residual_space"
        return "confirmed_repair"
    if sector_recovery_state == "fresh_oversold":
        return "new_oversold"
    return "expected_repair"


def score_rolling_stock_candidates(
    stock_features: pd.DataFrame,
    sector_states: pd.DataFrame,
    *,
    top_n: int,
    config: RollingOversoldConfig,
) -> pd.DataFrame:
    """Join sector context, score only non-blocked sectors, and return deterministic ranks."""
```

Use existing consumer V2 feature functions for price/technical/fundamental/valuation features through a thin adapter. The adapter must pass `anchor_date` into every feature loader and must not call an external source. Compose the score from oversold depth, residual distance to the 252-session high, stock/sector excess return, repairability, direction, activity, quality, valuation, and a size elasticity component clipped to the 5th–95th percentile. Store both component columns and `stock_score` so a later report can explain why a stock outranked another.

Join sector state by `(sector_system, sector_code)` and drop only rows whose sector gate is `blocked`; missing joins must create a `DataGap` before scoring rather than silently dropping the asset. Keep a stock that has already risen 10–20% when its distance to the 252-session high still exceeds `residual_high_distance` and its sector remains `confirmed`; mark it `repair_with_residual_space` instead of deleting it. A stock close to its high or inside a repaired/weak sector becomes `confirmed_repair` and is retained only for evaluation, not as a fresh entry.

- [ ] **Step 4: Run the stock tests and the existing consumer V2 focused suite.**

Run: `rtk pytest tests/test_rolling_oversold_stock_scoring.py tests/test_consumer_oversold_scoring.py tests/test_consumer_oversold_pipeline.py tests/test_consumer_oversold_v2_evaluation.py -q`

Expected: new tests pass and the existing consumer tests remain green; no consumer score-version output changes.

- [ ] **Step 5: Commit the stock scorer.**

```bash
rtk git add src/stock_research/rolling_oversold/stock_scoring.py tests/test_rolling_oversold_stock_scoring.py
rtk git commit -m "feat: rank rolling oversold stocks with lifecycle states"
```

## Task 5: Persist immutable snapshots and rolling revisions

**Files:**
- Create: `src/stock_research/rolling_oversold/snapshots.py`
- Test: `tests/test_rolling_oversold_snapshots.py`

- [ ] **Step 1: Write failing tests for snapshot identity, immutability, and rank/state deltas.**

```python
def test_snapshot_id_contains_anchor_and_score_version():
    snapshot = build_rolling_snapshot(
        anchor_date=date(2026, 7, 21),
        data_cutoff_date=date(2026, 7, 21),
        market_regime={"market_regime": "neutral"},
        sector_states=make_sector_states([{"sector_code": "C1"}]),
        stock_candidates=make_stock_candidates([{"asset_id": "A", "stock_rank": 1}]),
        previous_snapshot=None,
        score_version="rolling_oversold_v1",
    )

    assert snapshot["snapshot_id"] == "rolling_oversold_v1|2026-07-21"


def test_write_snapshot_never_overwrites_existing_anchor(tmp_path):
    snapshot = make_snapshot(snapshot_id="rolling_oversold_v1|2026-07-21")
    first = write_rolling_snapshot(snapshot, output_dir=tmp_path)
    second = write_rolling_snapshot(snapshot, output_dir=tmp_path)

    assert first["manifest_path"] == second["manifest_path"]
    assert first["status"] == "created"
    assert second["status"] == "already_exists_identical"


def test_revision_links_previous_rank_and_lifecycle():
    previous = make_snapshot(
        snapshot_id="rolling_oversold_v1|2026-07-20",
        stock_rows=[{"asset_id": "A", "stock_rank": 5, "stock_lifecycle": "expected_repair"}],
    )
    current = build_rolling_snapshot(
        anchor_date=date(2026, 7, 21),
        data_cutoff_date=date(2026, 7, 21),
        market_regime={"market_regime": "neutral"},
        sector_states=make_sector_states([{"sector_code": "C1"}]),
        stock_candidates=make_stock_candidates(
            [{"asset_id": "A", "stock_rank": 2, "stock_lifecycle": "repair_with_residual_space"}]
        ),
        previous_snapshot=previous,
        score_version="rolling_oversold_v1",
    )

    row = current["stock_candidates"].iloc[0]
    assert row["previous_snapshot_id"] == "rolling_oversold_v1|2026-07-20"
    assert row["rank_delta"] == 3
    assert row["lifecycle_delta"] == "expected_repair->repair_with_residual_space"
```

- [ ] **Step 2: Run the snapshot tests and verify they fail.**

Run: `rtk pytest tests/test_rolling_oversold_snapshots.py -q`

Expected: FAIL with import errors for the snapshot functions.

- [ ] **Step 3: Implement deterministic snapshot assembly and atomic writes.**

Implement:

```python
def build_rolling_snapshot(
    *,
    anchor_date: date,
    data_cutoff_date: date,
    market_regime: dict[str, object],
    sector_states: pd.DataFrame,
    stock_candidates: pd.DataFrame,
    previous_snapshot: dict[str, object] | None,
    score_version: str,
) -> dict[str, object]:
    """Build a normalized snapshot; repeated calls with the same inputs are byte-stable."""


def write_rolling_snapshot(
    snapshot: dict[str, object],
    *,
    output_dir: str | Path,
) -> dict[str, object]:
    """Write one anchor directory without replacing an existing different snapshot."""
```

Use the directory `rolling_sector_oversold/anchor=YYYY-MM-DD/version=<score_version>/`. Write `manifest.json`, `market_regime.csv`, `sector_states.csv`, `stock_candidates.csv`, `preflight.json`, and `backfill_requests.csv` through the repository's atomic file pattern. The manifest must include `snapshot_id`, `anchor_date`, `data_cutoff_date`, `score_version`, row counts, SHA-256 hashes for each artifact, runtime stage timings, and `previous_snapshot_id`. If the target manifest exists and hashes match, return `already_exists_identical`; if any hash differs, raise a clear immutability error and leave all existing files untouched.

When a previous snapshot is supplied, join stock rows by `asset_id` and sector rows by `(sector_system, sector_code)`. Compute rank delta as `previous_rank - current_rank` and lifecycle/state deltas as `old->new`; assets absent from the current gated universe get a revision row with lifecycle `invalidated` and reason `sector_gate_or_data_change`.

- [ ] **Step 4: Run the snapshot tests.**

Run: `rtk pytest tests/test_rolling_oversold_snapshots.py -q`

Expected: `3 passed` and a second write of the same snapshot reports `already_exists_identical`.

- [ ] **Step 5: Commit snapshot persistence.**

```bash
rtk git add src/stock_research/rolling_oversold/snapshots.py tests/test_rolling_oversold_snapshots.py
rtk git commit -m "feat: persist immutable rolling snapshots"
```

## Task 6: Add 1/3/5-trading-day outcome evaluation

**Files:**
- Create: `src/stock_research/rolling_oversold/outcomes.py`
- Test: `tests/test_rolling_oversold_outcomes.py`

- [ ] **Step 1: Write failing tests for completed and pending horizons.**

```python
def test_evaluate_snapshot_uses_trading_sessions_not_calendar_days():
    snapshot = make_snapshot(
        anchor_date="2026-07-21",
        stock_rows=[{"asset_id": "A", "anchor_close": 10.0}],
    )
    bars = make_daily_bars(
        asset_id="A",
        dates=["2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24", "2026-07-27", "2026-07-28"],
        closes=[10.0, 10.2, 10.1, 10.4, 10.6, 10.5],
    )

    result = evaluate_snapshot(snapshot, bars=bars, evaluation_cutoff=date(2026, 7, 28))

    row = result[result["asset_id"] == "A"].iloc[0]
    assert row["forward_1d_return"] == 0.02
    assert round(row["forward_3d_return"], 6) == 0.04
    assert row["forward_5d_return"] == 0.05
    assert row["forward_5d_status"] == "complete"


def test_evaluation_marks_horizon_pending_without_future_bar():
    snapshot = make_snapshot(
        anchor_date="2026-07-30",
        stock_rows=[{"asset_id": "A", "anchor_close": 10.0}],
    )
    bars = make_daily_bars(
        asset_id="A",
        dates=["2026-07-30", "2026-07-31"],
        closes=[10.0, 10.5],
    )

    result = evaluate_snapshot(snapshot, bars=bars, evaluation_cutoff=date(2026, 7, 31))

    row = result.iloc[0]
    assert row["forward_1d_status"] == "complete"
    assert row["forward_3d_status"] == "pending"
    assert pd.isna(row["forward_3d_return"])
```

- [ ] **Step 2: Run the outcome tests to verify they fail.**

Run: `rtk pytest tests/test_rolling_oversold_outcomes.py -q`

Expected: FAIL with import errors for `evaluate_snapshot`.

- [ ] **Step 3: Implement leakage-safe outcome and calibration functions.**

Implement:

```python
def evaluate_snapshot(
    snapshot: dict[str, object],
    *,
    bars: pd.DataFrame,
    evaluation_cutoff: date,
    horizons: Sequence[int] = (1, 3, 5),
) -> pd.DataFrame:
    """Evaluate only bars after anchor_date and not after evaluation_cutoff."""


def summarize_rolling_evaluation(detail: pd.DataFrame) -> pd.DataFrame:
    """Return hit rate, return distribution, and sector/state conditional summaries."""
```

For each asset, sort distinct open trading dates strictly after `anchor_date`; the Nth date is the N-trading-day endpoint. Use the snapshot's frozen `anchor_close` and the configured adjusted close source. A horizon is `pending` when fewer than N future sessions are present by `evaluation_cutoff`; do not fill it with the latest available close. Emit `forward_Nd_return`, `forward_Nd_status`, `hit_3pct`, `hit_5pct`, and `hit_7pct` for each horizon, plus `sector_system`, `sector_code`, `sector_gate_status`, `stock_lifecycle`, `market_regime`, and `stock_rank` copied from the snapshot.

Summaries must include up ratio, mean/median return, 25th/75th/90th percentiles, 3/5/7% hit rates, sector hit rate, and conditional rows by market regime, sector recovery state, lifecycle, and rank bucket. Exclude pending rows from completed metrics and include their counts explicitly. Calibration updates may consume only completed snapshot outcomes and must never alter the original snapshot artifacts.

- [ ] **Step 4: Run the outcome tests.**

Run: `rtk pytest tests/test_rolling_oversold_outcomes.py -q`

Expected: `2 passed`.

- [ ] **Step 5: Commit outcome evaluation.**

```bash
rtk git add src/stock_research/rolling_oversold/outcomes.py tests/test_rolling_oversold_outcomes.py
rtk git commit -m "feat: evaluate rolling rebound outcomes"
```

## Task 7: Orchestrate replay/daily runs and expose CLI reports

**Files:**
- Create: `src/stock_research/rolling_oversold/pipeline.py`
- Create: `src/stock_research/rolling_oversold/reporting.py`
- Modify: `src/stock_research/cli.py`
- Create: `tests/test_rolling_oversold_pipeline.py`
- Create: `tests/test_rolling_oversold_cli.py`

- [ ] **Step 1: Write failing pipeline and parser tests.**

```python
from stock_research.cli import build_parser


def test_replay_processes_each_anchor_and_links_previous_snapshot(monkeypatch, tmp_path):
    anchors = [date(2026, 7, 21), date(2026, 7, 22)]
    seen = []

    monkeypatch.setattr(
        "stock_research.rolling_oversold.pipeline.iter_complete_anchor_dates",
        lambda **kwargs: anchors,
    )
    monkeypatch.setattr(
        "stock_research.rolling_oversold.pipeline.run_one_anchor",
        lambda *, anchor_date, previous_snapshot, **kwargs: (
            seen.append((anchor_date, previous_snapshot is not None))
            or make_snapshot(snapshot_id=f"v1|{anchor_date}")
        ),
    )

    result = run_rolling_replay(
        config=RollingOversoldConfig(anchor_start_date=anchors[0], anchor_end_date=anchors[-1]),
        output_dir=tmp_path,
        service="research",
    )

    assert seen == [(anchors[0], False), (anchors[1], True)]
    assert result["anchors_processed"] == 2


def test_cli_accepts_explicit_20260721_anchor_and_daily_trade_date():
    args = build_parser().parse_args(
        [
            "rolling-sector-oversold-replay",
            "--anchor-start-date",
            "2026-07-21",
            "--anchor-end-date",
            "2026-07-31",
            "--output-dir",
            "/tmp/rolling",
        ]
    )

    assert args.command == "rolling-sector-oversold-replay"
    assert args.anchor_start_date == "2026-07-21"
```

- [ ] **Step 2: Run the pipeline and CLI tests to verify they fail.**

Run: `rtk pytest tests/test_rolling_oversold_pipeline.py tests/test_rolling_oversold_cli.py -q`

Expected: FAIL because the parser commands and pipeline functions are not registered.

- [ ] **Step 3: Implement stage-timed orchestration and report rendering.**

Implement these interfaces:

```python
def run_one_anchor(
    *,
    anchor_date: date,
    previous_snapshot: dict[str, object] | None,
    config: RollingOversoldConfig,
    output_dir: str | Path,
    service: str,
) -> dict[str, object]:
    """Run preflight, regime, sector, stock, snapshot, and available evaluation stages."""


def run_rolling_replay(
    *,
    config: RollingOversoldConfig,
    output_dir: str | Path,
    service: str,
) -> dict[str, object]:
    """Process complete anchor sessions in ascending order and link adjacent snapshots."""


def run_rolling_daily(
    *,
    trade_date: date,
    config: RollingOversoldConfig,
    output_dir: str | Path,
    service: str,
) -> dict[str, object]:
    """Run one latest-complete-session snapshot and evaluate all horizons currently available."""
```

`run_one_anchor` must stop before scoring when preflight is blocked, persist the preflight and backfill artifacts, and return a blocked result with no fabricated candidates. It must use `StrategyRuntimeBudget` and record stage durations for load, preflight, regime, sector, stock, snapshot, and evaluation. A daily run selects the latest complete trading date not later than `trade_date`; it never assumes the wall-clock date is complete.

Register these commands in `src/stock_research/cli.py`:

```text
rolling-sector-oversold-replay
  --anchor-start-date YYYY-MM-DD (required)
  --anchor-end-date YYYY-MM-DD (optional; defaults to the latest complete session at or before today)
  --output-dir PATH (required)
  --service NAME (default: configured research service)
  --sector-top-n INTEGER (default: 30)
  --stock-top-n INTEGER (default: 20)
  --score-version TEXT (default: rolling_oversold_v1)
  --adjust-type {qfq,hfq,raw} (default: qfq)

rolling-sector-oversold-daily
  --trade-date YYYY-MM-DD (required)
  --output-dir PATH (required)
  --service NAME (default: configured research service)
  --score-version TEXT (default: rolling_oversold_v1)
  --adjust-type {qfq,hfq,raw} (default: qfq)

rolling-sector-oversold-report
  --snapshot-dir PATH (required)
  --focus-patterns TEXT (comma-separated, optional)
  --output-dir PATH (required)
```

The command handlers must print machine-readable lines for `snapshot_manifest`, `market_regime`, `sector_states`, `stock_candidates`, `evaluation`, `preflight`, `backfill_requests`, `runtime_seconds`, and `blocked`. `reporting.py` must write `rolling_sector_oversold_report.md` with sections for market state, all sector gates, selected stocks, lifecycle revisions, completed/pending 1/3/5-day evaluation, and data gaps. The report must include all sectors with a status, not only the top 30.

- [ ] **Step 4: Run parser, pipeline, and consumer regression tests.**

Run: `rtk pytest tests/test_rolling_oversold_pipeline.py tests/test_rolling_oversold_cli.py tests/test_consumer_oversold_pipeline.py tests/test_consumer_oversold_v2_evaluation.py -q`

Expected: all selected tests pass and the existing consumer artifacts remain unchanged.

- [ ] **Step 5: Commit the runnable commands.**

```bash
rtk git add src/stock_research/rolling_oversold/pipeline.py src/stock_research/rolling_oversold/reporting.py src/stock_research/cli.py tests/test_rolling_oversold_pipeline.py tests/test_rolling_oversold_cli.py
rtk git commit -m "feat: add rolling sector oversold replay commands"
```

## Task 8: Replay the approved window, validate 7/30 technology behavior, and enforce performance

**Files:**
- Modify: `tests/test_rolling_oversold_pipeline.py`
- Create: `tests/test_rolling_oversold_acceptance.py`
- Create: `docs/superpowers/verification/2026-08-01-rolling-sector-oversold-validation.md`

- [ ] **Step 1: Add acceptance tests for PIT, complete sector coverage, and no future leakage.**

```python
def test_acceptance_snapshot_is_reproducible_and_outcomes_are_delayed(tmp_path, db_fixture):
    config = RollingOversoldConfig(
        anchor_start_date=date(2026, 7, 21),
        anchor_end_date=date(2026, 7, 23),
    )

    first = run_rolling_replay(config=config, output_dir=tmp_path / "first", service=db_fixture)
    second = run_rolling_replay(config=config, output_dir=tmp_path / "second", service=db_fixture)

    assert first["snapshot_ids"] == second["snapshot_ids"]
    assert first["future_rows_used_for_scoring"] == 0
    assert first["all_sector_rows_have_status"] is True


def test_acceptance_does_not_report_5d_hit_before_fifth_session(db_fixture, tmp_path):
    result = run_rolling_daily(
        trade_date=date(2026, 7, 23),
        config=RollingOversoldConfig(anchor_start_date=date(2026, 7, 21)),
        output_dir=tmp_path,
        service=db_fixture,
    )

    assert result["evaluation"]["forward_5d_status"].eq("pending").all()
```

- [ ] **Step 2: Run acceptance tests and fix any contract mismatch before live replay.**

Run: `rtk pytest tests/test_rolling_oversold_acceptance.py -q`

Expected: `2 passed`, with the fixture proving that an anchor never reads a bar after its cutoff for feature computation.

- [ ] **Step 3: Run the frozen historical replay from 2026-07-21.**

Run:

```bash
rtk stock-research rolling-sector-oversold-replay \
  --anchor-start-date 2026-07-21 \
  --anchor-end-date 2026-07-31 \
  --output-dir artifacts/rolling_sector_oversold/replay_2026-07-21_2026-07-31 \
  --service research \
  --sector-top-n 30 \
  --stock-top-n 20 \
  --score-version rolling_oversold_v1 \
  --adjust-type qfq
```

Expected: one immutable snapshot directory per complete session; every industry/concept row has `confirmed`, `watch`, `blocked`, or `unknown`; any missing input appears in `backfill_requests.csv`; no network-source log line is emitted; runtime is recorded and remains below 3,600 seconds.

- [ ] **Step 4: Validate the special 2026-07-30 technology case and the consumer comparison.**

Use the generated `sector_states.csv` and `evaluation_1_3_5d.csv` to produce a focused table for sector names matching `芯片`, `半导体`, `CPO`, `算力`, `科技`, and the consumer sectors. The table must show oversold score, repairability, direction, gate, recovery state, candidate count, 1/3/5-day up ratio, and median return. Do not change a rank based on the validation result; only record whether the sector gate and stock lifecycle explained the move.

Run:

```bash
rtk stock-research rolling-sector-oversold-report \
  --snapshot-dir artifacts/rolling_sector_oversold/replay_2026-07-21_2026-07-31/anchor=2026-07-30/version=rolling_oversold_v1 \
  --focus-patterns '芯片,半导体,CPO,算力,科技,消费' \
  --output-dir artifacts/rolling_sector_oversold/validation_2026-07-30
```

Expected: the focused report contains both technology and consumer rows, labels completed versus pending outcomes, and exposes any missing mapping instead of silently omitting a sector.

- [ ] **Step 5: Measure runtime and add the permanent acceptance record.**

Run:

```bash
rtk pytest tests/test_rolling_oversold_acceptance.py tests/test_rolling_oversold_pipeline.py -q
rtk git status --short
```

Record in `docs/superpowers/verification/2026-08-01-rolling-sector-oversold-validation.md` the replay command, database service, anchor count, data cutoff for each anchor, stage timings, sector coverage counts, blocked gaps, completed/pending horizon counts, 7/30 technology focus result, and whether the runtime target was met. The acceptance record must state that normal daily execution reads only database data and creates a separate backfill task when a dependency is missing.

- [ ] **Step 6: Commit the replay validation record.**

```bash
rtk git add tests/test_rolling_oversold_acceptance.py docs/superpowers/verification/2026-08-01-rolling-sector-oversold-validation.md
rtk git commit -m "test: validate rolling sector oversold replay"
```

## Self-review against the approved design

- Market-state classification, all-industry/all-concept scanning, oversold/repairability/direction scores, and hard sector gates are implemented in Tasks 2–3.
- Stock lifecycle states, the 10–20% rebound re-evaluation rule, residual distance to the 1–2-year high, and the balanced 3–5-day objective are implemented in Task 4.
- Point-in-time membership and data cutoffs, no external strategy-time ingestion, and independent backfill requests are implemented in Task 2 and checked again in Task 8.
- Immutable daily snapshots, previous-snapshot links, rank/state deltas, deterministic reruns, and report explainability are implemented in Task 5.
- 1/3/5-trading-day up ratios, return strength, sector/state conditionals, pending windows, and delayed calibration are implemented in Task 6.
- Daily rolling orchestration, first anchor parameterization, replay from 2026-07-21, 2026-07-30 technology validation, and the 60-minute hard runtime budget are implemented in Tasks 7–8.
- Existing consumer V2 behavior is protected by the regression commands in Tasks 4 and 7.

Before handing the plan to an executor, perform a final repository scan for incomplete implementation markers and ambiguous prose; it must return no matches. Also inspect every code block for an incomplete code fragment before execution.
