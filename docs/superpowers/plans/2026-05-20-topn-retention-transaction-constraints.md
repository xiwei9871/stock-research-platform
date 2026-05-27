# TopN Retention Transaction Constraints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify execution-time transaction constraints across `vectorized_topn_backtest.py` and `retention_backtest.py` so both backtests apply the same suspended/limit/cost semantics.

**Architecture:** Introduce a small shared `backtest_constraints.py` module for executable-buy/sell checks and one-way cost math, then wire it into the two existing backtest engines without rewriting their higher-level strategy logic. Keep configuration backwards-compatible by adding defaulted execution-constraint fields to the existing config dataclasses, and only add CLI flags where a direct CLI already exists (`retention-backtest`).

**Tech Stack:** Python 3.14, pandas, existing backtest modules under `src/stock_research/`, existing CLI under `src/stock_research/cli.py`, pytest.

---

### Task 1: Add Shared Execution-Constraint Primitives

**Files:**
- Create: `src/stock_research/backtest_constraints.py`
- Create: `tests/test_backtest_constraints.py`

- [ ] **Step 1: Write the failing shared-constraint tests**

```python
from stock_research.backtest_constraints import (
    BacktestExecutionConstraints,
    can_close_long,
    can_open_long,
    one_way_cost_rate,
)


def test_can_open_long_blocks_suspended_and_limit_up_bars():
    constraints = BacktestExecutionConstraints()

    allowed, reason = can_open_long(
        {
            "trade_status": "1",
            "is_suspended": True,
            "is_limit_up": False,
            "amount": 100_000_000.0,
        },
        constraints,
    )
    assert allowed is False
    assert reason == "suspended"

    allowed, reason = can_open_long(
        {
            "trade_status": "1",
            "is_suspended": False,
            "is_limit_up": True,
            "amount": 100_000_000.0,
        },
        constraints,
    )
    assert allowed is False
    assert reason == "limit_up"
```

```python
def test_can_close_long_blocks_limit_down_when_enabled():
    constraints = BacktestExecutionConstraints(block_limit_down_sell=True)

    allowed, reason = can_close_long(
        {
            "trade_status": "1",
            "is_suspended": False,
            "is_limit_down": True,
            "amount": 100_000_000.0,
        },
        constraints,
    )

    assert allowed is False
    assert reason == "limit_down"
```

```python
def test_one_way_cost_rate_adds_commission_stamp_duty_and_slippage():
    constraints = BacktestExecutionConstraints(
        commission_bps=5.0,
        stamp_duty_bps=10.0,
        slippage_bps=8.0,
    )

    assert one_way_cost_rate("buy", constraints) == 0.0013
    assert one_way_cost_rate("sell", constraints) == 0.0023
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `.venv/bin/pytest tests/test_backtest_constraints.py -q`

Expected: FAIL because the shared constraint module does not exist yet.

- [ ] **Step 3: Implement the shared constraint dataclass and helper functions**

```python
# src/stock_research/backtest_constraints.py
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BacktestExecutionConstraints:
    commission_bps: float = 0.0
    stamp_duty_bps: float = 0.0
    slippage_bps: float = 0.0
    min_amount: float | None = None
    block_suspended: bool = True
    block_limit_up_buy: bool = True
    block_limit_down_sell: bool = True


def can_open_long(bar: dict[str, Any], constraints: BacktestExecutionConstraints) -> tuple[bool, str | None]:
    if constraints.block_suspended and (
        bool(bar.get("is_suspended"))
        or str(bar.get("trade_status") or "1") != "1"
    ):
        return False, "suspended"
    if constraints.block_limit_up_buy and bool(bar.get("is_limit_up")):
        return False, "limit_up"
    if constraints.min_amount is not None and float(bar.get("amount") or 0.0) < float(constraints.min_amount):
        return False, "low_amount"
    return True, None


def can_close_long(bar: dict[str, Any], constraints: BacktestExecutionConstraints) -> tuple[bool, str | None]:
    if constraints.block_suspended and (
        bool(bar.get("is_suspended"))
        or str(bar.get("trade_status") or "1") != "1"
    ):
        return False, "suspended"
    if constraints.block_limit_down_sell and bool(bar.get("is_limit_down")):
        return False, "limit_down"
    if constraints.min_amount is not None and float(bar.get("amount") or 0.0) < float(constraints.min_amount):
        return False, "low_amount"
    return True, None


def one_way_cost_rate(side: str, constraints: BacktestExecutionConstraints) -> float:
    if side not in {"buy", "sell"}:
        raise ValueError(f"unsupported side: {side}")
    stamp_duty = constraints.stamp_duty_bps if side == "sell" else 0.0
    return (constraints.commission_bps + constraints.slippage_bps + stamp_duty) / 10000.0
```

Implementation notes:
- Treat `trade_status != "1"` as non-tradable when `block_suspended=True`.
- `min_amount` should reject both buys and sells when the execution-day amount is below threshold.
- `stamp_duty_bps` applies only on `sell`.
- Keep helper inputs as plain `dict[str, Any]` so both vectorized and retention code can call them without extra wrappers.

- [ ] **Step 4: Run the tests and verify they pass**

Run: `.venv/bin/pytest tests/test_backtest_constraints.py -q`

Expected: PASS with deterministic cost math and skip reasons.

- [ ] **Step 5: Commit the shared constraint module**

```bash
git add tests/test_backtest_constraints.py src/stock_research/backtest_constraints.py
git commit -m "feat: add shared backtest execution constraints"
```

### Task 2: Wire Shared Constraints Into Vectorized TopN

**Files:**
- Modify: `src/stock_research/vectorized_topn_backtest.py`
- Test: `tests/test_vectorized_topn_backtest.py`
- Reuse: `src/stock_research/strategy_lifecycle.py`
- Reuse: `src/stock_research/industry_focus_score.py`
- Reuse: `src/stock_research/industry_focus_v2.py`
- Reuse: `src/stock_research/industry_regime_gated_backtest.py`
- Reuse: `src/stock_research/industry_exposure_risk_control.py`

- [ ] **Step 1: Write the failing Vectorized TopN tests**

```python
def test_run_vectorized_topn_backtest_skips_limit_up_buy_and_keeps_cash():
    scores = _scores(
        [
            ("2026-01-01", "A", 1, 90.0),
            ("2026-01-01", "B", 2, 80.0),
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "open": 10.0, "close": 10.0, "amount": 100000000.0, "trade_status": "1", "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
            {"trade_date": "2026-01-01", "asset_id": "B", "open": 20.0, "close": 20.0, "amount": 100000000.0, "trade_status": "1", "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
            {"trade_date": "2026-01-02", "asset_id": "A", "open": 11.0, "close": 11.0, "amount": 100000000.0, "trade_status": "1", "is_limit_up": True, "is_limit_down": False, "is_suspended": False},
            {"trade_date": "2026-01-02", "asset_id": "B", "open": 20.0, "close": 20.0, "amount": 100000000.0, "trade_status": "1", "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
            {"trade_date": "2026-01-03", "asset_id": "A", "open": 11.0, "close": 11.0, "amount": 100000000.0, "trade_status": "1", "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
            {"trade_date": "2026-01-03", "asset_id": "B", "open": 21.0, "close": 21.0, "amount": 100000000.0, "trade_status": "1", "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
        ]
    )
    config = VectorizedTopNConfig(
        start_date="2026-01-01",
        end_date="2026-01-03",
        top_n=2,
        execution_constraints=BacktestExecutionConstraints(),
    )

    result = run_vectorized_topn_backtest(scores, prices, config)

    assert list(result.trades["skip_reason"].dropna()) == ["limit_up"]
    assert result.equity_curve.iloc[0]["holdings_count"] == 1
```

```python
def test_run_vectorized_topn_backtest_applies_full_one_way_costs():
    scores = _scores(
        [
            ("2026-01-01", "A", 1, 90.0),
            ("2026-01-02", "B", 1, 95.0),
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2026-01-01", "asset_id": "A", "open": 10.0, "close": 10.0, "amount": 100000000.0, "trade_status": "1", "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
            {"trade_date": "2026-01-02", "asset_id": "A", "open": 11.0, "close": 11.0, "amount": 100000000.0, "trade_status": "1", "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
            {"trade_date": "2026-01-02", "asset_id": "B", "open": 20.0, "close": 20.0, "amount": 100000000.0, "trade_status": "1", "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
            {"trade_date": "2026-01-03", "asset_id": "A", "open": 11.0, "close": 11.0, "amount": 100000000.0, "trade_status": "1", "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
            {"trade_date": "2026-01-03", "asset_id": "B", "open": 21.0, "close": 21.0, "amount": 100000000.0, "trade_status": "1", "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
        ]
    )
    config = VectorizedTopNConfig(
        start_date="2026-01-01",
        end_date="2026-01-03",
        top_n=1,
        execution_constraints=BacktestExecutionConstraints(
            commission_bps=5.0,
            stamp_duty_bps=10.0,
            slippage_bps=5.0,
        ),
    )

    result = run_vectorized_topn_backtest(scores, prices, config)

    assert result.trades["transaction_cost"].sum() > 0
    assert result.equity_curve["transaction_cost"].sum() > 0
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py -q`

Expected: FAIL because the current vectorized engine has no shared execution-constraint support, no execution-day skip reasons, and no full one-way cost breakdown.

- [ ] **Step 3: Implement execution-day rebalances and shared cost handling in the Vectorized TopN engine**

```python
# src/stock_research/vectorized_topn_backtest.py
from dataclasses import dataclass, field

from stock_research.backtest_constraints import (
    BacktestExecutionConstraints,
    can_close_long,
    can_open_long,
    one_way_cost_rate,
)


@dataclass(frozen=True)
class VectorizedTopNConfig:
    start_date: object
    end_date: object
    top_n: int = 20
    rebalance_frequency: str = "daily"
    transaction_cost_bps: float = 0.0
    max_positions: int | None = None
    execution_constraints: BacktestExecutionConstraints = field(
        default_factory=BacktestExecutionConstraints
    )
```

```python
TRADE_COLUMNS = [
    "signal_date",
    "execution_date",
    "asset_id",
    "side",
    "previous_weight",
    "target_weight",
    "executed_weight",
    "delta_weight",
    "turnover_contribution",
    "transaction_cost",
    "skip_reason",
]
```

Implementation notes:
- Extend normalized price inputs to keep `open`, `close`, `amount`, `trade_status`, `is_limit_up`, `is_limit_down`, and `is_suspended`.
- Compute target weights on the signal date, but apply them on the next trade date using execution-day bars.
- Track `cash_weight` explicitly so blocked buys leave idle cash instead of forcing weights to sum to one.
- When a sell is blocked by `limit_down` or `suspended`, keep the position weight until a later executable date.
- Keep `transaction_cost_bps` as a backward-compatible alias. Convert it into `commission_bps` only when the new nested constraint fields are left at defaults, then deprecate the alias in comments/tests rather than silently removing it.
- Do not change existing callers in `industry_*` or `strategy_lifecycle.py`; rely on the defaulted `execution_constraints` field to preserve old construction sites.

- [ ] **Step 4: Run the tests and verify they pass**

Run: `.venv/bin/pytest tests/test_vectorized_topn_backtest.py tests/test_strategy_lifecycle.py tests/test_research_workflow.py -q`

Expected: PASS with execution-day trade rows, skipped buys/sells, and costed net returns.

- [ ] **Step 5: Commit the Vectorized TopN integration**

```bash
git add tests/test_vectorized_topn_backtest.py tests/test_strategy_lifecycle.py tests/test_research_workflow.py src/stock_research/vectorized_topn_backtest.py
git commit -m "feat: unify vectorized topn execution constraints"
```

### Task 3: Wire Shared Constraints Into Retention And Expose CLI Flags

**Files:**
- Modify: `src/stock_research/retention_backtest.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_retention_backtest.py`
- Test: `tests/test_factor_cli.py`

- [ ] **Step 1: Write the failing retention and CLI tests**

```python
def test_retention_skips_limit_up_buy_via_shared_constraints():
    feature_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_5d", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_20d", "feature_value": 0.15},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_60d", "feature_value": 0.10},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "amount_20d_avg", "feature_value": 100000000.0},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "volatility_20d", "feature_value": 0.02},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ma20_deviation", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "max_drawdown_20d", "feature_value": -0.03},
        ]
    )
    bar_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-05", "open": 10.0, "close": 10.0, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": True, "is_limit_down": False, "is_suspended": False},
            {"asset_id": "A", "trade_date": "2026-01-06", "open": 10.5, "close": 10.5, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
        ]
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-06",
        max_positions=1,
        execution_constraints=BacktestExecutionConstraints(),
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    skipped = result.trades[result.trades["skip_reason"] == "limit_up"]
    assert len(skipped) == 1
```

```python
def test_retention_rolls_limit_down_sell_until_executable():
    feature_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_5d", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_20d", "feature_value": 0.15},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ret_60d", "feature_value": 0.10},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "amount_20d_avg", "feature_value": 100000000.0},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "volatility_20d", "feature_value": 0.02},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "ma20_deviation", "feature_value": 0.05},
            {"asset_id": "A", "trade_date": "2026-01-02", "feature_name": "max_drawdown_20d", "feature_value": -0.03},
            {"asset_id": "B", "trade_date": "2026-01-06", "feature_name": "ret_5d", "feature_value": 0.01},
            {"asset_id": "B", "trade_date": "2026-01-06", "feature_name": "ret_20d", "feature_value": 0.02},
            {"asset_id": "B", "trade_date": "2026-01-06", "feature_name": "ret_60d", "feature_value": 0.03},
            {"asset_id": "B", "trade_date": "2026-01-06", "feature_name": "amount_20d_avg", "feature_value": 100000000.0},
            {"asset_id": "B", "trade_date": "2026-01-06", "feature_name": "volatility_20d", "feature_value": 0.02},
            {"asset_id": "B", "trade_date": "2026-01-06", "feature_name": "ma20_deviation", "feature_value": 0.01},
            {"asset_id": "B", "trade_date": "2026-01-06", "feature_name": "max_drawdown_20d", "feature_value": -0.01},
        ]
    )
    bar_frame = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2026-01-06", "open": 10.0, "close": 10.0, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": False, "is_limit_down": True, "is_suspended": False},
            {"asset_id": "A", "trade_date": "2026-01-07", "open": 9.8, "close": 9.8, "amount": 100000000.0, "trade_status": "1", "is_st": False, "is_limit_up": False, "is_limit_down": False, "is_suspended": False},
        ]
    )
    config = RetentionConfig(
        start_date="2026-01-02",
        end_date="2026-01-07",
        max_positions=1,
        execution_constraints=BacktestExecutionConstraints(),
    )

    result = simulate_retention_config(feature_frame, bar_frame, config)

    closed = result.trades[result.trades["status"] == "closed"].iloc[0]
    assert closed["sell_date"] == "2026-01-07"
```

```python
def test_cli_accepts_retention_execution_constraint_flags():
    args = build_parser().parse_args(
        [
            "retention-backtest",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-01-31",
            "--commission-bps",
            "5",
            "--stamp-duty-bps",
            "10",
            "--slippage-bps",
            "8",
            "--min-amount",
            "30000000",
        ]
    )

    assert args.commission_bps == 5.0
    assert args.stamp_duty_bps == 10.0
    assert args.slippage_bps == 8.0
    assert args.min_amount == 30000000.0
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `.venv/bin/pytest tests/test_retention_backtest.py tests/test_factor_cli.py -q -k "limit_up or limit_down or retention_execution_constraint_flags"`

Expected: FAIL because `RetentionConfig` has no shared execution-constraint field and the retention CLI does not expose these flags.

- [ ] **Step 3: Implement shared constraint wiring in retention and add CLI flags**

```python
# src/stock_research/retention_backtest.py
from dataclasses import dataclass, field

from stock_research.backtest_constraints import (
    BacktestExecutionConstraints,
    can_close_long,
    can_open_long,
    one_way_cost_rate,
)


@dataclass(frozen=True)
class RetentionConfig:
    start_date: object
    end_date: object
    initial_cash: float = 500000.0
    max_positions: int = 5
    lot_size: int = 100
    strategy_id: str | None = None
    entry_top_n: int = 20
    observe_top_n: int = 20
    exit_confirm_days: int = 1
    ma20_exit: bool = False
    use_adjusted_score: bool = False
    hard_entry_filters: bool = False
    market_entry_filter: bool = False
    board_entry_filter: bool = False
    stop_loss_pct: float | None = None
    execution_constraints: BacktestExecutionConstraints = field(
        default_factory=BacktestExecutionConstraints
    )
```

```python
def _execute_pending_buy(
    current_date: str,
    pending_buy: dict[str, object],
    cash: float,
    positions: list[dict[str, object]],
    trade_rows: list[dict[str, object]],
    bars_by_date_asset: dict[tuple[str, str], dict[str, object]],
    config: RetentionConfig,
):
    allowed, skip_reason = can_open_long(execution_bar, config.execution_constraints)
    if not allowed:
        trade_rows.append(_skip_trade(pending_buy["selection"], current_date, config, skip_reason))
        return cash, True
    buy_cost_rate = one_way_cost_rate("buy", config.execution_constraints)
    net_cash = cash * (1.0 - buy_cost_rate)
    return _finalize_buy(net_cash, pending_buy, positions, trade_rows, current_date, bars_by_date_asset, config), True


def _execute_pending_sells(
    current_date: str,
    cash: float,
    positions: list[dict[str, object]],
    bars_by_date_asset: dict[tuple[str, str], dict[str, object]],
    config: RetentionConfig,
):
    allowed, skip_reason = can_close_long(execution_bar, config.execution_constraints)
    if not allowed:
        position["pending_sell_skip_reason"] = skip_reason
        return cash
    sell_cost_rate = one_way_cost_rate("sell", config.execution_constraints)
    proceeds = gross_proceeds * (1.0 - sell_cost_rate)
    return cash + proceeds
```

```python
# src/stock_research/cli.py
retention_backtest.add_argument("--commission-bps", type=float, default=0.0)
retention_backtest.add_argument("--stamp-duty-bps", type=float, default=0.0)
retention_backtest.add_argument("--slippage-bps", type=float, default=0.0)
retention_backtest.add_argument("--min-amount", type=float)
```

```python
elif args.command == "retention-backtest":
    retention_kwargs = {
        "execution_constraints": BacktestExecutionConstraints(
            commission_bps=args.commission_bps,
            stamp_duty_bps=args.stamp_duty_bps,
            slippage_bps=args.slippage_bps,
            min_amount=args.min_amount,
        ),
        "reports_dir": args.reports_dir,
        "variant": args.variant,
        "top_ks": args.top_ks,
    }
```

Implementation notes:
- Reuse shared skip reasons verbatim: `suspended`, `limit_up`, `limit_down`, `low_amount`.
- Apply `one_way_cost_rate("buy", config.execution_constraints)` to entry notional and `one_way_cost_rate("sell", config.execution_constraints)` to exit notional before calculating realized `return_value`.
- Preserve all existing retention rules (`stop_loss_pct`, `ma20_exit`, top20 exit) and only change the execution gate and cost accounting paths.
- Include execution constraints in retention run-card config so future reports are auditable.

- [ ] **Step 4: Run the tests and verify they pass**

Run: `.venv/bin/pytest tests/test_retention_backtest.py tests/test_factor_cli.py -q`

Expected: PASS with shared skip reasons and costed retention trades.

- [ ] **Step 5: Commit the retention integration**

```bash
git add tests/test_retention_backtest.py tests/test_factor_cli.py src/stock_research/retention_backtest.py src/stock_research/cli.py
git commit -m "feat: unify retention execution constraints"
```

### Task 4: Regression Sweep For Cross-Module Compatibility

**Files:**
- Reuse: `tests/test_strategy_lifecycle.py`
- Reuse: `tests/test_research_workflow.py`
- Reuse: `tests/test_performance_tearsheet.py`

- [ ] **Step 1: Run the integrated regression set**

Run: `.venv/bin/pytest tests/test_backtest_constraints.py tests/test_vectorized_topn_backtest.py tests/test_retention_backtest.py tests/test_strategy_lifecycle.py tests/test_research_workflow.py tests/test_performance_tearsheet.py tests/test_factor_cli.py -q`

Expected: PASS with no callsite breakage from the new defaulted config fields.

- [ ] **Step 2: Commit only if no further fixes are needed**

```bash
git status --short
```

Expected: clean working tree after the three focused commits above.
