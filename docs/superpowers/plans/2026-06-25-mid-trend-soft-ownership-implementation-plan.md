# Mid Trend Soft Ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a baseline-safe `Mid Trend soft ownership optimization` experiment runner with four variants, full-window baseline-vs-variant evaluation, and auditable diagnostics over `2025-01-01` to `2026-06-12`.

**Architecture:** Keep `current_mid_trend_strategy_v1` unchanged and create a separate experimental runner that reuses the same regime/funnel/price inputs but simulates variant-specific target weights and ownership state day by day. The runner must write standalone outputs, verify baseline reproducibility against the known artifact, and stop interpretation if the baseline materially mismatches.

**Tech Stack:** Python, pandas, existing `stock_research` CLI, current `current_mid_trend_strategy_v1`/`mid_trend_strategy_validation` artifacts, pytest.

---

## File Map

- Create: `src/stock_research/mid_trend_soft_ownership_v1.py`
  - Owns configs, baseline rerun check, stateful variant simulation, metrics, diagnostics, and artifact writing.
- Modify: `src/stock_research/cli.py`
  - Adds `mid-trend-soft-ownership-optimize` parser and dispatch.
- Create: `tests/test_mid_trend_soft_ownership_v1.py`
  - Covers baseline pass-through, cash retention, ownership-state boundaries, partial-exit boundaries, and output writing.
- Create: `docs/research/mid_trend_soft_ownership_runbook.md`
  - Documents command usage, variants, outputs, and interpretation rules.

## Task 1: Scaffold Config and Baseline-Safe Module

**Files:**
- Create: `src/stock_research/mid_trend_soft_ownership_v1.py`
- Test: `tests/test_mid_trend_soft_ownership_v1.py`

- [ ] **Step 1: Write the failing config and variant smoke tests**

```python
from pathlib import Path

import pandas as pd

from stock_research.mid_trend_soft_ownership_v1 import (
    DEFAULT_SOFT_OWNERSHIP_END_DATE,
    DEFAULT_SOFT_OWNERSHIP_START_DATE,
    MidTrendSoftOwnershipConfig,
    default_soft_ownership_configs,
)


def test_default_window_is_fixed_full_experiment_window() -> None:
    assert DEFAULT_SOFT_OWNERSHIP_START_DATE == "2025-01-01"
    assert DEFAULT_SOFT_OWNERSHIP_END_DATE == "2026-06-12"


def test_default_soft_ownership_configs_expose_required_variants() -> None:
    configs = default_soft_ownership_configs()
    assert set(configs) == {
        "baseline",
        "entry_soft_weight_v1",
        "ownership_hold_v1",
        "partial_exit_v1",
        "combined_soft_ownership_v1",
    }
    assert configs["baseline"].variant_name == "baseline"
    assert configs["combined_soft_ownership_v1"].start_date == "2025-01-01"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_default_window_is_fixed_full_experiment_window tests/test_mid_trend_soft_ownership_v1.py::test_default_soft_ownership_configs_expose_required_variants -q
```

Expected: FAIL with `ModuleNotFoundError` or missing symbol errors.

- [ ] **Step 3: Write the minimal experimental module scaffold**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_SOFT_OWNERSHIP_START_DATE = "2025-01-01"
DEFAULT_SOFT_OWNERSHIP_END_DATE = "2026-06-12"


@dataclass(frozen=True)
class MidTrendSoftOwnershipConfig:
    variant_name: str
    start_date: str = DEFAULT_SOFT_OWNERSHIP_START_DATE
    end_date: str = DEFAULT_SOFT_OWNERSHIP_END_DATE
    top_n: int = 5
    entry_weak_rank_threshold: int = 20
    entry_extreme_rank_threshold: int = 50
    entry_weak_rank_multiplier: float = 0.7
    entry_weak_regime_multiplier: float = 0.8
    entry_weak_rank_and_regime_multiplier: float = 0.5
    entry_extreme_damage_multiplier: float = 0.1
    ownership_profit_cushion_min: float = 0.08
    ownership_top_rank_memory_threshold: int = 10
    ownership_rank_break_threshold: int = 20
    ownership_damage_rank_threshold: int = 50
    partial_exit_fraction_weak: float = 0.5
    partial_exit_fraction_damage: float = 1.0


def default_soft_ownership_configs() -> dict[str, MidTrendSoftOwnershipConfig]:
    return {
        "baseline": MidTrendSoftOwnershipConfig(variant_name="baseline"),
        "entry_soft_weight_v1": MidTrendSoftOwnershipConfig(variant_name="entry_soft_weight_v1"),
        "ownership_hold_v1": MidTrendSoftOwnershipConfig(variant_name="ownership_hold_v1"),
        "partial_exit_v1": MidTrendSoftOwnershipConfig(variant_name="partial_exit_v1"),
        "combined_soft_ownership_v1": MidTrendSoftOwnershipConfig(variant_name="combined_soft_ownership_v1"),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_default_window_is_fixed_full_experiment_window tests/test_mid_trend_soft_ownership_v1.py::test_default_soft_ownership_configs_expose_required_variants -q
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/mid_trend_soft_ownership_v1.py tests/test_mid_trend_soft_ownership_v1.py
git commit -m "feat: scaffold mid trend soft ownership configs"
```

## Task 2: Baseline Reference Audit and Diff Guard

**Files:**
- Modify: `src/stock_research/mid_trend_soft_ownership_v1.py`
- Test: `tests/test_mid_trend_soft_ownership_v1.py`

- [ ] **Step 1: Write the failing baseline reference tests**

```python
def test_compare_baseline_to_reference_reports_series_and_row_count_diffs(tmp_path: Path) -> None:
    from stock_research.mid_trend_soft_ownership_v1 import compare_baseline_to_reference

    rerun = {
        "equity": pd.DataFrame(
            [
                {"trade_date": "2025-01-02", "equity": 1.00},
                {"trade_date": "2025-01-03", "equity": 1.01},
            ]
        ),
        "holdings": pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "A"}]),
        "trades": pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "A"}]),
        "summary": pd.DataFrame(
            [{"strategy_family": "current_mid_trend_strategy_v1", "total_return": 0.01, "max_drawdown": -0.02}]
        ),
    }
    reference_dir = tmp_path / "reference"
    reference_dir.mkdir()
    pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "equity": 1.00},
            {"trade_date": "2025-01-03", "equity": 1.02},
        ]
    ).to_csv(reference_dir / "current_mid_trend_strategy_v1_equity.csv", index=False)
    pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "A"}]).to_csv(
        reference_dir / "current_mid_trend_strategy_v1_daily_holdings.csv", index=False
    )
    pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "A"}]).to_csv(
        reference_dir / "current_mid_trend_strategy_v1_trade_changes.csv", index=False
    )
    pd.DataFrame(
        [{"strategy_family": "current_mid_trend_strategy_v1", "total_return": 0.02, "max_drawdown": -0.02}]
    ).to_csv(reference_dir / "current_mid_trend_strategy_v1_summary.csv", index=False)

    report = compare_baseline_to_reference(rerun, reference_dir=reference_dir)

    assert report["baseline_match"] is False
    assert float(report["final_equity_diff"]) != 0.0
    assert "equity_series_max_abs_diff" in report
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_compare_baseline_to_reference_reports_series_and_row_count_diffs -q
```

Expected: FAIL with missing function errors.

- [ ] **Step 3: Implement baseline reference comparison and diff report writer**

```python
REFERENCE_BASELINE_DIR = (
    Path(__file__).resolve().parents[2]
    / "outputs"
    / "research"
    / "current_mid_trend_strategy_v1_20250101_20260612_retest"
)


def compare_baseline_to_reference(
    rerun: dict[str, pd.DataFrame],
    *,
    reference_dir: str | Path = REFERENCE_BASELINE_DIR,
    equity_tolerance: float = 1e-9,
    summary_tolerance: float = 1e-9,
) -> dict[str, object]:
    reference = Path(reference_dir)
    equity_ref = pd.read_csv(reference / "current_mid_trend_strategy_v1_equity.csv")
    holdings_ref = pd.read_csv(reference / "current_mid_trend_strategy_v1_daily_holdings.csv", low_memory=False)
    trades_ref = pd.read_csv(reference / "current_mid_trend_strategy_v1_trade_changes.csv", low_memory=False)
    summary_ref = pd.read_csv(reference / "current_mid_trend_strategy_v1_summary.csv")
    rerun_equity = rerun["equity"].copy()
    rerun_summary = rerun["summary"].copy()
    merged = rerun_equity[["trade_date", "equity"]].merge(
        equity_ref[["trade_date", "equity"]],
        on="trade_date",
        how="outer",
        suffixes=("_rerun", "_reference"),
    ).sort_values("trade_date")
    merged["abs_diff"] = (pd.to_numeric(merged["equity_rerun"], errors="coerce") - pd.to_numeric(
        merged["equity_reference"], errors="coerce"
    )).abs()
    final_equity_diff = (
        float(rerun_equity["equity"].iloc[-1]) - float(equity_ref["equity"].iloc[-1])
        if not rerun_equity.empty and not equity_ref.empty
        else float("nan")
    )
    total_return_diff = float(rerun_summary["total_return"].iloc[0]) - float(summary_ref["total_return"].iloc[0])
    max_drawdown_diff = float(rerun_summary["max_drawdown"].iloc[0]) - float(summary_ref["max_drawdown"].iloc[0])
    holdings_row_diff = int(len(rerun["holdings"])) - int(len(holdings_ref))
    trades_row_diff = int(len(rerun["trades"])) - int(len(trades_ref))
    baseline_match = (
        abs(final_equity_diff) <= equity_tolerance
        and abs(total_return_diff) <= summary_tolerance
        and abs(max_drawdown_diff) <= summary_tolerance
        and holdings_row_diff == 0
        and trades_row_diff == 0
        and float(merged["abs_diff"].fillna(0.0).max()) <= equity_tolerance
    )
    return {
        "baseline_match": baseline_match,
        "holdings_row_diff": holdings_row_diff,
        "trades_row_diff": trades_row_diff,
        "final_equity_diff": final_equity_diff,
        "total_return_diff": total_return_diff,
        "max_drawdown_diff": max_drawdown_diff,
        "equity_series_max_abs_diff": float(merged["abs_diff"].fillna(0.0).max()),
        "equity_series_diff": merged,
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_compare_baseline_to_reference_reports_series_and_row_count_diffs -q
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/mid_trend_soft_ownership_v1.py tests/test_mid_trend_soft_ownership_v1.py
git commit -m "feat: add mid trend baseline diff guard"
```

## Task 3: Build Full-Funnel State Access and Ownership Inputs

**Files:**
- Modify: `src/stock_research/mid_trend_soft_ownership_v1.py`
- Test: `tests/test_mid_trend_soft_ownership_v1.py`

- [ ] **Step 1: Write the failing state lookup tests**

```python
def test_daily_meta_lookup_reads_assets_even_when_not_in_protected_selection() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import build_daily_meta_lookup

    funnel = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "A", "score_rank": 3, "mid_trend_layer": "stable_trend_watch"},
            {"trade_date": "2025-01-03", "asset_id": "A", "score_rank": 25, "mid_trend_layer": "pullback_reacceleration_watch"},
        ]
    )

    lookup = build_daily_meta_lookup(funnel)

    assert ("2025-01-03", "A") in lookup
    assert lookup[("2025-01-03", "A")]["score_rank"] == 25


def test_daily_meta_lookup_marks_missing_meta_state() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import resolve_asset_day_meta

    meta = resolve_asset_day_meta({}, trade_date="2025-01-03", asset_id="A")

    assert meta["missing_meta_state"] == "missing_meta_state"
    assert pd.isna(meta["score_rank"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_daily_meta_lookup_reads_assets_even_when_not_in_protected_selection tests/test_mid_trend_soft_ownership_v1.py::test_daily_meta_lookup_marks_missing_meta_state -q
```

Expected: FAIL with missing function errors.

- [ ] **Step 3: Implement full-funnel day lookup helpers**

```python
META_COLUMNS = [
    "trade_date",
    "asset_id",
    "score_rank",
    "mid_trend_layer",
    "mid_trend_funnel_score",
    "confirmed_regime_state",
    "ret_20_score",
    "ret_60_score",
    "max_drawdown_20_score",
    "stock_excess_ret_20_score",
]


def build_daily_meta_lookup(funnel: pd.DataFrame) -> dict[tuple[str, str], dict[str, object]]:
    frame = funnel.copy()
    for column in META_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    frame["asset_id"] = frame["asset_id"].astype(str)
    return {
        (str(row["trade_date"]), str(row["asset_id"])): row
        for row in frame[META_COLUMNS].dropna(subset=["trade_date", "asset_id"]).drop_duplicates(
            ["trade_date", "asset_id"], keep="last"
        ).to_dict("records")
    }


def resolve_asset_day_meta(
    meta_lookup: dict[tuple[str, str], dict[str, object]],
    *,
    trade_date: str,
    asset_id: str,
) -> dict[str, object]:
    row = dict(meta_lookup.get((str(trade_date), str(asset_id)), {}))
    if row:
        row["missing_meta_state"] = ""
        return row
    return {
        "trade_date": trade_date,
        "asset_id": asset_id,
        "score_rank": pd.NA,
        "mid_trend_layer": pd.NA,
        "mid_trend_funnel_score": pd.NA,
        "confirmed_regime_state": pd.NA,
        "ret_20_score": pd.NA,
        "ret_60_score": pd.NA,
        "max_drawdown_20_score": pd.NA,
        "stock_excess_ret_20_score": pd.NA,
        "missing_meta_state": "missing_meta_state",
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_daily_meta_lookup_reads_assets_even_when_not_in_protected_selection tests/test_mid_trend_soft_ownership_v1.py::test_daily_meta_lookup_marks_missing_meta_state -q
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/mid_trend_soft_ownership_v1.py tests/test_mid_trend_soft_ownership_v1.py
git commit -m "feat: add full-funnel state lookup for soft ownership"
```

## Task 4: Entry Soft Weight With Cash Retention

**Files:**
- Modify: `src/stock_research/mid_trend_soft_ownership_v1.py`
- Test: `tests/test_mid_trend_soft_ownership_v1.py`

- [ ] **Step 1: Write the failing entry soft-weight tests**

```python
def test_entry_soft_weight_reduces_weight_and_keeps_released_weight_in_cash() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import (
        MidTrendSoftOwnershipConfig,
        apply_entry_soft_weight,
    )

    config = MidTrendSoftOwnershipConfig(variant_name="entry_soft_weight_v1")
    day = pd.DataFrame(
        [
            {"asset_id": "A", "base_target_weight": 0.2, "score_rank": 5, "mid_trend_layer": "stable_trend_watch", "confirmed_regime_state": "bull_trend", "max_drawdown_20_score": 80, "stock_excess_ret_20_score": 80},
            {"asset_id": "B", "base_target_weight": 0.2, "score_rank": 35, "mid_trend_layer": "high_elasticity_watch", "confirmed_regime_state": "bull_trend", "max_drawdown_20_score": 70, "stock_excess_ret_20_score": 70},
        ]
    )

    adjusted = apply_entry_soft_weight(day, config=config)

    assert adjusted.loc[adjusted["asset_id"] == "A", "adjusted_target_weight"].iloc[0] == 0.2
    assert adjusted.loc[adjusted["asset_id"] == "B", "adjusted_target_weight"].iloc[0] == 0.14
    assert adjusted["adjusted_target_weight"].sum() == 0.34
    assert adjusted["released_to_cash"].sum() == 0.06
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_entry_soft_weight_reduces_weight_and_keeps_released_weight_in_cash -q
```

Expected: FAIL with missing function errors.

- [ ] **Step 3: Implement entry multiplier assignment without renormalization**

```python
def _entry_soft_weight_rule(row: pd.Series, config: MidTrendSoftOwnershipConfig) -> tuple[float, str]:
    weak_rank = (
        pd.notna(row.get("score_rank"))
        and (
            float(row["score_rank"]) > float(config.entry_weak_rank_threshold)
            or (
                float(row["score_rank"]) > 10.0
                and str(row.get("mid_trend_layer")) == "high_elasticity_watch"
            )
        )
    )
    weak_regime = str(row.get("confirmed_regime_state") or "") in {"overheated", "trend_decay"}
    extreme_damage = (
        pd.notna(row.get("score_rank"))
        and float(row["score_rank"]) > float(config.entry_extreme_rank_threshold)
        and weak_regime
        and (
            float(pd.to_numeric(pd.Series([row.get("max_drawdown_20_score")]), errors="coerce").iloc[0] or 0.0) < 45.0
            or float(pd.to_numeric(pd.Series([row.get("stock_excess_ret_20_score")]), errors="coerce").iloc[0] or 0.0) < 40.0
        )
    )
    if extreme_damage:
        return config.entry_extreme_damage_multiplier, "extreme_damage"
    if weak_rank and weak_regime:
        return config.entry_weak_rank_and_regime_multiplier, "weak_rank_and_weak_regime"
    if weak_rank:
        return config.entry_weak_rank_multiplier, "weak_rank_only"
    if weak_regime:
        return config.entry_weak_regime_multiplier, "weak_regime_only"
    return 1.0, "normal"


def apply_entry_soft_weight(day: pd.DataFrame, *, config: MidTrendSoftOwnershipConfig) -> pd.DataFrame:
    frame = day.copy()
    frame["entry_weight_multiplier"] = 1.0
    frame["entry_soft_reason"] = "normal"
    for index, row in frame.iterrows():
        multiplier, reason = _entry_soft_weight_rule(row, config)
        frame.at[index, "entry_weight_multiplier"] = multiplier
        frame.at[index, "entry_soft_reason"] = reason
    frame["adjusted_target_weight"] = pd.to_numeric(frame["base_target_weight"], errors="coerce").fillna(0.0) * pd.to_numeric(
        frame["entry_weight_multiplier"], errors="coerce"
    ).fillna(1.0)
    frame["released_to_cash"] = (
        pd.to_numeric(frame["base_target_weight"], errors="coerce").fillna(0.0)
        - frame["adjusted_target_weight"].astype(float)
    ).clip(lower=0.0)
    return frame
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_entry_soft_weight_reduces_weight_and_keeps_released_weight_in_cash -q
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/mid_trend_soft_ownership_v1.py tests/test_mid_trend_soft_ownership_v1.py
git commit -m "feat: add entry soft weight with cash retention"
```

## Task 5: Ownership State and Confirmed-Damage Boundary

**Files:**
- Modify: `src/stock_research/mid_trend_soft_ownership_v1.py`
- Test: `tests/test_mid_trend_soft_ownership_v1.py`

- [ ] **Step 1: Write the failing ownership-state tests**

```python
def test_ownership_state_allows_noisy_winner_with_rank_memory_and_profit_cushion() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import MidTrendSoftOwnershipConfig, evaluate_ownership_state

    config = MidTrendSoftOwnershipConfig(variant_name="ownership_hold_v1")
    state = evaluate_ownership_state(
        meta={
            "score_rank": 22,
            "mid_trend_layer": "pullback_reacceleration_watch",
            "max_drawdown_20_score": 60,
            "stock_excess_ret_20_score": 65,
        },
        prior_best_rank=4,
        profit_cushion=0.18,
        atr_damage=False,
        repeated_rank_break=False,
        config=config,
    )

    assert state["ownership_state"] == "owned_noisy_but_valid"
    assert state["confirmed_damage_flag"] is False


def test_ownership_state_treats_risk_exclusion_as_confirmed_damage() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import MidTrendSoftOwnershipConfig, evaluate_ownership_state

    config = MidTrendSoftOwnershipConfig(variant_name="ownership_hold_v1")
    state = evaluate_ownership_state(
        meta={
            "score_rank": 70,
            "mid_trend_layer": "risk_exclusion_watch",
            "max_drawdown_20_score": 20,
            "stock_excess_ret_20_score": 20,
        },
        prior_best_rank=3,
        profit_cushion=-0.02,
        atr_damage=False,
        repeated_rank_break=True,
        config=config,
    )

    assert state["ownership_state"] == "ownership_broken"
    assert state["confirmed_damage_flag"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_ownership_state_allows_noisy_winner_with_rank_memory_and_profit_cushion tests/test_mid_trend_soft_ownership_v1.py::test_ownership_state_treats_risk_exclusion_as_confirmed_damage -q
```

Expected: FAIL with missing function errors.

- [ ] **Step 3: Implement ownership-state evaluation**

```python
def evaluate_ownership_state(
    *,
    meta: dict[str, object],
    prior_best_rank: int | None,
    profit_cushion: float,
    atr_damage: bool,
    repeated_rank_break: bool,
    config: MidTrendSoftOwnershipConfig,
) -> dict[str, object]:
    score_rank = pd.to_numeric(pd.Series([meta.get("score_rank")]), errors="coerce").iloc[0]
    layer = str(meta.get("mid_trend_layer") or "")
    drawdown_score = pd.to_numeric(pd.Series([meta.get("max_drawdown_20_score")]), errors="coerce").iloc[0]
    excess_score = pd.to_numeric(pd.Series([meta.get("stock_excess_ret_20_score")]), errors="coerce").iloc[0]
    no_cushion = profit_cushion <= 0.0
    confirmed_damage = bool(
        atr_damage
        or layer == "risk_exclusion_watch"
        or repeated_rank_break
        or (
            pd.notna(drawdown_score)
            and pd.notna(excess_score)
            and float(drawdown_score) < 35.0
            and float(excess_score) < 35.0
        )
        or (no_cushion and pd.notna(score_rank) and float(score_rank) > float(config.ownership_rank_break_threshold))
    )
    if prior_best_rank is not None and prior_best_rank <= config.ownership_top_rank_memory_threshold:
        rank_memory_state = "front_rank_memory"
    elif prior_best_rank is not None and prior_best_rank <= 20:
        rank_memory_state = "secondary_rank_memory"
    else:
        rank_memory_state = "no_rank_memory"
    if profit_cushion >= config.ownership_profit_cushion_min:
        profit_cushion_state = "cushion_strong"
    elif profit_cushion > 0:
        profit_cushion_state = "cushion_small"
    else:
        profit_cushion_state = "no_cushion"
    if confirmed_damage:
        return {
            "ownership_state": "ownership_broken",
            "ownership_reason": "confirmed_damage",
            "rank_memory_state": rank_memory_state,
            "profit_cushion_state": profit_cushion_state,
            "damage_state": "confirmed_damage",
            "confirmed_damage_flag": True,
        }
    if pd.notna(score_rank) and float(score_rank) <= 10 and layer in {"stable_trend_watch", "mainline_momentum_watch"}:
        state = "owned_strong"
    elif rank_memory_state == "front_rank_memory" and profit_cushion > 0:
        state = "owned_noisy_but_valid"
    else:
        state = "owned_weak"
    return {
        "ownership_state": state,
        "ownership_reason": state,
        "rank_memory_state": rank_memory_state,
        "profit_cushion_state": profit_cushion_state,
        "damage_state": "soft_damage" if state == "owned_weak" else "none",
        "confirmed_damage_flag": False,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_ownership_state_allows_noisy_winner_with_rank_memory_and_profit_cushion tests/test_mid_trend_soft_ownership_v1.py::test_ownership_state_treats_risk_exclusion_as_confirmed_damage -q
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/mid_trend_soft_ownership_v1.py tests/test_mid_trend_soft_ownership_v1.py
git commit -m "feat: add ownership state and confirmed damage boundary"
```

## Task 6: Partial Exit Without Ownership Suppression

**Files:**
- Modify: `src/stock_research/mid_trend_soft_ownership_v1.py`
- Test: `tests/test_mid_trend_soft_ownership_v1.py`

- [ ] **Step 1: Write the failing partial-exit boundary tests**

```python
def test_partial_exit_variant_reduces_weight_without_extending_holding_by_ownership() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import determine_exit_action

    result = determine_exit_action(
        variant_name="partial_exit_v1",
        baseline_exit_signal=True,
        ownership_state="owned_noisy_but_valid",
        confirmed_damage=False,
        current_weight=0.2,
        reduce_fraction=0.5,
    )

    assert result["exit_action"] == "reduce"
    assert result["exit_fraction"] == 0.5
    assert result["whether_exit_was_suppressed_by_ownership"] is False


def test_confirmed_damage_forces_full_exit_for_all_variants() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import determine_exit_action

    result = determine_exit_action(
        variant_name="ownership_hold_v1",
        baseline_exit_signal=True,
        ownership_state="owned_noisy_but_valid",
        confirmed_damage=True,
        current_weight=0.2,
        reduce_fraction=0.5,
    )

    assert result["exit_action"] == "full_exit"
    assert result["exit_fraction"] == 1.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_partial_exit_variant_reduces_weight_without_extending_holding_by_ownership tests/test_mid_trend_soft_ownership_v1.py::test_confirmed_damage_forces_full_exit_for_all_variants -q
```

Expected: FAIL with missing function errors.

- [ ] **Step 3: Implement exit-action logic with clean ablation boundaries**

```python
def determine_exit_action(
    *,
    variant_name: str,
    baseline_exit_signal: bool,
    ownership_state: str,
    confirmed_damage: bool,
    current_weight: float,
    reduce_fraction: float,
) -> dict[str, object]:
    if not baseline_exit_signal:
        return {
            "exit_action": "hold",
            "exit_fraction": 0.0,
            "target_weight_after_exit": current_weight,
            "whether_exit_was_suppressed_by_ownership": False,
        }
    if confirmed_damage:
        return {
            "exit_action": "full_exit",
            "exit_fraction": 1.0,
            "target_weight_after_exit": 0.0,
            "whether_exit_was_suppressed_by_ownership": False,
        }
    if variant_name == "partial_exit_v1":
        next_weight = current_weight * (1.0 - reduce_fraction)
        return {
            "exit_action": "reduce",
            "exit_fraction": reduce_fraction,
            "target_weight_after_exit": next_weight,
            "whether_exit_was_suppressed_by_ownership": False,
        }
    if variant_name in {"ownership_hold_v1", "combined_soft_ownership_v1"} and ownership_state in {
        "owned_strong",
        "owned_noisy_but_valid",
    }:
        return {
            "exit_action": "hold",
            "exit_fraction": 0.0,
            "target_weight_after_exit": current_weight,
            "whether_exit_was_suppressed_by_ownership": True,
        }
    return {
        "exit_action": "full_exit",
        "exit_fraction": 1.0,
        "target_weight_after_exit": 0.0,
        "whether_exit_was_suppressed_by_ownership": False,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_partial_exit_variant_reduces_weight_without_extending_holding_by_ownership tests/test_mid_trend_soft_ownership_v1.py::test_confirmed_damage_forces_full_exit_for_all_variants -q
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/mid_trend_soft_ownership_v1.py tests/test_mid_trend_soft_ownership_v1.py
git commit -m "feat: add partial exit ablation boundaries"
```

## Task 7: Stateful Variant Simulation and Output Writing

**Files:**
- Modify: `src/stock_research/mid_trend_soft_ownership_v1.py`
- Test: `tests/test_mid_trend_soft_ownership_v1.py`

- [ ] **Step 1: Write the failing runner output test**

```python
def test_run_soft_ownership_experiment_writes_required_artifacts(tmp_path: Path) -> None:
    from stock_research.mid_trend_soft_ownership_v1 import run_mid_trend_soft_ownership_experiment

    result = run_mid_trend_soft_ownership_experiment(
        start_date="2025-01-01",
        end_date="2026-06-12",
        output_dir=tmp_path,
        baseline_result={
            "equity": pd.DataFrame([{"trade_date": "2025-01-02", "daily_return": 0.01, "equity": 1.01}]),
            "summary": pd.DataFrame([{"strategy_family": "current_mid_trend_strategy_v1", "total_return": 0.01, "annualized_return": 0.01, "max_drawdown": -0.01, "days": 1}]),
            "holdings": pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "A", "target_weight": 0.2}]),
            "trades": pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "A", "action": "buy"}]),
        },
        baseline_reference_check={"baseline_match": True},
        funnel=pd.DataFrame(),
        regime=pd.DataFrame(),
        prices=pd.DataFrame(),
        variants=["baseline"],
    )

    assert (tmp_path / "code_audit.md").exists()
    assert (tmp_path / "baseline_vs_variants.csv").exists()
    assert (tmp_path / "baseline_vs_variants.md").exists()
    assert (tmp_path / "final_interpretation.md").exists()
    assert "paths" in result
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_run_soft_ownership_experiment_writes_required_artifacts -q
```

Expected: FAIL with missing runner errors.

- [ ] **Step 3: Implement the first end-to-end artifact writer**

```python
def run_mid_trend_soft_ownership_experiment(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    baseline_result: dict[str, pd.DataFrame],
    baseline_reference_check: dict[str, object],
    funnel: pd.DataFrame,
    regime: pd.DataFrame,
    prices: pd.DataFrame,
    variants: list[str],
) -> dict[str, object]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    code_audit_path = output / "code_audit.md"
    baseline_vs_variants_csv = output / "baseline_vs_variants.csv"
    baseline_vs_variants_md = output / "baseline_vs_variants.md"
    trade_level_path = output / "trade_level_diagnostics.csv"
    ownership_path = output / "ownership_event_diagnostics.csv"
    exit_path = output / "exit_event_diagnostics.csv"
    bucket_path = output / "bucket_contribution_entry_weight.csv"
    suppressed_path = output / "suppressed_exit_analysis.csv"
    interpretation_path = output / "final_interpretation.md"
    code_audit_path.write_text("# Code Audit\n\nGenerated by experiment runner.\n", encoding="utf-8")
    summary = pd.DataFrame(
        [
            {
                "variant_name": "baseline",
                "total_return": float(pd.to_numeric(baseline_result["summary"]["total_return"], errors="coerce").iloc[0]),
                "annualized_return": float(pd.to_numeric(baseline_result["summary"]["annualized_return"], errors="coerce").iloc[0]),
                "max_drawdown": float(pd.to_numeric(baseline_result["summary"]["max_drawdown"], errors="coerce").iloc[0]),
                "average_exposure": float(pd.to_numeric(baseline_result["holdings"]["target_weight"], errors="coerce").sum()),
                "cash_weight_avg": 0.0,
                "min_exposure": float(pd.to_numeric(baseline_result["holdings"]["target_weight"], errors="coerce").sum()),
                "max_exposure": float(pd.to_numeric(baseline_result["holdings"]["target_weight"], errors="coerce").sum()),
                "return_per_unit_exposure": float(pd.to_numeric(baseline_result["summary"]["total_return"], errors="coerce").iloc[0]),
                "baseline_match": bool(baseline_reference_check["baseline_match"]),
            }
        ]
    )
    summary.to_csv(baseline_vs_variants_csv, index=False)
    baseline_vs_variants_md.write_text(summary.to_markdown(index=False) + "\n", encoding="utf-8")
    pd.DataFrame().to_csv(trade_level_path, index=False)
    pd.DataFrame().to_csv(ownership_path, index=False)
    pd.DataFrame().to_csv(exit_path, index=False)
    pd.DataFrame().to_csv(bucket_path, index=False)
    pd.DataFrame().to_csv(suppressed_path, index=False)
    interpretation_path.write_text("# Final Interpretation\n\nPending full implementation.\n", encoding="utf-8")
    return {
        "summary": summary,
        "paths": {
            "code_audit": str(code_audit_path),
            "baseline_vs_variants_csv": str(baseline_vs_variants_csv),
            "baseline_vs_variants_md": str(baseline_vs_variants_md),
            "trade_level_diagnostics": str(trade_level_path),
            "ownership_event_diagnostics": str(ownership_path),
            "exit_event_diagnostics": str(exit_path),
            "bucket_contribution_entry_weight": str(bucket_path),
            "suppressed_exit_analysis": str(suppressed_path),
            "final_interpretation": str(interpretation_path),
        },
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_run_soft_ownership_experiment_writes_required_artifacts -q
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/mid_trend_soft_ownership_v1.py tests/test_mid_trend_soft_ownership_v1.py
git commit -m "feat: add soft ownership artifact writer"
```

## Task 8: CLI Entry and Runbook

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_mid_trend_soft_ownership_v1.py`
- Create: `docs/research/mid_trend_soft_ownership_runbook.md`

- [ ] **Step 1: Write the failing CLI parser and dispatch tests**

```python
from stock_research import cli


def test_cli_parser_accepts_mid_trend_soft_ownership_command() -> None:
    args = cli.build_parser().parse_args(
        [
            "mid-trend-soft-ownership-optimize",
            "--output-dir",
            "outputs/research/test_soft_ownership",
        ]
    )
    assert args.command == "mid-trend-soft-ownership-optimize"
    assert args.start_date == "2025-01-01"
    assert args.end_date == "2026-06-12"


def test_cli_dispatch_calls_soft_ownership_runner(tmp_path: Path, monkeypatch) -> None:
    called: dict[str, object] = {}

    def _fake_runner(**kwargs: object) -> dict[str, object]:
        called.update(kwargs)
        return {"paths": {"baseline_vs_variants_csv": str(tmp_path / "baseline_vs_variants.csv")}}

    monkeypatch.setattr(
        "stock_research.mid_trend_soft_ownership_v1.run_mid_trend_soft_ownership_cli",
        _fake_runner,
    )

    rc = cli.main(["mid-trend-soft-ownership-optimize", "--output-dir", str(tmp_path)])

    assert rc in {0, None}
    assert called["start_date"] == "2025-01-01"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_cli_parser_accepts_mid_trend_soft_ownership_command tests/test_mid_trend_soft_ownership_v1.py::test_cli_dispatch_calls_soft_ownership_runner -q
```

Expected: FAIL because the CLI command does not exist.

- [ ] **Step 3: Add CLI parser branch, dispatch, and runbook**

```python
# build_parser()
mid_trend_soft = subparsers.add_parser("mid-trend-soft-ownership-optimize")
mid_trend_soft.add_argument("--start-date", default="2025-01-01")
mid_trend_soft.add_argument("--end-date", default="2026-06-12")
mid_trend_soft.add_argument("--output-dir", required=True)
mid_trend_soft.add_argument(
    "--variants",
    nargs="*",
    default=[
        "baseline",
        "entry_soft_weight_v1",
        "ownership_hold_v1",
        "partial_exit_v1",
        "combined_soft_ownership_v1",
    ],
)


# main_for_args()
elif args.command == "mid-trend-soft-ownership-optimize":
    from stock_research.mid_trend_soft_ownership_v1 import run_mid_trend_soft_ownership_cli

    result = run_mid_trend_soft_ownership_cli(
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=args.output_dir,
        variants=args.variants,
    )
    print(f"mid_trend_soft_ownership|baseline_vs_variants|{result['paths']['baseline_vs_variants_csv']}")
```

```md
# Mid Trend Soft Ownership Runbook

Run baseline + default variants:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/stock-research mid-trend-soft-ownership-optimize \
  --output-dir outputs/research/mid_trend_soft_ownership_optimization_manual
```

Artifacts:

- `code_audit.md`
- `baseline_vs_variants.csv`
- `final_interpretation.md`
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_cli_parser_accepts_mid_trend_soft_ownership_command tests/test_mid_trend_soft_ownership_v1.py::test_cli_dispatch_calls_soft_ownership_runner -q
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/cli.py src/stock_research/mid_trend_soft_ownership_v1.py tests/test_mid_trend_soft_ownership_v1.py docs/research/mid_trend_soft_ownership_runbook.md
git commit -m "feat: add mid trend soft ownership cli"
```

## Task 9: Full Variant Engine, Metrics, and Interpretation

**Files:**
- Modify: `src/stock_research/mid_trend_soft_ownership_v1.py`
- Modify: `tests/test_mid_trend_soft_ownership_v1.py`

- [ ] **Step 1: Write focused failing tests for the final metrics helpers**

```python
def test_variant_summary_includes_exposure_metrics_and_return_per_unit_exposure() -> None:
    from stock_research.mid_trend_soft_ownership_v1 import summarize_variant_metrics

    equity = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "daily_return": 0.01, "equity": 1.01, "invested_weight": 0.8},
            {"trade_date": "2025-01-03", "daily_return": 0.00, "equity": 1.01, "invested_weight": 0.6},
        ]
    )
    trades = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "A", "action": "buy", "pnl": 0.1, "holding_days": 5},
            {"trade_date": "2025-01-03", "asset_id": "A", "action": "sell", "pnl": -0.05, "holding_days": 3},
        ]
    )
    audit = pd.DataFrame(
        [
            {"audit_label": "bad_buy"},
            {"audit_label": "bad_sell"},
        ]
    )

    summary = summarize_variant_metrics("baseline", equity=equity, trades=trades, audit_detail=audit)

    assert "average_exposure" in summary
    assert "cash_weight_avg" in summary
    assert "return_per_unit_exposure" in summary
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_variant_summary_includes_exposure_metrics_and_return_per_unit_exposure -q
```

Expected: FAIL with missing function errors.

- [ ] **Step 3: Finish the production implementation**

Implement in `src/stock_research/mid_trend_soft_ownership_v1.py`:

- `run_mid_trend_soft_ownership_cli(...)`
- baseline rerun using existing regime/funnel inputs
- baseline diff report writing and hard stop on mismatch
- full daily simulation for all variants
- ownership carry logic using full-funnel lookup
- partial exit logic with cash retention
- addback tracking
- trade-level diagnostics generation
- ownership event diagnostics generation
- exit event diagnostics generation
- entry multiplier bucket contribution generation
- suppressed exit analysis generation
- variant summary table generation
- markdown summary rendering
- final interpretation writer that answers:
  - hard veto failure
  - entry soft weight vs entry veto
  - ownership hold saved winners vs false holds
  - partial exit vs full exit
  - combined variant vs baseline
  - improvement source
  - effective vs ineffective rules
  - whether to continue parameter search
  - which parameters to tune or avoid
  - whether return and drawdown changes are mainly exposure/cash effects
  - whether top winners were harmed by entry soft weighting
  - whether released capital stayed in cash

- [ ] **Step 4: Run the focused test and then the full file**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py::test_variant_summary_includes_exposure_metrics_and_return_per_unit_exposure -q
PYTHONPATH=src .venv/bin/pytest tests/test_mid_trend_soft_ownership_v1.py -q
```

Expected: all PASS.

- [ ] **Step 5: Run the full experiment**

Run:

```bash
cd /Users/xiwei/stock_research
PYTHONPATH=src .venv/bin/stock-research mid-trend-soft-ownership-optimize \
  --start-date 2025-01-01 \
  --end-date 2026-06-12 \
  --output-dir outputs/research/mid_trend_soft_ownership_optimization_20260625
```

Expected:

- baseline reproduced or diff report written and the run stops
- if baseline reproduced, all variant outputs are written
- `baseline_vs_variants.csv` exists
- `final_interpretation.md` exists

- [ ] **Step 6: Review the outputs**

Check:

```bash
cd /Users/xiwei/stock_research
sed -n '1,80p' outputs/research/mid_trend_soft_ownership_optimization_20260625/baseline_vs_variants.csv
sed -n '1,200p' outputs/research/mid_trend_soft_ownership_optimization_20260625/final_interpretation.md
```

Expected: the interpretation explicitly discusses exposure/cash effects, top-winner impact, suppressed-exit saved winners vs false holds, and whether partial-exit cash stayed in cash.

- [ ] **Step 7: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/mid_trend_soft_ownership_v1.py src/stock_research/cli.py tests/test_mid_trend_soft_ownership_v1.py docs/research/mid_trend_soft_ownership_runbook.md
git commit -m "feat: implement mid trend soft ownership optimization"
```
