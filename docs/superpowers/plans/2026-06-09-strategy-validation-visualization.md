# Strategy Validation Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only Strategy Validation workspace that normalizes existing LHB, mid-trend, tech bottleneck, and position-control artifacts into stable dashboard read models and renders the first useful replay/cohort/risk/evidence views.

**Architecture:** Add focused backend DTOs and artifact adapters under `src/stock_research/dashboard/`, expose read-only FastAPI routes under `/api/strategy-validation/*`, then add typed frontend API clients and a Strategy Validation workspace inside the existing Vite dashboard. The first complete view is single-asset replay; cohort, portfolio risk, and evidence receive stable minimal views backed by the same normalized run contract.

**Tech Stack:** Python dataclasses, pandas for fixture/adapters, FastAPI/TestClient, pytest, TypeScript, React, Vite, lightweight-charts, Vitest, Playwright.

---

## File Structure

Backend files:

- Create `src/stock_research/dashboard/strategy_validation.py`
  - Owns DTO dataclasses and small in-memory query helpers for normalized runs.
  - Contains fixture-backed artifact adapter functions used by route tests and early UI wiring.
- Modify `src/stock_research/dashboard/app.py`
  - Adds read-only `/api/strategy-validation/*` routes.
  - Delegates all data loading to `strategy_validation.py`.
- Create `tests/test_dashboard_strategy_validation.py`
  - Covers DTO serialization, fixture adapters, route payloads, empty states, and asset replay shape.

Frontend files:

- Modify `dashboard/src/api/types.ts`
  - Adds TypeScript types matching backend DTO field names.
- Modify `dashboard/src/api/client.ts`
  - Adds `fetchStrategyValidationRuns`, `fetchStrategyValidationReplay`, and related list clients.
- Create `dashboard/src/charts/strategyMarkers.ts`
  - Converts normalized signals/trades into chart marker view models.
- Create `dashboard/src/components/StrategyValidationWorkspace.tsx`
  - Owns strategy/run selection and tab state for Replay, Cohort, Portfolio Risk, and Evidence.
- Create `dashboard/src/components/StrategyReplayPanel.tsx`
  - Renders selected asset replay chart and signal/trade detail.
- Create `dashboard/src/components/StrategyCohortPanel.tsx`
  - Renders minimal grouped metrics table.
- Create `dashboard/src/components/StrategyPortfolioRiskPanel.tsx`
  - Renders minimal position/exposure summary.
- Create `dashboard/src/components/StrategyEvidencePanel.tsx`
  - Renders run config, warnings, and artifact links.
- Modify `dashboard/src/App.tsx`
  - Adds a small mode switch between the existing Research Workbench and Strategy Validation.
- Modify `dashboard/src/charts/AssetChart.tsx`
  - Accepts optional markers without changing current behavior.
- Modify `dashboard/src/styles.css`
  - Adds compact workspace, tab, marker summary, and table styles.
- Create `dashboard/tests/strategyMarkers.test.ts`
  - Covers marker conversion.
- Create `dashboard/tests/strategy-validation-workspace.test.tsx`
  - Covers loading, empty, replay, cohort, risk, and evidence states.
- Modify `dashboard/tests/client.test.ts`
  - Adds strategy validation client URL tests.
- Modify `dashboard/tests/app-smoke.spec.ts`
  - Adds browser smoke for the Strategy Validation mode.

---

### Task 1: Backend Strategy Validation DTOs

**Files:**
- Create: `src/stock_research/dashboard/strategy_validation.py`
- Test: `tests/test_dashboard_strategy_validation.py`

- [ ] **Step 1: Write failing DTO serialization tests**

Add this file:

```python
from stock_research.dashboard.strategy_validation import (
    StrategyEvidenceArtifact,
    StrategyMetricRow,
    StrategyPositionSnapshot,
    StrategySignal,
    StrategyTrade,
    StrategyValidationRun,
)


def test_strategy_validation_run_to_dict_preserves_configs():
    row = StrategyValidationRun(
        run_id="lhb_shortline:2026-06-08:phase16",
        strategy_id="lhb_shortline",
        strategy_name="LHB Shortline",
        strategy_version="phase16",
        run_type="replay",
        start_date="2026-01-01",
        end_date="2026-06-08",
        created_at="2026-06-08T20:30:00+08:00",
        benchmark="000300.SH",
        universe="a_share",
        data_window={"bar": "daily", "minute": "5min"},
        cost_config={"commission": 0.0003},
        slippage_config={"type": "fixed_bps", "bps": 5},
        risk_config={"max_position_weight": 0.2},
        position_config={"initial_cash": 1000000},
        source_artifact_paths=["outputs/research/lhb_phase16/report.md"],
        summary_metrics={"sample_count": 12, "win_rate": 0.58},
        warnings=["partial adapter coverage"],
    )

    payload = row.to_dict()

    assert payload["strategy_id"] == "lhb_shortline"
    assert payload["cost_config"] == {"commission": 0.0003}
    assert payload["summary_metrics"]["win_rate"] == 0.58
    assert payload["warnings"] == ["partial adapter coverage"]


def test_strategy_signal_to_dict_preserves_reason_and_tags():
    row = StrategySignal(
        run_id="mid_trend:2026-06-08:stability",
        strategy_id="mid_trend",
        asset_id="000001.SZ",
        stock_code="000001",
        stock_name="平安银行",
        signal_time="2026-06-08",
        trade_date="2026-06-08",
        signal_type="trend_protection",
        signal_strength=0.82,
        signal_bucket="protection_ok",
        risk_bucket="normal",
        rule_id="mid_trend_trend_protection_v1",
        reason="trend protection holds above stop band",
        tags=["trend", "protection"],
        source_artifact_path="outputs/research/mid_trend/report.md",
    )

    payload = row.to_dict()

    assert payload["signal_type"] == "trend_protection"
    assert payload["reason"] == "trend protection holds above stop band"
    assert payload["tags"] == ["trend", "protection"]


def test_strategy_trade_position_metric_and_artifact_to_dict():
    trade = StrategyTrade(
        run_id="tech_bottleneck:2026-06-08:c2",
        strategy_id="tech_bottleneck",
        asset_id="000002.SZ",
        entry_time="2026-06-03",
        entry_price=10.0,
        entry_reason="bottleneck_rank_top10",
        exit_time="2026-06-08",
        exit_price=11.0,
        exit_reason="rank_decay",
        holding_days=3,
        return_pct=0.1,
        max_high_return_pct=0.16,
        max_drawdown_pct=-0.04,
        outcome_status="complete",
        source_artifact_path="outputs/research/bottleneck/trades.csv",
    )
    position = StrategyPositionSnapshot(
        run_id="position_control:2026-06-08:budget",
        strategy_id="position_control",
        trade_date="2026-06-08",
        asset_id="000002.SZ",
        position_weight=0.08,
        target_weight=0.1,
        cash_weight=0.42,
        exposure=0.58,
        position_cap=0.1,
        risk_budget=0.6,
        suppression_reason="regime_budget",
        source_artifact_path="outputs/research/position/curve.csv",
    )
    metric = StrategyMetricRow(
        run_id="tech_bottleneck:2026-06-08:c2",
        strategy_id="tech_bottleneck",
        metric_level="signal_bucket",
        group_key="bottleneck_rank_top10",
        sample_count=20,
        complete_count=18,
        win_rate=0.55,
        forward_return_mean=0.08,
        forward_return_median=0.05,
        max_high_return_mean=0.14,
        max_drawdown_mean=-0.05,
        max_drawdown_worst=-0.18,
        turnover=0.3,
        exposure_mean=0.45,
        source_artifact_path="outputs/research/bottleneck/metrics.csv",
    )
    artifact = StrategyEvidenceArtifact(
        run_id="tech_bottleneck:2026-06-08:c2",
        artifact_type="csv",
        title="Bottleneck Trades",
        path="outputs/research/bottleneck/trades.csv",
        format="csv",
        trade_date="2026-06-08",
        description="normalized fixture trades",
    )

    assert trade.to_dict()["exit_reason"] == "rank_decay"
    assert position.to_dict()["suppression_reason"] == "regime_budget"
    assert metric.to_dict()["group_key"] == "bottleneck_rank_top10"
    assert artifact.to_dict()["path"].endswith("trades.csv")
```

- [ ] **Step 2: Run the DTO tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_strategy_validation.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stock_research.dashboard.strategy_validation'`.

- [ ] **Step 3: Add DTO implementation**

Create `src/stock_research/dashboard/strategy_validation.py` with:

```python
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StrategyValidationRun:
    run_id: str
    strategy_id: str
    strategy_name: str
    strategy_version: str
    run_type: str
    start_date: str
    end_date: str
    created_at: str
    benchmark: str
    universe: str
    data_window: dict[str, Any]
    cost_config: dict[str, Any]
    slippage_config: dict[str, Any]
    risk_config: dict[str, Any]
    position_config: dict[str, Any]
    source_artifact_paths: list[str]
    summary_metrics: dict[str, Any]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategySignal:
    run_id: str
    strategy_id: str
    asset_id: str
    stock_code: str
    stock_name: str
    signal_time: str
    trade_date: str
    signal_type: str
    signal_strength: float | None
    signal_bucket: str
    risk_bucket: str
    rule_id: str
    reason: str
    tags: list[str]
    source_artifact_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyTrade:
    run_id: str
    strategy_id: str
    asset_id: str
    entry_time: str | None
    entry_price: float | None
    entry_reason: str
    exit_time: str | None
    exit_price: float | None
    exit_reason: str
    holding_days: int | None
    return_pct: float | None
    max_high_return_pct: float | None
    max_drawdown_pct: float | None
    outcome_status: str
    source_artifact_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyPositionSnapshot:
    run_id: str
    strategy_id: str
    trade_date: str
    asset_id: str
    position_weight: float | None
    target_weight: float | None
    cash_weight: float | None
    exposure: float | None
    position_cap: float | None
    risk_budget: float | None
    suppression_reason: str
    source_artifact_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyMetricRow:
    run_id: str
    strategy_id: str
    metric_level: str
    group_key: str
    sample_count: int
    complete_count: int
    win_rate: float | None
    forward_return_mean: float | None
    forward_return_median: float | None
    max_high_return_mean: float | None
    max_drawdown_mean: float | None
    max_drawdown_worst: float | None
    turnover: float | None
    exposure_mean: float | None
    source_artifact_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyEvidenceArtifact:
    run_id: str
    artifact_type: str
    title: str
    path: str
    format: str
    trade_date: str | None
    description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

- [ ] **Step 4: Run the DTO tests and verify they pass**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_strategy_validation.py -q
```

Expected: PASS for 3 tests.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/dashboard/strategy_validation.py tests/test_dashboard_strategy_validation.py
git commit -m "feat: add strategy validation dashboard DTOs"
```

---

### Task 2: Fixture-Backed Artifact Adapter And Query Helpers

**Files:**
- Modify: `src/stock_research/dashboard/strategy_validation.py`
- Modify: `tests/test_dashboard_strategy_validation.py`

- [ ] **Step 1: Add failing tests for fixture-backed run store**

Append these tests to `tests/test_dashboard_strategy_validation.py`:

```python
from stock_research.dashboard.strategy_validation import (
    build_strategy_validation_store_from_frames,
    build_strategy_validation_fixture_store,
    build_strategy_validation_replay,
    list_strategy_validation_artifacts,
    list_strategy_validation_metrics,
    list_strategy_validation_positions,
    list_strategy_validation_runs,
    list_strategy_validation_signals,
    list_strategy_validation_trades,
    load_strategy_validation_run,
)


def test_fixture_store_lists_runs_and_filters_by_strategy():
    store = build_strategy_validation_fixture_store()

    all_runs = list_strategy_validation_runs(store=store)
    lhb_runs = list_strategy_validation_runs(strategy_id="lhb_shortline", store=store)

    assert [row["strategy_id"] for row in all_runs] == [
        "lhb_shortline",
        "mid_trend",
        "tech_bottleneck",
        "position_control",
    ]
    assert len(lhb_runs) == 1
    assert lhb_runs[0]["run_id"] == "lhb_shortline:fixture:phase16"


def test_fixture_store_loads_run_and_related_rows():
    store = build_strategy_validation_fixture_store()
    run_id = "lhb_shortline:fixture:phase16"

    run = load_strategy_validation_run(run_id, store=store)
    signals = list_strategy_validation_signals(run_id, asset_id="000001.SZ", store=store)
    trades = list_strategy_validation_trades(run_id, asset_id="000001.SZ", store=store)
    positions = list_strategy_validation_positions(run_id, asset_id="000001.SZ", store=store)
    metrics = list_strategy_validation_metrics(run_id, metric_level="signal_bucket", store=store)
    artifacts = list_strategy_validation_artifacts(run_id, store=store)

    assert run is not None
    assert run["strategy_name"] == "LHB Shortline"
    assert signals[0]["signal_type"] == "support"
    assert trades[0]["entry_reason"] == "phase16_follow_candidate"
    assert positions[0]["suppression_reason"] == ""
    assert metrics[0]["group_key"] == "support"
    assert artifacts[0]["format"] == "md"


def test_fixture_store_returns_empty_rows_for_missing_run():
    store = build_strategy_validation_fixture_store()

    assert load_strategy_validation_run("missing", store=store) is None
    assert list_strategy_validation_signals("missing", store=store) == []
    assert list_strategy_validation_trades("missing", store=store) == []
    assert list_strategy_validation_positions("missing", store=store) == []
    assert list_strategy_validation_metrics("missing", store=store) == []
    assert list_strategy_validation_artifacts("missing", store=store) == []


def test_strategy_validation_replay_combines_asset_rows():
    store = build_strategy_validation_fixture_store()

    replay = build_strategy_validation_replay(
        run_id="lhb_shortline:fixture:phase16",
        asset_id="000001.SZ",
        bars=[
            {
                "time": "2026-06-03",
                "open": 10.0,
                "high": 10.8,
                "low": 9.8,
                "close": 10.5,
                "volume": 100000.0,
                "amount": 1000000.0,
            }
        ],
        store=store,
    )

    assert replay["run"]["run_id"] == "lhb_shortline:fixture:phase16"
    assert replay["asset_id"] == "000001.SZ"
    assert replay["bars"][0]["time"] == "2026-06-03"
    assert replay["signals"][0]["signal_type"] == "support"
    assert replay["trades"][0]["outcome_status"] == "complete"
    assert replay["artifacts"][0]["title"] == "LHB Fixture Report"


def test_strategy_validation_store_from_frames_maps_representative_artifacts():
    import pandas as pd

    store = build_strategy_validation_store_from_frames(
        run={
            "run_id": "lhb_shortline:artifact:phase16",
            "strategy_id": "lhb_shortline",
            "strategy_name": "LHB Shortline",
            "strategy_version": "phase16",
            "run_type": "replay",
            "start_date": "2026-06-01",
            "end_date": "2026-06-08",
            "created_at": "2026-06-08T20:30:00+08:00",
            "benchmark": "000300.SH",
            "universe": "a_share",
        },
        signals=pd.DataFrame(
            [
                {
                    "asset_id": "000001.SZ",
                    "stock_code": "000001",
                    "stock_name": "平安银行",
                    "signal_time": "2026-06-03",
                    "trade_date": "2026-06-03",
                    "signal_type": "support",
                    "signal_strength": 0.86,
                    "signal_bucket": "support",
                    "risk_bucket": "normal",
                    "rule_id": "lhb_phase16_follow",
                    "reason": "support confirmed",
                    "tags": "lhb,support",
                    "source_artifact_path": "outputs/research/lhb_signal.csv",
                }
            ]
        ),
        trades=pd.DataFrame(
            [
                {
                    "asset_id": "000001.SZ",
                    "entry_time": "2026-06-04",
                    "entry_price": 10.5,
                    "entry_reason": "phase16_follow_candidate",
                    "exit_time": "2026-06-06",
                    "exit_price": 11.0,
                    "exit_reason": "phase16_exit_confirmed",
                    "holding_days": 2,
                    "return_pct": 0.0476,
                    "max_high_return_pct": 0.08,
                    "max_drawdown_pct": -0.02,
                    "outcome_status": "complete",
                    "source_artifact_path": "outputs/research/lhb_trades.csv",
                }
            ]
        ),
        metrics=pd.DataFrame(
            [
                {
                    "metric_level": "signal_bucket",
                    "group_key": "support",
                    "sample_count": 1,
                    "complete_count": 1,
                    "win_rate": 1.0,
                    "forward_return_mean": 0.0476,
                    "forward_return_median": 0.0476,
                    "max_high_return_mean": 0.08,
                    "max_drawdown_mean": -0.02,
                    "max_drawdown_worst": -0.02,
                    "turnover": 0.1,
                    "exposure_mean": 0.08,
                    "source_artifact_path": "outputs/research/lhb_metrics.csv",
                }
            ]
        ),
        artifacts=[
            {
                "artifact_type": "markdown",
                "title": "LHB Artifact Report",
                "path": "outputs/research/lhb_report.md",
                "format": "md",
                "trade_date": "2026-06-08",
                "description": "representative artifact report",
            }
        ],
    )

    assert store["runs"][0]["run_id"] == "lhb_shortline:artifact:phase16"
    assert store["signals"][0]["tags"] == ["lhb", "support"]
    assert store["trades"][0]["entry_reason"] == "phase16_follow_candidate"
    assert store["metrics"][0]["group_key"] == "support"
    assert store["artifacts"][0]["title"] == "LHB Artifact Report"
```

- [ ] **Step 2: Run adapter tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_strategy_validation.py -q
```

Expected: FAIL with import errors for `build_strategy_validation_fixture_store` and `build_strategy_validation_store_from_frames`.

- [ ] **Step 3: Add fixture store and query helpers**

Append this implementation to `src/stock_research/dashboard/strategy_validation.py`:

```python
StrategyValidationStore = dict[str, list[dict[str, Any]]]


def build_strategy_validation_fixture_store() -> StrategyValidationStore:
    runs = [
        StrategyValidationRun(
            run_id="lhb_shortline:fixture:phase16",
            strategy_id="lhb_shortline",
            strategy_name="LHB Shortline",
            strategy_version="phase16",
            run_type="replay",
            start_date="2026-06-01",
            end_date="2026-06-08",
            created_at="2026-06-08T20:30:00+08:00",
            benchmark="000300.SH",
            universe="a_share",
            data_window={"bar": "daily", "minute": "5min"},
            cost_config={"commission": 0.0003},
            slippage_config={"type": "fixed_bps", "bps": 5},
            risk_config={"max_position_weight": 0.2},
            position_config={"initial_cash": 1000000},
            source_artifact_paths=["outputs/research/lhb_fixture/lhb_phase16_report.md"],
            summary_metrics={"sample_count": 1, "win_rate": 1.0},
            warnings=["fixture-backed run"],
        ),
        StrategyValidationRun(
            run_id="mid_trend:fixture:stability",
            strategy_id="mid_trend",
            strategy_name="Mid Trend",
            strategy_version="stability_v1",
            run_type="review",
            start_date="2026-06-01",
            end_date="2026-06-08",
            created_at="2026-06-08T20:40:00+08:00",
            benchmark="000905.SH",
            universe="a_share",
            data_window={"bar": "daily"},
            cost_config={"commission": 0.0003},
            slippage_config={"type": "fixed_bps", "bps": 5},
            risk_config={"max_position_weight": 0.1},
            position_config={"rebalance": "weekly"},
            source_artifact_paths=["outputs/research/mid_trend_fixture/report.md"],
            summary_metrics={"sample_count": 1, "win_rate": 1.0},
            warnings=["fixture-backed run"],
        ),
        StrategyValidationRun(
            run_id="tech_bottleneck:fixture:c2",
            strategy_id="tech_bottleneck",
            strategy_name="Tech Bottleneck",
            strategy_version="c2",
            run_type="cohort",
            start_date="2026-06-01",
            end_date="2026-06-08",
            created_at="2026-06-08T20:50:00+08:00",
            benchmark="000905.SH",
            universe="a_share",
            data_window={"bar": "daily"},
            cost_config={"commission": 0.0003},
            slippage_config={"type": "fixed_bps", "bps": 5},
            risk_config={"max_position_weight": 0.08},
            position_config={"top_n": 10},
            source_artifact_paths=["outputs/research/bottleneck_fixture/report.md"],
            summary_metrics={"sample_count": 1, "win_rate": 1.0},
            warnings=["fixture-backed run"],
        ),
        StrategyValidationRun(
            run_id="position_control:fixture:budget",
            strategy_id="position_control",
            strategy_name="Position Control",
            strategy_version="budget_v1",
            run_type="portfolio",
            start_date="2026-06-01",
            end_date="2026-06-08",
            created_at="2026-06-08T21:00:00+08:00",
            benchmark="000300.SH",
            universe="a_share",
            data_window={"bar": "daily"},
            cost_config={"commission": 0.0003},
            slippage_config={"type": "fixed_bps", "bps": 5},
            risk_config={"max_exposure": 0.6},
            position_config={"cash_buffer": 0.4},
            source_artifact_paths=["outputs/research/position_fixture/report.md"],
            summary_metrics={"exposure_mean": 0.45, "max_drawdown": -0.03},
            warnings=["fixture-backed run"],
        ),
    ]
    signals = [
        StrategySignal(
            run_id="lhb_shortline:fixture:phase16",
            strategy_id="lhb_shortline",
            asset_id="000001.SZ",
            stock_code="000001",
            stock_name="平安银行",
            signal_time="2026-06-03",
            trade_date="2026-06-03",
            signal_type="support",
            signal_strength=0.86,
            signal_bucket="support",
            risk_bucket="normal",
            rule_id="lhb_phase16_follow",
            reason="LHB support behavior with next-day confirmation",
            tags=["lhb", "support"],
            source_artifact_path="outputs/research/lhb_fixture/lhb_phase16_detail.csv",
        ),
        StrategySignal(
            run_id="mid_trend:fixture:stability",
            strategy_id="mid_trend",
            asset_id="000002.SZ",
            stock_code="000002",
            stock_name="万科A",
            signal_time="2026-06-04",
            trade_date="2026-06-04",
            signal_type="trend_protection",
            signal_strength=0.72,
            signal_bucket="protection_ok",
            risk_bucket="normal",
            rule_id="mid_trend_protection_v1",
            reason="trend protection remains valid",
            tags=["mid_trend", "protection"],
            source_artifact_path="outputs/research/mid_trend_fixture/detail.csv",
        ),
        StrategySignal(
            run_id="tech_bottleneck:fixture:c2",
            strategy_id="tech_bottleneck",
            asset_id="000003.SZ",
            stock_code="000003",
            stock_name="Fixture Tech",
            signal_time="2026-06-05",
            trade_date="2026-06-05",
            signal_type="bottleneck_hit",
            signal_strength=0.91,
            signal_bucket="bottleneck_rank_top10",
            risk_bucket="normal",
            rule_id="bottleneck_c2_rank",
            reason="ranked in top 10 bottleneck discoveries",
            tags=["bottleneck", "rank"],
            source_artifact_path="outputs/research/bottleneck_fixture/detail.csv",
        ),
    ]
    trades = [
        StrategyTrade(
            run_id="lhb_shortline:fixture:phase16",
            strategy_id="lhb_shortline",
            asset_id="000001.SZ",
            entry_time="2026-06-04",
            entry_price=10.5,
            entry_reason="phase16_follow_candidate",
            exit_time="2026-06-06",
            exit_price=11.0,
            exit_reason="phase16_exit_confirmed",
            holding_days=2,
            return_pct=0.0476,
            max_high_return_pct=0.08,
            max_drawdown_pct=-0.02,
            outcome_status="complete",
            source_artifact_path="outputs/research/lhb_fixture/lhb_phase16_trades.csv",
        ),
    ]
    positions = [
        StrategyPositionSnapshot(
            run_id="lhb_shortline:fixture:phase16",
            strategy_id="lhb_shortline",
            trade_date="2026-06-04",
            asset_id="000001.SZ",
            position_weight=0.08,
            target_weight=0.08,
            cash_weight=0.92,
            exposure=0.08,
            position_cap=0.1,
            risk_budget=0.2,
            suppression_reason="",
            source_artifact_path="outputs/research/lhb_fixture/lhb_phase16_positions.csv",
        ),
        StrategyPositionSnapshot(
            run_id="position_control:fixture:budget",
            strategy_id="position_control",
            trade_date="2026-06-04",
            asset_id="000001.SZ",
            position_weight=0.05,
            target_weight=0.08,
            cash_weight=0.45,
            exposure=0.55,
            position_cap=0.08,
            risk_budget=0.6,
            suppression_reason="regime_budget",
            source_artifact_path="outputs/research/position_fixture/positions.csv",
        ),
    ]
    metrics = [
        StrategyMetricRow(
            run_id="lhb_shortline:fixture:phase16",
            strategy_id="lhb_shortline",
            metric_level="signal_bucket",
            group_key="support",
            sample_count=1,
            complete_count=1,
            win_rate=1.0,
            forward_return_mean=0.0476,
            forward_return_median=0.0476,
            max_high_return_mean=0.08,
            max_drawdown_mean=-0.02,
            max_drawdown_worst=-0.02,
            turnover=0.1,
            exposure_mean=0.08,
            source_artifact_path="outputs/research/lhb_fixture/lhb_phase16_metrics.csv",
        ),
        StrategyMetricRow(
            run_id="tech_bottleneck:fixture:c2",
            strategy_id="tech_bottleneck",
            metric_level="signal_bucket",
            group_key="bottleneck_rank_top10",
            sample_count=1,
            complete_count=1,
            win_rate=1.0,
            forward_return_mean=0.05,
            forward_return_median=0.05,
            max_high_return_mean=0.07,
            max_drawdown_mean=-0.015,
            max_drawdown_worst=-0.015,
            turnover=0.2,
            exposure_mean=0.12,
            source_artifact_path="outputs/research/bottleneck_fixture/metrics.csv",
        ),
    ]
    artifacts = [
        StrategyEvidenceArtifact(
            run_id="lhb_shortline:fixture:phase16",
            artifact_type="markdown",
            title="LHB Fixture Report",
            path="outputs/research/lhb_fixture/lhb_phase16_report.md",
            format="md",
            trade_date="2026-06-08",
            description="Fixture LHB phase16 report",
        ),
        StrategyEvidenceArtifact(
            run_id="tech_bottleneck:fixture:c2",
            artifact_type="csv",
            title="Bottleneck Fixture Metrics",
            path="outputs/research/bottleneck_fixture/metrics.csv",
            format="csv",
            trade_date="2026-06-08",
            description="Fixture bottleneck cohort metrics",
        ),
    ]
    return {
        "runs": [row.to_dict() for row in runs],
        "signals": [row.to_dict() for row in signals],
        "trades": [row.to_dict() for row in trades],
        "positions": [row.to_dict() for row in positions],
        "metrics": [row.to_dict() for row in metrics],
        "artifacts": [row.to_dict() for row in artifacts],
    }


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def build_strategy_validation_store_from_frames(
    run: dict[str, Any],
    signals: Any,
    trades: Any,
    metrics: Any,
    artifacts: list[dict[str, Any]],
    positions: Any | None = None,
) -> StrategyValidationStore:
    run_id = str(run["run_id"])
    strategy_id = str(run["strategy_id"])
    run_row = StrategyValidationRun(
        run_id=run_id,
        strategy_id=strategy_id,
        strategy_name=str(run["strategy_name"]),
        strategy_version=str(run["strategy_version"]),
        run_type=str(run["run_type"]),
        start_date=str(run["start_date"]),
        end_date=str(run["end_date"]),
        created_at=str(run["created_at"]),
        benchmark=str(run["benchmark"]),
        universe=str(run["universe"]),
        data_window=dict(run.get("data_window", {})),
        cost_config=dict(run.get("cost_config", {})),
        slippage_config=dict(run.get("slippage_config", {})),
        risk_config=dict(run.get("risk_config", {})),
        position_config=dict(run.get("position_config", {})),
        source_artifact_paths=[str(item) for item in run.get("source_artifact_paths", [])],
        summary_metrics=dict(run.get("summary_metrics", {})),
        warnings=[str(item) for item in run.get("warnings", [])],
    )
    signal_rows = [
        StrategySignal(
            run_id=run_id,
            strategy_id=strategy_id,
            asset_id=str(row.get("asset_id", "")),
            stock_code=str(row.get("stock_code", "")),
            stock_name=str(row.get("stock_name", "")),
            signal_time=str(row.get("signal_time", "")),
            trade_date=str(row.get("trade_date", "")),
            signal_type=str(row.get("signal_type", "")),
            signal_strength=_optional_float(row.get("signal_strength")),
            signal_bucket=str(row.get("signal_bucket", "")),
            risk_bucket=str(row.get("risk_bucket", "")),
            rule_id=str(row.get("rule_id", "")),
            reason=str(row.get("reason", "")),
            tags=_string_list(row.get("tags")),
            source_artifact_path=str(row.get("source_artifact_path", "")),
        ).to_dict()
        for row in signals.to_dict("records")
    ]
    trade_rows = [
        StrategyTrade(
            run_id=run_id,
            strategy_id=strategy_id,
            asset_id=str(row.get("asset_id", "")),
            entry_time=str(row.get("entry_time")) if row.get("entry_time") is not None else None,
            entry_price=_optional_float(row.get("entry_price")),
            entry_reason=str(row.get("entry_reason", "")),
            exit_time=str(row.get("exit_time")) if row.get("exit_time") is not None else None,
            exit_price=_optional_float(row.get("exit_price")),
            exit_reason=str(row.get("exit_reason", "")),
            holding_days=_optional_int(row.get("holding_days")),
            return_pct=_optional_float(row.get("return_pct")),
            max_high_return_pct=_optional_float(row.get("max_high_return_pct")),
            max_drawdown_pct=_optional_float(row.get("max_drawdown_pct")),
            outcome_status=str(row.get("outcome_status", "")),
            source_artifact_path=str(row.get("source_artifact_path", "")),
        ).to_dict()
        for row in trades.to_dict("records")
    ]
    position_records = [] if positions is None else positions.to_dict("records")
    position_rows = [
        StrategyPositionSnapshot(
            run_id=run_id,
            strategy_id=strategy_id,
            trade_date=str(row.get("trade_date", "")),
            asset_id=str(row.get("asset_id", "")),
            position_weight=_optional_float(row.get("position_weight")),
            target_weight=_optional_float(row.get("target_weight")),
            cash_weight=_optional_float(row.get("cash_weight")),
            exposure=_optional_float(row.get("exposure")),
            position_cap=_optional_float(row.get("position_cap")),
            risk_budget=_optional_float(row.get("risk_budget")),
            suppression_reason=str(row.get("suppression_reason", "")),
            source_artifact_path=str(row.get("source_artifact_path", "")),
        ).to_dict()
        for row in position_records
    ]
    metric_rows = [
        StrategyMetricRow(
            run_id=run_id,
            strategy_id=strategy_id,
            metric_level=str(row.get("metric_level", "")),
            group_key=str(row.get("group_key", "")),
            sample_count=int(row.get("sample_count", 0)),
            complete_count=int(row.get("complete_count", 0)),
            win_rate=_optional_float(row.get("win_rate")),
            forward_return_mean=_optional_float(row.get("forward_return_mean")),
            forward_return_median=_optional_float(row.get("forward_return_median")),
            max_high_return_mean=_optional_float(row.get("max_high_return_mean")),
            max_drawdown_mean=_optional_float(row.get("max_drawdown_mean")),
            max_drawdown_worst=_optional_float(row.get("max_drawdown_worst")),
            turnover=_optional_float(row.get("turnover")),
            exposure_mean=_optional_float(row.get("exposure_mean")),
            source_artifact_path=str(row.get("source_artifact_path", "")),
        ).to_dict()
        for row in metrics.to_dict("records")
    ]
    artifact_rows = [
        StrategyEvidenceArtifact(
            run_id=run_id,
            artifact_type=str(row.get("artifact_type", "")),
            title=str(row.get("title", "")),
            path=str(row.get("path", "")),
            format=str(row.get("format", "")),
            trade_date=str(row.get("trade_date")) if row.get("trade_date") is not None else None,
            description=str(row.get("description", "")),
        ).to_dict()
        for row in artifacts
    ]
    return {
        "runs": [run_row.to_dict()],
        "signals": signal_rows,
        "trades": trade_rows,
        "positions": position_rows,
        "metrics": metric_rows,
        "artifacts": artifact_rows,
    }


def _default_store(store: StrategyValidationStore | None) -> StrategyValidationStore:
    return store if store is not None else build_strategy_validation_fixture_store()


def _filter_rows(rows: list[dict[str, Any]], **filters: object) -> list[dict[str, Any]]:
    result = rows
    for key, value in filters.items():
        if value is not None:
            result = [row for row in result if row.get(key) == value]
    return result


def list_strategy_validation_runs(
    strategy_id: str | None = None,
    store: StrategyValidationStore | None = None,
) -> list[dict[str, Any]]:
    data = _default_store(store)
    return _filter_rows(data["runs"], strategy_id=strategy_id)


def load_strategy_validation_run(
    run_id: str,
    store: StrategyValidationStore | None = None,
) -> dict[str, Any] | None:
    data = _default_store(store)
    rows = _filter_rows(data["runs"], run_id=run_id)
    return rows[0] if rows else None


def list_strategy_validation_signals(
    run_id: str,
    asset_id: str | None = None,
    signal_bucket: str | None = None,
    risk_bucket: str | None = None,
    store: StrategyValidationStore | None = None,
) -> list[dict[str, Any]]:
    data = _default_store(store)
    return _filter_rows(
        data["signals"],
        run_id=run_id,
        asset_id=asset_id,
        signal_bucket=signal_bucket,
        risk_bucket=risk_bucket,
    )


def list_strategy_validation_trades(
    run_id: str,
    asset_id: str | None = None,
    store: StrategyValidationStore | None = None,
) -> list[dict[str, Any]]:
    data = _default_store(store)
    return _filter_rows(data["trades"], run_id=run_id, asset_id=asset_id)


def list_strategy_validation_positions(
    run_id: str,
    asset_id: str | None = None,
    store: StrategyValidationStore | None = None,
) -> list[dict[str, Any]]:
    data = _default_store(store)
    return _filter_rows(data["positions"], run_id=run_id, asset_id=asset_id)


def list_strategy_validation_metrics(
    run_id: str,
    metric_level: str | None = None,
    store: StrategyValidationStore | None = None,
) -> list[dict[str, Any]]:
    data = _default_store(store)
    return _filter_rows(data["metrics"], run_id=run_id, metric_level=metric_level)


def list_strategy_validation_artifacts(
    run_id: str,
    store: StrategyValidationStore | None = None,
) -> list[dict[str, Any]]:
    data = _default_store(store)
    return _filter_rows(data["artifacts"], run_id=run_id)


def build_strategy_validation_replay(
    run_id: str,
    asset_id: str,
    bars: list[dict[str, Any]],
    store: StrategyValidationStore | None = None,
) -> dict[str, Any]:
    run = load_strategy_validation_run(run_id, store=store)
    return {
        "run": run,
        "asset_id": asset_id,
        "bars": bars,
        "signals": list_strategy_validation_signals(run_id, asset_id=asset_id, store=store),
        "trades": list_strategy_validation_trades(run_id, asset_id=asset_id, store=store),
        "positions": list_strategy_validation_positions(run_id, asset_id=asset_id, store=store),
        "metrics": list_strategy_validation_metrics(run_id, store=store),
        "artifacts": list_strategy_validation_artifacts(run_id, store=store),
    }
```

- [ ] **Step 4: Run adapter tests and verify they pass**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_strategy_validation.py -q
```

Expected: PASS for 8 tests.

- [ ] **Step 5: Commit**

Run:

```bash
git add src/stock_research/dashboard/strategy_validation.py tests/test_dashboard_strategy_validation.py
git commit -m "feat: add strategy validation fixture read model"
```

---

### Task 3: Read-Only Strategy Validation API Routes

**Files:**
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_strategy_validation.py`

- [ ] **Step 1: Add failing FastAPI route tests**

Append these tests to `tests/test_dashboard_strategy_validation.py`:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


def test_strategy_validation_runs_route(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "list_strategy_validation_runs",
        lambda strategy_id=None: [
            {
                "run_id": "lhb_shortline:fixture:phase16",
                "strategy_id": strategy_id or "lhb_shortline",
                "strategy_name": "LHB Shortline",
            }
        ],
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/strategy-validation/runs?strategy_id=lhb_shortline")

    assert response.status_code == 200
    assert response.json()["items"][0]["run_id"] == "lhb_shortline:fixture:phase16"
    assert response.json()["items"][0]["strategy_id"] == "lhb_shortline"


def test_strategy_validation_run_route_returns_404(monkeypatch):
    monkeypatch.setattr(dashboard_app, "load_strategy_validation_run", lambda run_id: None)
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/strategy-validation/runs/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "strategy validation run not found"


def test_strategy_validation_run_child_routes(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "list_strategy_validation_signals",
        lambda run_id, asset_id=None, signal_bucket=None, risk_bucket=None: [
            {"run_id": run_id, "asset_id": asset_id, "signal_bucket": signal_bucket, "risk_bucket": risk_bucket}
        ],
    )
    monkeypatch.setattr(
        dashboard_app,
        "list_strategy_validation_trades",
        lambda run_id, asset_id=None: [{"run_id": run_id, "asset_id": asset_id}],
    )
    monkeypatch.setattr(
        dashboard_app,
        "list_strategy_validation_positions",
        lambda run_id, asset_id=None: [{"run_id": run_id, "asset_id": asset_id}],
    )
    monkeypatch.setattr(
        dashboard_app,
        "list_strategy_validation_metrics",
        lambda run_id, metric_level=None: [{"run_id": run_id, "metric_level": metric_level}],
    )
    monkeypatch.setattr(
        dashboard_app,
        "list_strategy_validation_artifacts",
        lambda run_id: [{"run_id": run_id, "title": "Artifact"}],
    )
    client = TestClient(dashboard_app.create_app())

    signals = client.get(
        "/api/strategy-validation/runs/run-1/signals"
        "?asset_id=000001.SZ&signal_bucket=support&risk_bucket=normal"
    )
    trades = client.get("/api/strategy-validation/runs/run-1/trades?asset_id=000001.SZ")
    positions = client.get("/api/strategy-validation/runs/run-1/positions?asset_id=000001.SZ")
    metrics = client.get("/api/strategy-validation/runs/run-1/metrics?metric_level=signal_bucket")
    artifacts = client.get("/api/strategy-validation/runs/run-1/artifacts")

    assert signals.json()["items"][0] == {
        "run_id": "run-1",
        "asset_id": "000001.SZ",
        "signal_bucket": "support",
        "risk_bucket": "normal",
    }
    assert trades.json()["items"][0]["asset_id"] == "000001.SZ"
    assert positions.json()["items"][0]["asset_id"] == "000001.SZ"
    assert metrics.json()["items"][0]["metric_level"] == "signal_bucket"
    assert artifacts.json()["items"][0]["title"] == "Artifact"


def test_strategy_validation_replay_route_combines_bars(monkeypatch):
    captured = {}

    def fake_load_daily_bars(asset_id, start_date, end_date, adjust_type):
        captured["bars_args"] = [asset_id, start_date, end_date, adjust_type]
        return [{"time": "2026-06-03", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100, "amount": 1000}]

    def fake_replay(run_id, asset_id, bars):
        captured["replay_args"] = [run_id, asset_id, bars]
        return {"run": {"run_id": run_id}, "asset_id": asset_id, "bars": bars, "signals": [], "trades": []}

    monkeypatch.setattr(dashboard_app, "load_daily_bars", fake_load_daily_bars)
    monkeypatch.setattr(dashboard_app, "build_strategy_validation_replay", fake_replay)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/strategy-validation/runs/run-1/assets/000001.SZ/replay"
        "?start_date=2026-06-01&end_date=2026-06-08&adjust_type=hfq"
    )

    assert response.status_code == 200
    assert captured["bars_args"] == ["000001.SZ", "2026-06-01", "2026-06-08", "hfq"]
    assert captured["replay_args"][0:2] == ["run-1", "000001.SZ"]
    assert response.json()["bars"][0]["time"] == "2026-06-03"
```

- [ ] **Step 2: Run route tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_strategy_validation.py -q -k "route"
```

Expected: FAIL because `/api/strategy-validation/*` routes do not exist or dashboard app does not import the helpers.

- [ ] **Step 3: Import strategy validation helpers in `app.py`**

Add these imports near the other dashboard imports in `src/stock_research/dashboard/app.py`:

```python
from stock_research.dashboard.strategy_validation import (
    build_strategy_validation_replay,
    list_strategy_validation_artifacts,
    list_strategy_validation_metrics,
    list_strategy_validation_positions,
    list_strategy_validation_runs,
    list_strategy_validation_signals,
    list_strategy_validation_trades,
    load_strategy_validation_run,
)
```

- [ ] **Step 4: Add read-only API routes in `create_app()`**

Add these routes before `return app` in `src/stock_research/dashboard/app.py`:

```python
    @app.get("/api/strategy-validation/runs")
    def strategy_validation_runs(strategy_id: str | None = None):
        return {"items": list_strategy_validation_runs(strategy_id)}

    @app.get("/api/strategy-validation/runs/{run_id}")
    def strategy_validation_run(run_id: str):
        run = load_strategy_validation_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="strategy validation run not found")
        return {"item": run}

    @app.get("/api/strategy-validation/runs/{run_id}/signals")
    def strategy_validation_signals(
        run_id: str,
        asset_id: str | None = None,
        signal_bucket: str | None = None,
        risk_bucket: str | None = None,
    ):
        return {
            "run_id": run_id,
            "items": list_strategy_validation_signals(
                run_id,
                asset_id=asset_id,
                signal_bucket=signal_bucket,
                risk_bucket=risk_bucket,
            ),
        }

    @app.get("/api/strategy-validation/runs/{run_id}/trades")
    def strategy_validation_trades(run_id: str, asset_id: str | None = None):
        return {"run_id": run_id, "items": list_strategy_validation_trades(run_id, asset_id=asset_id)}

    @app.get("/api/strategy-validation/runs/{run_id}/positions")
    def strategy_validation_positions(run_id: str, asset_id: str | None = None):
        return {"run_id": run_id, "items": list_strategy_validation_positions(run_id, asset_id=asset_id)}

    @app.get("/api/strategy-validation/runs/{run_id}/metrics")
    def strategy_validation_metrics(run_id: str, metric_level: str | None = None):
        return {"run_id": run_id, "items": list_strategy_validation_metrics(run_id, metric_level=metric_level)}

    @app.get("/api/strategy-validation/runs/{run_id}/artifacts")
    def strategy_validation_artifacts(run_id: str):
        return {"run_id": run_id, "items": list_strategy_validation_artifacts(run_id)}

    @app.get("/api/strategy-validation/runs/{run_id}/assets/{asset_id}/replay")
    def strategy_validation_asset_replay(
        run_id: str,
        asset_id: str,
        start_date: str,
        end_date: str,
        adjust_type: str = "qfq",
    ):
        bars = load_daily_bars(asset_id, start_date, end_date, adjust_type)
        return build_strategy_validation_replay(run_id, asset_id, bars)
```

- [ ] **Step 5: Run strategy validation backend tests**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_strategy_validation.py -q
```

Expected: PASS.

- [ ] **Step 6: Run dashboard app regression tests**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_app.py tests/test_dashboard_schemas.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add src/stock_research/dashboard/app.py tests/test_dashboard_strategy_validation.py
git commit -m "feat: expose strategy validation dashboard API"
```

---

### Task 4: Frontend Types And API Client

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Add failing client tests**

Append these tests before the final closing `});` of the existing `describe('dashboard API client', () => {` block in `dashboard/tests/client.test.ts`:

```typescript
  it('fetches strategy validation runs with optional strategy filter', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ run_id: 'lhb_shortline:fixture:phase16', strategy_id: 'lhb_shortline' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const { fetchStrategyValidationRuns } = await import('../src/api/client');
    const result = await fetchStrategyValidationRuns({ strategyId: 'lhb_shortline' });

    expect(fetchMock).toHaveBeenCalledWith('/api/strategy-validation/runs?strategy_id=lhb_shortline');
    expect(result[0].run_id).toBe('lhb_shortline:fixture:phase16');
  });

  it('fetches strategy validation replay with date range', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        run: { run_id: 'run-1', strategy_id: 'lhb_shortline' },
        asset_id: '000001.SZ',
        bars: [],
        signals: [],
        trades: [],
        positions: [],
        metrics: [],
        artifacts: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const { fetchStrategyValidationReplay } = await import('../src/api/client');
    const result = await fetchStrategyValidationReplay('run-1', '000001.SZ', '2026-06-01', '2026-06-08');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/strategy-validation/runs/run-1/assets/000001.SZ/replay?start_date=2026-06-01&end_date=2026-06-08&adjust_type=qfq'
    );
    expect(result.asset_id).toBe('000001.SZ');
  });
```

- [ ] **Step 2: Run client tests and verify they fail**

Run:

```bash
cd dashboard && pnpm test tests/client.test.ts
```

Expected: FAIL because the client functions do not exist.

- [ ] **Step 3: Add strategy validation types**

Append these exports to `dashboard/src/api/types.ts`:

```typescript
export type StrategyValidationRun = {
  run_id: string;
  strategy_id: string;
  strategy_name: string;
  strategy_version: string;
  run_type: string;
  start_date: string;
  end_date: string;
  created_at: string;
  benchmark: string;
  universe: string;
  data_window: Record<string, unknown>;
  cost_config: Record<string, unknown>;
  slippage_config: Record<string, unknown>;
  risk_config: Record<string, unknown>;
  position_config: Record<string, unknown>;
  source_artifact_paths: string[];
  summary_metrics: Record<string, unknown>;
  warnings: string[];
};

export type StrategySignal = {
  run_id: string;
  strategy_id: string;
  asset_id: string;
  stock_code: string;
  stock_name: string;
  signal_time: string;
  trade_date: string;
  signal_type: string;
  signal_strength: number | null;
  signal_bucket: string;
  risk_bucket: string;
  rule_id: string;
  reason: string;
  tags: string[];
  source_artifact_path: string;
};

export type StrategyTrade = {
  run_id: string;
  strategy_id: string;
  asset_id: string;
  entry_time: string | null;
  entry_price: number | null;
  entry_reason: string;
  exit_time: string | null;
  exit_price: number | null;
  exit_reason: string;
  holding_days: number | null;
  return_pct: number | null;
  max_high_return_pct: number | null;
  max_drawdown_pct: number | null;
  outcome_status: string;
  source_artifact_path: string;
};

export type StrategyPositionSnapshot = {
  run_id: string;
  strategy_id: string;
  trade_date: string;
  asset_id: string;
  position_weight: number | null;
  target_weight: number | null;
  cash_weight: number | null;
  exposure: number | null;
  position_cap: number | null;
  risk_budget: number | null;
  suppression_reason: string;
  source_artifact_path: string;
};

export type StrategyMetricRow = {
  run_id: string;
  strategy_id: string;
  metric_level: string;
  group_key: string;
  sample_count: number;
  complete_count: number;
  win_rate: number | null;
  forward_return_mean: number | null;
  forward_return_median: number | null;
  max_high_return_mean: number | null;
  max_drawdown_mean: number | null;
  max_drawdown_worst: number | null;
  turnover: number | null;
  exposure_mean: number | null;
  source_artifact_path: string;
};

export type StrategyEvidenceArtifact = {
  run_id: string;
  artifact_type: string;
  title: string;
  path: string;
  format: string;
  trade_date: string | null;
  description: string;
};

export type StrategyReplayPayload = {
  run: StrategyValidationRun | null;
  asset_id: string;
  bars: BarPoint[];
  signals: StrategySignal[];
  trades: StrategyTrade[];
  positions: StrategyPositionSnapshot[];
  metrics: StrategyMetricRow[];
  artifacts: StrategyEvidenceArtifact[];
};
```

- [ ] **Step 4: Import types and add client functions**

Add these names to the type import in `dashboard/src/api/client.ts`:

```typescript
  StrategyEvidenceArtifact,
  StrategyMetricRow,
  StrategyPositionSnapshot,
  StrategyReplayPayload,
  StrategySignal,
  StrategyTrade,
  StrategyValidationRun,
```

Then add these functions before `getJson`:

```typescript
export async function fetchStrategyValidationRuns(
  options: { strategyId?: string } = {}
): Promise<StrategyValidationRun[]> {
  const strategy = options.strategyId ? `?strategy_id=${encodeURIComponent(options.strategyId)}` : '';
  const payload = await getJson<{ items: StrategyValidationRun[] }>(`/api/strategy-validation/runs${strategy}`);
  return payload.items;
}

export async function fetchStrategyValidationSignals(
  runId: string,
  options: { assetId?: string; signalBucket?: string; riskBucket?: string } = {}
): Promise<StrategySignal[]> {
  const params = new URLSearchParams();
  if (options.assetId) params.set('asset_id', options.assetId);
  if (options.signalBucket) params.set('signal_bucket', options.signalBucket);
  if (options.riskBucket) params.set('risk_bucket', options.riskBucket);
  const suffix = params.toString() ? `?${params.toString()}` : '';
  const payload = await getJson<{ items: StrategySignal[] }>(
    `/api/strategy-validation/runs/${encodeURIComponent(runId)}/signals${suffix}`
  );
  return payload.items;
}

export async function fetchStrategyValidationTrades(
  runId: string,
  options: { assetId?: string } = {}
): Promise<StrategyTrade[]> {
  const suffix = options.assetId ? `?asset_id=${encodeURIComponent(options.assetId)}` : '';
  const payload = await getJson<{ items: StrategyTrade[] }>(
    `/api/strategy-validation/runs/${encodeURIComponent(runId)}/trades${suffix}`
  );
  return payload.items;
}

export async function fetchStrategyValidationPositions(
  runId: string,
  options: { assetId?: string } = {}
): Promise<StrategyPositionSnapshot[]> {
  const suffix = options.assetId ? `?asset_id=${encodeURIComponent(options.assetId)}` : '';
  const payload = await getJson<{ items: StrategyPositionSnapshot[] }>(
    `/api/strategy-validation/runs/${encodeURIComponent(runId)}/positions${suffix}`
  );
  return payload.items;
}

export async function fetchStrategyValidationMetrics(
  runId: string,
  options: { metricLevel?: string } = {}
): Promise<StrategyMetricRow[]> {
  const suffix = options.metricLevel ? `?metric_level=${encodeURIComponent(options.metricLevel)}` : '';
  const payload = await getJson<{ items: StrategyMetricRow[] }>(
    `/api/strategy-validation/runs/${encodeURIComponent(runId)}/metrics${suffix}`
  );
  return payload.items;
}

export async function fetchStrategyValidationArtifacts(runId: string): Promise<StrategyEvidenceArtifact[]> {
  const payload = await getJson<{ items: StrategyEvidenceArtifact[] }>(
    `/api/strategy-validation/runs/${encodeURIComponent(runId)}/artifacts`
  );
  return payload.items;
}

export async function fetchStrategyValidationReplay(
  runId: string,
  assetId: string,
  startDate: string,
  endDate: string,
  adjustType = 'qfq'
): Promise<StrategyReplayPayload> {
  return getJson<StrategyReplayPayload>(
    `/api/strategy-validation/runs/${encodeURIComponent(runId)}` +
      `/assets/${encodeURIComponent(assetId)}/replay?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&adjust_type=${encodeURIComponent(adjustType)}`
  );
}
```

- [ ] **Step 5: Run client tests**

Run:

```bash
cd dashboard && pnpm test tests/client.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/tests/client.test.ts
git commit -m "feat: add strategy validation frontend API client"
```

---

### Task 5: Strategy Markers And Optional Chart Marker Prop

**Files:**
- Create: `dashboard/src/charts/strategyMarkers.ts`
- Modify: `dashboard/src/charts/AssetChart.tsx`
- Test: `dashboard/tests/strategyMarkers.test.ts`

- [ ] **Step 1: Write failing marker conversion tests**

Create `dashboard/tests/strategyMarkers.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { toStrategyChartMarkers } from '../src/charts/strategyMarkers';
import type { StrategySignal, StrategyTrade } from '../src/api/types';

function signal(overrides: Partial<StrategySignal> = {}): StrategySignal {
  return {
    run_id: 'run-1',
    strategy_id: 'lhb_shortline',
    asset_id: '000001.SZ',
    stock_code: '000001',
    stock_name: '平安银行',
    signal_time: '2026-06-03',
    trade_date: '2026-06-03',
    signal_type: 'support',
    signal_strength: 0.8,
    signal_bucket: 'support',
    risk_bucket: 'normal',
    rule_id: 'rule-1',
    reason: 'support confirmed',
    tags: ['lhb'],
    source_artifact_path: 'outputs/research/lhb.csv',
    ...overrides
  };
}

function trade(overrides: Partial<StrategyTrade> = {}): StrategyTrade {
  return {
    run_id: 'run-1',
    strategy_id: 'lhb_shortline',
    asset_id: '000001.SZ',
    entry_time: '2026-06-04',
    entry_price: 10,
    entry_reason: 'follow',
    exit_time: '2026-06-06',
    exit_price: 11,
    exit_reason: 'exit_confirmed',
    holding_days: 2,
    return_pct: 0.1,
    max_high_return_pct: 0.12,
    max_drawdown_pct: -0.02,
    outcome_status: 'complete',
    source_artifact_path: 'outputs/research/trades.csv',
    ...overrides
  };
}

describe('strategy chart markers', () => {
  it('converts signals and trades into stable marker view models', () => {
    const markers = toStrategyChartMarkers([signal()], [trade()]);

    expect(markers).toEqual([
      {
        time: '2026-06-03',
        position: 'aboveBar',
        color: '#2563eb',
        shape: 'circle',
        text: 'support'
      },
      {
        time: '2026-06-04',
        position: 'belowBar',
        color: '#1f9d55',
        shape: 'arrowUp',
        text: 'entry'
      },
      {
        time: '2026-06-06',
        position: 'aboveBar',
        color: '#d64545',
        shape: 'arrowDown',
        text: 'exit'
      }
    ]);
  });

  it('skips missing trade times', () => {
    const markers = toStrategyChartMarkers([], [trade({ entry_time: null, exit_time: null })]);

    expect(markers).toEqual([]);
  });
});
```

- [ ] **Step 2: Run marker tests and verify they fail**

Run:

```bash
cd dashboard && pnpm test tests/strategyMarkers.test.ts
```

Expected: FAIL because `strategyMarkers.ts` does not exist.

- [ ] **Step 3: Add marker conversion helper**

Create `dashboard/src/charts/strategyMarkers.ts`:

```typescript
import type { SeriesMarker, Time } from 'lightweight-charts';
import type { StrategySignal, StrategyTrade } from '../api/types';

export type StrategyChartMarker = SeriesMarker<Time>;

export function toStrategyChartMarkers(signals: StrategySignal[], trades: StrategyTrade[]): StrategyChartMarker[] {
  const signalMarkers = signals.map((signal) => ({
    time: signal.trade_date as Time,
    position: 'aboveBar' as const,
    color: signal.risk_bucket === 'high' ? '#d64545' : '#2563eb',
    shape: 'circle' as const,
    text: signal.signal_type
  }));

  const tradeMarkers = trades.flatMap((trade) => {
    const markers: StrategyChartMarker[] = [];
    if (trade.entry_time) {
      markers.push({
        time: trade.entry_time as Time,
        position: 'belowBar',
        color: '#1f9d55',
        shape: 'arrowUp',
        text: 'entry'
      });
    }
    if (trade.exit_time) {
      markers.push({
        time: trade.exit_time as Time,
        position: 'aboveBar',
        color: '#d64545',
        shape: 'arrowDown',
        text: 'exit'
      });
    }
    return markers;
  });

  return [...signalMarkers, ...tradeMarkers].sort((left, right) => String(left.time).localeCompare(String(right.time)));
}
```

- [ ] **Step 4: Add optional chart marker prop**

Modify `dashboard/src/charts/AssetChart.tsx`:

```typescript
import {
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  type IChartApi,
  type SeriesMarker,
  type Time
} from 'lightweight-charts';
```

Change props:

```typescript
type AssetChartProps = {
  bars: BarPoint[];
  markers?: SeriesMarker<Time>[];
};
```

Change component signature:

```typescript
export function AssetChart({ bars, markers = [] }: AssetChartProps) {
```

After `candleSeries.setData(toCandlestickData(bars));`, add:

```typescript
    if (markers.length > 0) {
      createSeriesMarkers(candleSeries, markers);
    }
```

Change the effect dependency:

```typescript
  }, [bars, markers]);
```

- [ ] **Step 5: Run marker tests and frontend build**

Run:

```bash
cd dashboard && pnpm test tests/strategyMarkers.test.ts
cd dashboard && pnpm build
```

Expected: marker tests PASS and build PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add dashboard/src/charts/strategyMarkers.ts dashboard/src/charts/AssetChart.tsx dashboard/tests/strategyMarkers.test.ts
git commit -m "feat: add strategy validation chart markers"
```

---

### Task 6: Strategy Validation Workspace And Panels

**Files:**
- Create: `dashboard/src/components/StrategyValidationWorkspace.tsx`
- Create: `dashboard/src/components/StrategyReplayPanel.tsx`
- Create: `dashboard/src/components/StrategyCohortPanel.tsx`
- Create: `dashboard/src/components/StrategyPortfolioRiskPanel.tsx`
- Create: `dashboard/src/components/StrategyEvidencePanel.tsx`
- Test: `dashboard/tests/strategy-validation-workspace.test.tsx`

- [ ] **Step 1: Write failing workspace tests**

Create `dashboard/tests/strategy-validation-workspace.test.tsx`:

```tsx
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StrategyValidationWorkspace } from '../src/components/StrategyValidationWorkspace';
import type { StrategyReplayPayload, StrategyValidationRun } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchStrategyValidationRuns: vi.fn(),
  fetchStrategyValidationReplay: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

vi.mock('../src/charts/AssetChart', () => ({
  AssetChart: ({ bars, markers }: { bars: unknown[]; markers?: unknown[] }) => (
    <div data-testid="strategy-asset-chart">
      {bars.length} bars / {markers?.length ?? 0} markers
    </div>
  )
}));

function makeRun(overrides: Partial<StrategyValidationRun> = {}): StrategyValidationRun {
  return {
    run_id: 'lhb_shortline:fixture:phase16',
    strategy_id: 'lhb_shortline',
    strategy_name: 'LHB Shortline',
    strategy_version: 'phase16',
    run_type: 'replay',
    start_date: '2026-06-01',
    end_date: '2026-06-08',
    created_at: '2026-06-08T20:30:00+08:00',
    benchmark: '000300.SH',
    universe: 'a_share',
    data_window: { bar: 'daily' },
    cost_config: { commission: 0.0003 },
    slippage_config: { bps: 5 },
    risk_config: { max_position_weight: 0.2 },
    position_config: { initial_cash: 1000000 },
    source_artifact_paths: ['outputs/research/lhb.md'],
    summary_metrics: { sample_count: 1, win_rate: 1 },
    warnings: ['fixture-backed run'],
    ...overrides
  };
}

function makeReplay(): StrategyReplayPayload {
  return {
    run: makeRun(),
    asset_id: '000001.SZ',
    bars: [
      { time: '2026-06-03', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }
    ],
    signals: [
      {
        run_id: 'lhb_shortline:fixture:phase16',
        strategy_id: 'lhb_shortline',
        asset_id: '000001.SZ',
        stock_code: '000001',
        stock_name: '平安银行',
        signal_time: '2026-06-03',
        trade_date: '2026-06-03',
        signal_type: 'support',
        signal_strength: 0.86,
        signal_bucket: 'support',
        risk_bucket: 'normal',
        rule_id: 'lhb_phase16_follow',
        reason: 'LHB support behavior with next-day confirmation',
        tags: ['lhb'],
        source_artifact_path: 'outputs/research/lhb.csv'
      }
    ],
    trades: [
      {
        run_id: 'lhb_shortline:fixture:phase16',
        strategy_id: 'lhb_shortline',
        asset_id: '000001.SZ',
        entry_time: '2026-06-04',
        entry_price: 10.5,
        entry_reason: 'phase16_follow_candidate',
        exit_time: '2026-06-06',
        exit_price: 11,
        exit_reason: 'phase16_exit_confirmed',
        holding_days: 2,
        return_pct: 0.0476,
        max_high_return_pct: 0.08,
        max_drawdown_pct: -0.02,
        outcome_status: 'complete',
        source_artifact_path: 'outputs/research/lhb_trades.csv'
      }
    ],
    positions: [
      {
        run_id: 'lhb_shortline:fixture:phase16',
        strategy_id: 'lhb_shortline',
        trade_date: '2026-06-04',
        asset_id: '000001.SZ',
        position_weight: 0.08,
        target_weight: 0.08,
        cash_weight: 0.92,
        exposure: 0.08,
        position_cap: 0.1,
        risk_budget: 0.2,
        suppression_reason: '',
        source_artifact_path: 'outputs/research/lhb_positions.csv'
      }
    ],
    metrics: [
      {
        run_id: 'lhb_shortline:fixture:phase16',
        strategy_id: 'lhb_shortline',
        metric_level: 'signal_bucket',
        group_key: 'support',
        sample_count: 1,
        complete_count: 1,
        win_rate: 1,
        forward_return_mean: 0.0476,
        forward_return_median: 0.0476,
        max_high_return_mean: 0.08,
        max_drawdown_mean: -0.02,
        max_drawdown_worst: -0.02,
        turnover: 0.1,
        exposure_mean: 0.08,
        source_artifact_path: 'outputs/research/lhb_metrics.csv'
      }
    ],
    artifacts: [
      {
        run_id: 'lhb_shortline:fixture:phase16',
        artifact_type: 'markdown',
        title: 'LHB Fixture Report',
        path: 'outputs/research/lhb.md',
        format: 'md',
        trade_date: '2026-06-08',
        description: 'Fixture report'
      }
    ]
  };
}

describe('StrategyValidationWorkspace', () => {
  beforeEach(() => {
    apiMocks.fetchStrategyValidationRuns.mockResolvedValue([makeRun()]);
    apiMocks.fetchStrategyValidationReplay.mockResolvedValue(makeReplay());
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('loads runs and renders replay view', async () => {
    render(<StrategyValidationWorkspace />);

    expect(screen.getByText('Loading strategy validation...')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('LHB Shortline')).toBeInTheDocument());

    expect(screen.getByTestId('strategy-asset-chart')).toHaveTextContent('1 bars / 3 markers');
    expect(screen.getByText('support')).toBeInTheDocument();
    expect(screen.getByText('LHB support behavior with next-day confirmation')).toBeInTheDocument();
  });

  it('shows empty state when there are no runs', async () => {
    apiMocks.fetchStrategyValidationRuns.mockResolvedValue([]);

    render(<StrategyValidationWorkspace />);

    await waitFor(() => expect(screen.getByText('No strategy validation runs found.')).toBeInTheDocument());
  });

  it('switches to cohort, portfolio risk, and evidence tabs', async () => {
    render(<StrategyValidationWorkspace />);

    await waitFor(() => expect(screen.getByText('LHB Shortline')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Cohort' }));
    expect(screen.getByText('support')).toBeInTheDocument();
    expect(screen.getByText('1.00')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Portfolio Risk' }));
    expect(screen.getByText('Exposure 0.08')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Evidence' }));
    expect(screen.getByText('fixture-backed run')).toBeInTheDocument();
    expect(screen.getByText('LHB Fixture Report')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run workspace tests and verify they fail**

Run:

```bash
cd dashboard && pnpm test tests/strategy-validation-workspace.test.tsx
```

Expected: FAIL because `StrategyValidationWorkspace` does not exist.

- [ ] **Step 3: Add Replay panel**

Create `dashboard/src/components/StrategyReplayPanel.tsx`:

```tsx
import type { StrategyReplayPayload } from '../api/types';
import { AssetChart } from '../charts/AssetChart';
import { toStrategyChartMarkers } from '../charts/strategyMarkers';

type StrategyReplayPanelProps = {
  replay: StrategyReplayPayload;
};

function formatPercent(value: number | null) {
  return value === null ? '-' : `${(value * 100).toFixed(2)}%`;
}

export function StrategyReplayPanel({ replay }: StrategyReplayPanelProps) {
  const markers = toStrategyChartMarkers(replay.signals, replay.trades);

  return (
    <section className="strategy-replay">
      <div className="strategy-chart-panel">
        {replay.bars.length > 0 ? (
          <AssetChart bars={replay.bars} markers={markers} />
        ) : (
          <p className="muted">Bars are unavailable for selected range.</p>
        )}
      </div>
      <aside className="strategy-detail-panel">
        <h3>Signals</h3>
        {replay.signals.length === 0 ? (
          <p className="muted">No replay rows for selected asset in this run.</p>
        ) : (
          replay.signals.map((signal) => (
            <div className="strategy-row" key={`${signal.run_id}-${signal.asset_id}-${signal.signal_time}-${signal.signal_type}`}>
              <strong>{signal.signal_type}</strong>
              <span>{signal.reason}</span>
              <small>{signal.rule_id} / {signal.risk_bucket}</small>
            </div>
          ))
        )}
        <h3>Trades</h3>
        {replay.trades.map((trade) => (
          <div className="strategy-row" key={`${trade.run_id}-${trade.asset_id}-${trade.entry_time}-${trade.exit_time}`}>
            <strong>{trade.entry_reason}</strong>
            <span>{trade.exit_reason}</span>
            <small>{trade.outcome_status} / {formatPercent(trade.return_pct)}</small>
          </div>
        ))}
      </aside>
    </section>
  );
}
```

- [ ] **Step 4: Add Cohort panel**

Create `dashboard/src/components/StrategyCohortPanel.tsx`:

```tsx
import type { StrategyMetricRow } from '../api/types';

type StrategyCohortPanelProps = {
  rows: StrategyMetricRow[];
};

function formatNumber(value: number | null) {
  return value === null ? '-' : value.toFixed(2);
}

export function StrategyCohortPanel({ rows }: StrategyCohortPanelProps) {
  if (rows.length === 0) {
    return <p className="muted">No cohort metrics for this run.</p>;
  }

  return (
    <table className="strategy-table">
      <thead>
        <tr>
          <th>Group</th>
          <th>Samples</th>
          <th>Complete</th>
          <th>Win Rate</th>
          <th>Forward Mean</th>
          <th>Max Drawdown</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={`${row.run_id}-${row.metric_level}-${row.group_key}`}>
            <td>{row.group_key}</td>
            <td>{row.sample_count}</td>
            <td>{row.complete_count}</td>
            <td>{formatNumber(row.win_rate)}</td>
            <td>{formatNumber(row.forward_return_mean)}</td>
            <td>{formatNumber(row.max_drawdown_worst)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 5: Add Portfolio Risk panel**

Create `dashboard/src/components/StrategyPortfolioRiskPanel.tsx`:

```tsx
import type { StrategyPositionSnapshot } from '../api/types';

type StrategyPortfolioRiskPanelProps = {
  rows: StrategyPositionSnapshot[];
};

function formatValue(value: number | null) {
  return value === null ? '-' : value.toFixed(2);
}

export function StrategyPortfolioRiskPanel({ rows }: StrategyPortfolioRiskPanelProps) {
  if (rows.length === 0) {
    return <p className="muted">No position snapshots for this run.</p>;
  }

  return (
    <div className="strategy-card-grid">
      {rows.map((row) => (
        <div className="strategy-summary-card" key={`${row.run_id}-${row.asset_id}-${row.trade_date}`}>
          <strong>{row.asset_id}</strong>
          <span>Exposure {formatValue(row.exposure)}</span>
          <span>Position {formatValue(row.position_weight)}</span>
          <span>Cash {formatValue(row.cash_weight)}</span>
          {row.suppression_reason ? <small>{row.suppression_reason}</small> : <small>No suppression</small>}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Add Evidence panel**

Create `dashboard/src/components/StrategyEvidencePanel.tsx`:

```tsx
import type { StrategyEvidenceArtifact, StrategyValidationRun } from '../api/types';

type StrategyEvidencePanelProps = {
  run: StrategyValidationRun;
  artifacts: StrategyEvidenceArtifact[];
};

export function StrategyEvidencePanel({ run, artifacts }: StrategyEvidencePanelProps) {
  return (
    <section className="strategy-evidence">
      <div className="strategy-summary-card">
        <strong>{run.run_id}</strong>
        <span>{run.strategy_version} / {run.run_type}</span>
        <span>{run.start_date} to {run.end_date}</span>
        <span>Benchmark {run.benchmark}</span>
      </div>
      {run.warnings.length > 0 ? (
        <div className="strategy-warning-list">
          {run.warnings.map((warning) => (
            <span key={warning}>{warning}</span>
          ))}
        </div>
      ) : null}
      <table className="strategy-table">
        <thead>
          <tr>
            <th>Artifact</th>
            <th>Format</th>
            <th>Path</th>
          </tr>
        </thead>
        <tbody>
          {artifacts.map((artifact) => (
            <tr key={`${artifact.run_id}-${artifact.path}`}>
              <td>{artifact.title}</td>
              <td>{artifact.format}</td>
              <td>{artifact.path}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
```

- [ ] **Step 7: Add Strategy Validation workspace**

Create `dashboard/src/components/StrategyValidationWorkspace.tsx`:

```tsx
import { useEffect, useMemo, useState } from 'react';
import { fetchStrategyValidationReplay, fetchStrategyValidationRuns } from '../api/client';
import type { StrategyReplayPayload, StrategyValidationRun } from '../api/types';
import { StrategyCohortPanel } from './StrategyCohortPanel';
import { StrategyEvidencePanel } from './StrategyEvidencePanel';
import { StrategyPortfolioRiskPanel } from './StrategyPortfolioRiskPanel';
import { StrategyReplayPanel } from './StrategyReplayPanel';

type StrategyTab = 'replay' | 'cohort' | 'risk' | 'evidence';

const DEFAULT_ASSET_ID = '000001.SZ';

export function StrategyValidationWorkspace() {
  const [runs, setRuns] = useState<StrategyValidationRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState('');
  const [selectedAssetId, setSelectedAssetId] = useState(DEFAULT_ASSET_ID);
  const [activeTab, setActiveTab] = useState<StrategyTab>('replay');
  const [replay, setReplay] = useState<StrategyReplayPayload | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const selectedRun = useMemo(
    () => runs.find((run) => run.run_id === selectedRunId) ?? null,
    [runs, selectedRunId]
  );

  useEffect(() => {
    let ignore = false;
    setIsLoading(true);
    setError(null);
    fetchStrategyValidationRuns()
      .then((rows) => {
        if (!ignore) {
          setRuns(rows);
          setSelectedRunId(rows[0]?.run_id ?? '');
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setIsLoading(false);
        }
      });
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedRun) {
      setReplay(null);
      return;
    }
    let ignore = false;
    setError(null);
    fetchStrategyValidationReplay(selectedRun.run_id, selectedAssetId, selectedRun.start_date, selectedRun.end_date)
      .then((payload) => {
        if (!ignore) {
          setReplay(payload);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setReplay(null);
        }
      });
    return () => {
      ignore = true;
    };
  }, [selectedRun, selectedAssetId]);

  if (isLoading) {
    return <p className="muted">Loading strategy validation...</p>;
  }

  if (runs.length === 0) {
    return <p className="muted">No strategy validation runs found.</p>;
  }

  return (
    <section className="strategy-workspace">
      <header className="strategy-toolbar">
        <select aria-label="strategy validation run" value={selectedRunId} onChange={(event) => setSelectedRunId(event.target.value)}>
          {runs.map((run) => (
            <option key={run.run_id} value={run.run_id}>
              {run.strategy_name}
            </option>
          ))}
        </select>
        <input aria-label="strategy asset id" value={selectedAssetId} onChange={(event) => setSelectedAssetId(event.target.value.trim())} />
        {error ? <span className="error-text">{error}</span> : null}
      </header>
      <nav className="strategy-tabs" aria-label="strategy validation tabs">
        <button type="button" className={activeTab === 'replay' ? 'active' : ''} onClick={() => setActiveTab('replay')}>Replay</button>
        <button type="button" className={activeTab === 'cohort' ? 'active' : ''} onClick={() => setActiveTab('cohort')}>Cohort</button>
        <button type="button" className={activeTab === 'risk' ? 'active' : ''} onClick={() => setActiveTab('risk')}>Portfolio Risk</button>
        <button type="button" className={activeTab === 'evidence' ? 'active' : ''} onClick={() => setActiveTab('evidence')}>Evidence</button>
      </nav>
      {selectedRun && replay ? (
        <>
          {activeTab === 'replay' ? <StrategyReplayPanel replay={replay} /> : null}
          {activeTab === 'cohort' ? <StrategyCohortPanel rows={replay.metrics} /> : null}
          {activeTab === 'risk' ? <StrategyPortfolioRiskPanel rows={replay.positions} /> : null}
          {activeTab === 'evidence' ? <StrategyEvidencePanel run={selectedRun} artifacts={replay.artifacts} /> : null}
        </>
      ) : (
        <p className="muted">No replay rows for selected asset in this run.</p>
      )}
    </section>
  );
}
```

- [ ] **Step 8: Run workspace tests**

Run:

```bash
cd dashboard && pnpm test tests/strategy-validation-workspace.test.tsx
```

Expected: PASS.

- [ ] **Step 9: Commit**

Run:

```bash
git add \
  dashboard/src/components/StrategyValidationWorkspace.tsx \
  dashboard/src/components/StrategyReplayPanel.tsx \
  dashboard/src/components/StrategyCohortPanel.tsx \
  dashboard/src/components/StrategyPortfolioRiskPanel.tsx \
  dashboard/src/components/StrategyEvidencePanel.tsx \
  dashboard/tests/strategy-validation-workspace.test.tsx
git commit -m "feat: add strategy validation workspace"
```

---

### Task 7: App Mode Switch And Styling

**Files:**
- Modify: `dashboard/src/App.tsx`
- Modify: `dashboard/src/styles.css`
- Modify: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Add failing app shell test for mode switch**

In `dashboard/tests/app-shell.test.tsx`, add `fetchStrategyValidationRuns` and `fetchStrategyValidationReplay` to the `apiMocks` object:

```typescript
  fetchStrategyValidationRuns: vi.fn(),
  fetchStrategyValidationReplay: vi.fn()
```

No additional `vi.mock('../src/api/client', () => apiMocks);` change is needed because that mock already returns the full `apiMocks` object.

Add this test near the other `App` tests:

```tsx
  it('switches from research workbench to strategy validation mode', async () => {
    apiMocks.fetchOverview.mockResolvedValue(makeOverview());
    apiMocks.fetchDailyBars.mockResolvedValue(makeBars(2));
    apiMocks.fetchAssetScore.mockResolvedValue(makeScore());
    apiMocks.fetchAssetSignals.mockResolvedValue(makeSignals());
    apiMocks.fetchAssetDecisions.mockResolvedValue(makeDecisions());
    apiMocks.fetchAssetOutcomes.mockResolvedValue(makeOutcomes());
    apiMocks.fetchOutcomeAnalytics.mockResolvedValue(makeOutcomeAnalytics());
    apiMocks.fetchExperimentProposals.mockResolvedValue(makeExperimentProposals());
    apiMocks.fetchExperimentReplay.mockResolvedValue(makeExperimentReplay());
    apiMocks.fetchShadowWatchlist.mockResolvedValue(makeShadowWatchlist());
    apiMocks.fetchShadowOutcomes.mockResolvedValue(makeShadowOutcomes());
    apiMocks.fetchShadowOutcomeAnalytics.mockResolvedValue(makeShadowOutcomeAnalytics());
    apiMocks.fetchShadowAnalyticsReview.mockResolvedValue(makeShadowAnalyticsReview());
    apiMocks.fetchShadowReviewDecisions.mockResolvedValue(makeShadowReviewDecisions());
    apiMocks.fetchShadowFollowUpQueue.mockResolvedValue(makeShadowFollowUpQueue());
    apiMocks.fetchShadowFollowUpResolution.mockResolvedValue(makeShadowFollowUpResolution());
    apiMocks.fetchStrategyValidationRuns.mockResolvedValue([
      {
        run_id: 'lhb_shortline:fixture:phase16',
        strategy_id: 'lhb_shortline',
        strategy_name: 'LHB Shortline',
        strategy_version: 'phase16',
        run_type: 'replay',
        start_date: '2026-06-01',
        end_date: '2026-06-08',
        created_at: '2026-06-08T20:30:00+08:00',
        benchmark: '000300.SH',
        universe: 'a_share',
        data_window: {},
        cost_config: {},
        slippage_config: {},
        risk_config: {},
        position_config: {},
        source_artifact_paths: [],
        summary_metrics: {},
        warnings: []
      }
    ]);
    apiMocks.fetchStrategyValidationReplay.mockResolvedValue({
      run: null,
      asset_id: '000001.SZ',
      bars: [],
      signals: [],
      trades: [],
      positions: [],
      metrics: [],
      artifacts: []
    });

    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: 'Strategy Validation' }));

    await waitFor(() => expect(screen.getByText('LHB Shortline')).toBeInTheDocument());
  });
```

- [ ] **Step 2: Run app shell test and verify it fails**

Run:

```bash
cd dashboard && pnpm test tests/app-shell.test.tsx
```

Expected: FAIL because the `Strategy Validation` mode button does not exist.

- [ ] **Step 3: Add app mode switch**

Modify `dashboard/src/App.tsx`:

Add import:

```typescript
import { StrategyValidationWorkspace } from './components/StrategyValidationWorkspace';
```

Add state near other `useState` calls:

```typescript
  const [workspaceMode, setWorkspaceMode] = useState<'research' | 'strategy'>('research');
```

At the beginning of the returned `<main className="workbench">`, insert:

```tsx
      <div className="mode-switch" aria-label="workspace mode">
        <button
          type="button"
          className={workspaceMode === 'research' ? 'active' : ''}
          onClick={() => setWorkspaceMode('research')}
        >
          Research Workbench
        </button>
        <button
          type="button"
          className={workspaceMode === 'strategy' ? 'active' : ''}
          onClick={() => setWorkspaceMode('strategy')}
        >
          Strategy Validation
        </button>
      </div>
```

Insert this opening conditional immediately before the current `<aside className="sidebar">`:

```tsx
      {workspaceMode === 'strategy' ? (
        <section className="strategy-mode">
          <StrategyValidationWorkspace />
        </section>
      ) : (
        <>
```

Insert this closing conditional immediately after the current inspector `</aside>` and before the final `</main>`:

```tsx
        </>
      )}
```

After the edit, the current `<aside className="sidebar">`, `<section className="workspace">`, and `<aside className="inspector">` blocks are children of the fragment in the research branch.

- [ ] **Step 4: Add styles**

Append to `dashboard/src/styles.css`:

```css
.mode-switch {
  grid-column: 1 / -1;
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid #d9dee7;
  background: #f7f9fc;
}

.mode-switch button,
.strategy-tabs button {
  border: 1px solid #cfd6e2;
  background: #ffffff;
  color: #202936;
  border-radius: 6px;
  padding: 7px 10px;
  font: inherit;
  cursor: pointer;
}

.mode-switch button.active,
.strategy-tabs button.active {
  border-color: #2563eb;
  color: #1d4ed8;
  background: #eef4ff;
}

.strategy-mode {
  grid-column: 1 / -1;
  min-height: 720px;
  padding: 16px;
  overflow: auto;
}

.strategy-workspace {
  display: grid;
  gap: 12px;
}

.strategy-toolbar,
.strategy-tabs {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.strategy-toolbar select,
.strategy-toolbar input {
  min-width: 180px;
}

.strategy-replay {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 12px;
}

.strategy-chart-panel,
.strategy-detail-panel,
.strategy-summary-card,
.strategy-evidence {
  border: 1px solid #d9dee7;
  background: #ffffff;
  border-radius: 8px;
  padding: 12px;
}

.strategy-detail-panel {
  display: grid;
  align-content: start;
  gap: 10px;
}

.strategy-row {
  display: grid;
  gap: 4px;
  border-top: 1px solid #eef1f5;
  padding-top: 8px;
}

.strategy-row span,
.strategy-row small,
.strategy-summary-card span,
.strategy-summary-card small {
  color: #5b6678;
}

.strategy-table {
  width: 100%;
  border-collapse: collapse;
  background: #ffffff;
}

.strategy-table th,
.strategy-table td {
  border: 1px solid #d9dee7;
  padding: 8px;
  text-align: left;
  vertical-align: top;
}

.strategy-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}

.strategy-summary-card {
  display: grid;
  gap: 5px;
}

.strategy-warning-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 10px 0;
}

.strategy-warning-list span {
  border: 1px solid #f4c542;
  background: #fff8df;
  border-radius: 999px;
  padding: 3px 8px;
  color: #7a5c00;
}

@media (max-width: 900px) {
  .strategy-replay {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: Run app shell tests**

Run:

```bash
cd dashboard && pnpm test tests/app-shell.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Run frontend build**

Run:

```bash
cd dashboard && pnpm build
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add dashboard/src/App.tsx dashboard/src/styles.css dashboard/tests/app-shell.test.tsx
git commit -m "feat: add strategy validation dashboard mode"
```

---

### Task 8: Browser Smoke And Full Verification

**Files:**
- Modify: `dashboard/tests/app-smoke.spec.ts`
- Document verification result in final response only

- [ ] **Step 1: Add Playwright route mocks for strategy validation**

In `dashboard/tests/app-smoke.spec.ts`, add route mocks for:

```typescript
await page.route('**/api/strategy-validation/runs', async (route) => {
  await route.fulfill({
    json: {
      items: [
        {
          run_id: 'lhb_shortline:fixture:phase16',
          strategy_id: 'lhb_shortline',
          strategy_name: 'LHB Shortline',
          strategy_version: 'phase16',
          run_type: 'replay',
          start_date: '2026-06-01',
          end_date: '2026-06-08',
          created_at: '2026-06-08T20:30:00+08:00',
          benchmark: '000300.SH',
          universe: 'a_share',
          data_window: {},
          cost_config: {},
          slippage_config: {},
          risk_config: {},
          position_config: {},
          source_artifact_paths: [],
          summary_metrics: {},
          warnings: ['fixture-backed run']
        }
      ]
    }
  });
});

await page.route('**/api/strategy-validation/runs/*/assets/*/replay?*', async (route) => {
  await route.fulfill({
    json: {
      run: null,
      asset_id: '000001.SZ',
      bars: [
        { time: '2026-06-03', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }
      ],
      signals: [],
      trades: [],
      positions: [],
      metrics: [],
      artifacts: []
    }
  });
});
```

- [ ] **Step 2: Add smoke assertion for Strategy Validation mode**

In the desktop smoke test, after existing workbench assertions, add:

```typescript
await page.getByRole('button', { name: 'Strategy Validation' }).click();
await expect(page.getByText('LHB Shortline')).toBeVisible();
await expect(page.getByRole('button', { name: 'Replay' })).toBeVisible();
```

- [ ] **Step 3: Run frontend unit tests**

Run:

```bash
cd dashboard && pnpm test
```

Expected: PASS.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd dashboard && pnpm build
```

Expected: PASS.

- [ ] **Step 5: Run browser smoke tests**

Run:

```bash
cd dashboard && pnpm test:e2e
```

Expected: PASS.

- [ ] **Step 6: Run backend dashboard tests**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_strategy_validation.py tests/test_dashboard_app.py tests/test_dashboard_schemas.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```bash
git add dashboard/tests/app-smoke.spec.ts
git commit -m "test: add strategy validation dashboard smoke"
```

- [ ] **Step 8: Final status check**

Run:

```bash
git status --short
```

Expected: only pre-existing unrelated working-tree changes remain. No uncommitted files from this plan remain.
