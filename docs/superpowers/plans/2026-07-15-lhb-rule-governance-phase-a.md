# LHB Rule Governance Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make delisting, near-limit-down, pump-risk, drawdown, and point-in-time price-limit decisions identical across LHB candidate selection, lifecycle/account backtests, EOD publication, and audit artifacts.

**Architecture:** Introduce a pure `lhb_eligibility` contract and a point-in-time price-limit resolver, then adapt each existing pipeline stage to consume the same immutable decision fields. Preserve rejected events in audit outputs while excluding them from rankings and trades. Rebuild asset status with same-day LHB name evidence and verify the resulting contract through cross-stage parity tests and a historical replay.

**Tech Stack:** Python 3, pandas, PostgreSQL, pytest, existing `stock_research` LHB lifecycle and strategy EOD publishers.

---

## File map

- Create `src/stock_research/lhb_eligibility.py`: price-limit resolution and versioned eligibility contract.
- Create `tests/test_lhb_eligibility.py`: table-driven contract and precedence tests.
- Modify `src/stock_research/core_data.py`: point-in-time ST fallback, correct Beijing thresholds, and status-source quality logic.
- Modify `tests/test_core_data.py`: SQL assertions for point-in-time status and board-specific thresholds.
- Modify `src/stock_research/lhb_data.py`: apply the contract before full-market ranking and retain rejected-event audits.
- Modify `tests/test_lhb_data.py`: delisting, near-limit-down, pump-boundary, and audit-preservation tests.
- Modify `src/stock_research/lhb_shortline_v1.py`: correct drawdown sign and enforce decisions before lifecycle/account entry.
- Expand `tests/test_lhb_shortline_v1.py`: candidate scoring, lifecycle, and account rejection tests.
- Modify `src/stock_research/dashboard/strategy_backtest_adapters.py`: use the shared contract constants and canonical drawdown calculation.
- Modify `src/stock_research/lhb_review_policy.py`: compatibility wrapper around the shared contract.
- Modify `src/stock_research/strategy_eod_publish.py`: consume upstream decisions and emit parity fields.
- Modify `src/stock_research/strategy_score_audit.py`: preserve contract version and decision reasons.
- Modify `tests/test_strategy_eod_publish.py` and `tests/test_strategy_score_audit.py`: publication and audit parity tests.
- Generate a new replay directory under `outputs/research/` through official commands; do not edit generated CSVs manually.

### Task 1: Implement the point-in-time price-limit resolver

**Files:**
- Create: `tests/test_lhb_eligibility.py`
- Create: `src/stock_research/lhb_eligibility.py`

- [ ] **Step 1: Write failing resolver tests**

```python
import pytest

from stock_research.lhb_eligibility import resolve_price_limit_state


@pytest.mark.parametrize(
    ("ts_code", "same_day_name", "pct_chg", "expected_regime", "expected_threshold"),
    [
        ("001399.SZ", "惠科股份", -9.5, "main_board", -9.5),
        ("000078.SZ", "ST海王", -4.8, "st", -4.8),
        ("300001.SZ", "特锐德", -19.0, "chinext", -19.0),
        ("688001.SH", "华兴源创", -19.0, "star", -19.0),
        ("920001.BJ", "北交样本", -29.0, "beijing", -29.0),
    ],
)
def test_resolve_price_limit_state_uses_same_day_regime(
    ts_code, same_day_name, pct_chg, expected_regime, expected_threshold
):
    state = resolve_price_limit_state(
        trade_date="2026-07-14",
        ts_code=ts_code,
        same_day_name=same_day_name,
        current_name="当前名称不应决定历史状态",
        pct_chg=pct_chg,
        stored_is_st=None,
        stored_status_quality="untrusted_all_false",
        list_date="2020-01-01",
    )
    assert state.regime == expected_regime
    assert state.near_limit_down_threshold == expected_threshold
    assert state.status_source == "same_day_lhb_name"


def test_resolve_price_limit_state_marks_missing_price_change_unknown():
    state = resolve_price_limit_state(
        trade_date="2026-07-14",
        ts_code="001399.SZ",
        same_day_name="惠科股份",
        current_name="惠科股份",
        pct_chg=None,
        stored_is_st=False,
        stored_status_quality="trusted",
        list_date="2020-01-01",
    )
    assert state.data_quality_status == "pct_chg_missing"
    assert state.near_limit_down is False
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `rtk .venv/bin/pytest -q tests/test_lhb_eligibility.py`

Expected: collection fails because `stock_research.lhb_eligibility` does not exist.

- [ ] **Step 3: Implement the resolver and immutable result type**

Implement these public interfaces:

```python
LHB_ELIGIBILITY_CONTRACT_VERSION = "lhb_eligibility_v2"

@dataclass(frozen=True)
class PriceLimitState:
    regime: str
    near_limit_down_threshold: float | None
    near_limit_down: bool
    is_st: bool | None
    status_source: str
    data_quality_status: str

def resolve_price_limit_state(
    *,
    trade_date: str,
    ts_code: str,
    same_day_name: object,
    current_name: object,
    pct_chg: object,
    stored_is_st: object,
    stored_status_quality: str,
    list_date: object,
) -> PriceLimitState:
    name = normalize_same_day_name(same_day_name)
    is_st, source = resolve_point_in_time_st(
        same_day_name=name,
        stored_is_st=stored_is_st,
        stored_status_quality=stored_status_quality,
    )
    regime, threshold = regime_and_threshold(ts_code=ts_code, is_st=is_st, trade_date=trade_date, list_date=list_date)
    change = optional_float(pct_chg)
    quality = "complete" if change is not None and threshold is not None else "pct_chg_missing"
    return PriceLimitState(
        regime=regime,
        near_limit_down_threshold=threshold,
        near_limit_down=bool(change is not None and threshold is not None and change <= threshold),
        is_st=is_st,
        status_source=source,
        data_quality_status=quality,
    )
```

The resolver must prefer same-day names, use `stored_is_st` only when quality is `trusted`, classify Beijing at -29.0%, and return a distinct no-limit regime for the first five trading days when reliable listing-age information proves that state. Missing evidence returns an explicit quality code rather than guessing.

- [ ] **Step 4: Run resolver tests**

Run: `rtk .venv/bin/pytest -q tests/test_lhb_eligibility.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
rtk git add src/stock_research/lhb_eligibility.py tests/test_lhb_eligibility.py
rtk git commit -m "feat: add point-in-time LHB price-limit resolver"
```

### Task 2: Implement the shared eligibility contract

**Files:**
- Modify: `tests/test_lhb_eligibility.py`
- Modify: `src/stock_research/lhb_eligibility.py`

- [ ] **Step 1: Add failing contract and precedence tests**

```python
from stock_research.lhb_eligibility import PriceLimitState, evaluate_lhb_eligibility


def main_board_state(*, pct_chg: float) -> PriceLimitState:
    return PriceLimitState(
        regime="main_board",
        near_limit_down_threshold=-9.5,
        near_limit_down=pct_chg <= -9.5,
        is_st=False,
        status_source="same_day_lhb_name",
        data_quality_status="complete",
    )


def test_delisting_is_hard_reject_and_wins_over_other_rules():
    decision = evaluate_lhb_eligibility(
        trade_date="2026-06-26",
        ts_code="000004.SZ",
        lhb_reason="退市整理期",
        price_limit_state=main_board_state(pct_chg=-10.0),
        pump_risk=0.95,
        high_to_close_drawdown=0.12,
        institution_net_buy=None,
    )
    assert decision.eligibility_status == "hard_reject"
    assert decision.top5_eligible is False
    assert decision.backtest_entry_eligible is False
    assert decision.reason_codes[0] == "delisting_period"


@pytest.mark.parametrize(
    ("pump", "status", "top5", "warning"),
    [
        (0.7499, "eligible", True, ""),
        (0.75, "eligible", True, "high_elasticity_pump_risk"),
        (0.8999, "eligible", True, "high_elasticity_pump_risk"),
        (0.90, "hard_reject", False, "extreme_one_day_pump_risk"),
    ],
)
def test_pump_boundaries_are_shared(pump, status, top5, warning):
    decision = evaluate_lhb_eligibility(
        trade_date="2026-07-14",
        ts_code="000001.SZ",
        lhb_reason="日涨幅偏离值达到7%的前5只证券",
        price_limit_state=main_board_state(pct_chg=1.0),
        pump_risk=pump,
        high_to_close_drawdown=0.01,
        institution_net_buy=1.0,
    )
    assert decision.eligibility_status == status
    assert decision.top5_eligible is top5
    assert (warning in decision.warning_codes or warning in decision.reason_codes) if warning else not decision.warning_codes


def test_near_limit_down_is_research_only():
    decision = evaluate_lhb_eligibility(
        trade_date="2026-07-14",
        ts_code="001399.SZ",
        lhb_reason="日跌幅偏离值达到7%的前5只证券",
        price_limit_state=main_board_state(pct_chg=-9.991),
        pump_risk=0.30,
        high_to_close_drawdown=0.02,
        institution_net_buy=None,
    )
    assert decision.eligibility_status == "risk_watch"
    assert decision.top5_eligible is False
    assert decision.backtest_entry_eligible is False
    assert "near_limit_down_followthrough_risk" in decision.reason_codes
    assert "institution_activity_unknown" in decision.warning_codes
```

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk .venv/bin/pytest -q tests/test_lhb_eligibility.py`

Expected: FAIL because `evaluate_lhb_eligibility` and `EligibilityDecision` are absent.

- [ ] **Step 3: Implement contract types and precedence**

```python
@dataclass(frozen=True)
class EligibilityDecision:
    eligibility_status: str
    top5_eligible: bool
    backtest_entry_eligible: bool
    reason_codes: tuple[str, ...]
    reason_texts: tuple[str, ...]
    warning_codes: tuple[str, ...]
    price_limit_regime: str
    near_limit_down_threshold: float | None
    data_quality_status: str
    contract_version: str = LHB_ELIGIBILITY_CONTRACT_VERSION

def evaluate_lhb_eligibility(
    *,
    trade_date: str,
    ts_code: str,
    lhb_reason: object,
    price_limit_state: PriceLimitState,
    pump_risk: object,
    high_to_close_drawdown: object,
    institution_net_buy: object,
) -> EligibilityDecision:
    reason = str(lhb_reason or "")
    warnings = []
    if institution_net_buy is None:
        warnings.append("institution_activity_unknown")
    if "退市" in reason:
        return EligibilityDecision(
            "hard_reject", False, False, ("delisting_period",),
            ("证券处于退市整理阶段",), tuple(warnings),
            price_limit_state.regime, price_limit_state.near_limit_down_threshold,
            price_limit_state.data_quality_status,
        )
    if price_limit_state.data_quality_status != "complete":
        return EligibilityDecision(
            "risk_watch", False, False, (price_limit_state.data_quality_status,),
            ("涨跌停制度数据不完整",), tuple(warnings),
            price_limit_state.regime, price_limit_state.near_limit_down_threshold,
            price_limit_state.data_quality_status,
        )
    if price_limit_state.near_limit_down:
        return EligibilityDecision(
            "risk_watch", False, False, ("near_limit_down_followthrough_risk",),
            ("接近跌停，禁止进入跟随和回测交易",), tuple(warnings),
            price_limit_state.regime, price_limit_state.near_limit_down_threshold,
            price_limit_state.data_quality_status,
        )
    pump = optional_float(pump_risk)
    if pump is None:
        return EligibilityDecision(
            "risk_watch", False, False, ("pump_risk_missing",),
            ("一日游风险数据缺失",), tuple(warnings),
            price_limit_state.regime, price_limit_state.near_limit_down_threshold,
            "pump_risk_missing",
        )
    if pump >= 0.90:
        return EligibilityDecision(
            "hard_reject", False, False, ("extreme_one_day_pump_risk",),
            ("一日游风险达到硬拒绝阈值",), tuple(warnings),
            price_limit_state.regime, price_limit_state.near_limit_down_threshold,
            price_limit_state.data_quality_status,
        )
    if pump >= 0.75:
        warnings.append("high_elasticity_pump_risk")
    drawdown = optional_float(high_to_close_drawdown)
    if drawdown is not None and drawdown >= 0.08:
        warnings.append("large_high_to_close_drawdown")
    return EligibilityDecision(
        "eligible", True, True, (), (), tuple(warnings),
        price_limit_state.regime, price_limit_state.near_limit_down_threshold,
        price_limit_state.data_quality_status,
    )
```

Implement delisting, missing critical price data, near-limit-down, pump boundaries, positive drawdown warnings, and institution-unknown warnings in the exact precedence defined by the spec.

- [ ] **Step 4: Run contract tests**

Run: `rtk .venv/bin/pytest -q tests/test_lhb_eligibility.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
rtk git add src/stock_research/lhb_eligibility.py tests/test_lhb_eligibility.py
rtk git commit -m "feat: add shared LHB eligibility contract"
```

### Task 3: Repair point-in-time asset status generation

**Files:**
- Modify: `tests/test_core_data.py`
- Modify: `src/stock_research/core_data.py:452-520`

- [ ] **Step 1: Write failing SQL contract tests**

Extend `test_build_asset_status_daily_uses_point_in_time_daily_bars` to assert:

```python
assert "market.lhb_top_list_daily" in sql
assert "same_day_lhb_name" in sql
assert "29.8" in sql
assert "WHEN resolved_is_st THEN 4.8" in sql
assert "status_quality" in sql
```

Add a test proving same-day LHB ST evidence takes precedence over `b.is_st = false`.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `rtk .venv/bin/pytest -q tests/test_core_data.py -k asset_status_daily`

Expected: FAIL because the SQL uses `b.is_st` directly and assigns Beijing 19.8%.

- [ ] **Step 3: Implement point-in-time status CTEs**

Build SQL CTEs for:

```sql
same_day_lhb AS (
  SELECT trade_date, ts_code, max(NULLIF(name, '')) AS same_day_lhb_name
  FROM market.lhb_top_list_daily
  GROUP BY trade_date, ts_code
),
resolved AS (
  SELECT b.*,
         COALESCE(same_day_lhb_name ~* '^(\\*?ST|S\\*ST)', b.is_st) AS resolved_is_st,
         CASE
           WHEN same_day_lhb_name IS NOT NULL THEN 'same_day_lhb_name'
           WHEN b.is_st THEN 'daily_bar'
           ELSE 'daily_bar_unverified_false'
         END AS status_quality
  FROM market_daily_bar b
  LEFT JOIN core.asset_master a ON a.asset_id = b.asset_id
  LEFT JOIN same_day_lhb l ON l.trade_date = b.trade_date AND l.ts_code = a.ts_code
)
```

Use 4.8, 9.8, 19.8, and 29.8 operational thresholds for status-table flags and prices. Append the quality source to the existing `source` text because the current table has no separate quality column. Do not change unrelated schema in Phase A.

- [ ] **Step 4: Run core-data tests**

Run: `rtk .venv/bin/pytest -q tests/test_core_data.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
rtk git add src/stock_research/core_data.py tests/test_core_data.py
rtk git commit -m "fix: build point-in-time LHB asset status"
```

### Task 4: Apply the contract before full-market ranking

**Files:**
- Modify: `tests/test_lhb_data.py`
- Modify: `src/stock_research/lhb_data.py:7236-7335`

- [ ] **Step 1: Add failing candidate-pool tests**

Create a compact frame containing ordinary, delisting, near-limit-down, `000080.SZ` with pump 0.80, and `000090.SZ` with pump 0.90 rows. Assert:

```python
result = lhb_data.build_lhb_full_market_pool_backtest_v1(
    lhb_features=lhb_features,
    daily_bars=daily_bars,
    start_date="2026-07-14",
    end_date="2026-07-14",
    top_n_values=[10],
    output_dir=tmp_path,
    pool_mode="raw_lhb_positive",
)
selected = result["selected_trades"]
rejected = result["rejected_events"]

assert "000004.SZ" not in set(selected["ts_code"])
assert "001399.SZ" not in set(selected["ts_code"])
assert "000080.SZ" in set(selected["ts_code"])
assert "000090.SZ" not in set(selected["ts_code"])
assert set(rejected["eligibility_status"]) == {"hard_reject", "risk_watch"}
```

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk .venv/bin/pytest -q tests/test_lhb_data.py -k 'eligibility or delisting or near_limit_down'`

Expected: FAIL because the pool only applies the legacy positive/pump filter and returns no rejected audit.

- [ ] **Step 3: Enrich candidates and evaluate decisions**

Before `_filter_lhb_full_market_pool`, join or carry same-day name, reason, pct change, board, list date, and status fields. Apply the shared contract row by row through a focused helper that expands the decision into columns:

```python
eligibility_status
top5_eligible
backtest_entry_eligible
eligibility_reason_codes
eligibility_warning_codes
price_limit_regime
near_limit_down_threshold
eligibility_contract_version
```

Rank only `backtest_entry_eligible == true` rows. Return and write `lhb_full_market_pool_rejected_events_v2.csv` for rejected/risk-watch rows.

- [ ] **Step 4: Remove the legacy 0.90 implementation from pool filtering**

`_filter_lhb_full_market_pool` may keep positive-capital structural filters, but pump hard thresholds and safety rules must come only from the contract.

- [ ] **Step 5: Run LHB data tests**

Run: `rtk .venv/bin/pytest -q tests/test_lhb_data.py -k 'full_market_pool or eligibility or delisting or near_limit_down'`

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
rtk git add src/stock_research/lhb_data.py tests/test_lhb_data.py
rtk git commit -m "fix: gate LHB candidates before ranking"
```

### Task 5: Correct drawdown scoring and unify adapter thresholds

**Files:**
- Modify: `tests/test_lhb_shortline_v1.py`
- Modify: `src/stock_research/lhb_shortline_v1.py:800-845`
- Modify: `src/stock_research/dashboard/strategy_backtest_adapters.py:704-750`

- [ ] **Step 1: Add a failing positive-drawdown score test**

```python
def test_candidate_score_penalizes_positive_high_to_close_drawdown():
    base = candidate_frame(high_to_close_drawdown=0.0)
    faded = candidate_frame(high_to_close_drawdown=0.10)
    base_score = lhb_shortline_v1.build_lhb_shortline_v1_candidates(base.lhb, base.tech, candidate_pool_n=10)
    faded_score = lhb_shortline_v1.build_lhb_shortline_v1_candidates(faded.lhb, faded.tech, candidate_pool_n=10)
    assert faded_score.iloc[0]["score_total"] == pytest.approx(base_score.iloc[0]["score_total"] - 4.0)
```

- [ ] **Step 2: Run test and verify RED**

Run: `rtk .venv/bin/pytest -q tests/test_lhb_shortline_v1.py -k drawdown`

Expected: FAIL because positive drawdown currently receives no penalty.

- [ ] **Step 3: Fix the sign and use shared pump constants**

Replace the incorrect expression with:

```python
drawdown = _optional_num(frame, "high_to_close_drawdown").clip(0, 1)
```

Import contract constants for warning and hard-reject pump boundaries. Remove independent `< 0.75` hard eligibility from the dashboard adapter; eligibility comes from contract decisions while the score retains the continuous pump penalty.

- [ ] **Step 4: Run scorer and adapter tests**

Run: `rtk .venv/bin/pytest -q tests/test_lhb_shortline_v1.py tests/test_lhb_review_policy.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

```bash
rtk git add src/stock_research/lhb_shortline_v1.py src/stock_research/dashboard/strategy_backtest_adapters.py tests/test_lhb_shortline_v1.py
rtk git commit -m "fix: unify LHB drawdown and pump scoring"
```

### Task 6: Enforce eligibility in lifecycle and account stages

**Files:**
- Modify: `tests/test_lhb_shortline_v1.py`
- Modify: `src/stock_research/lhb_shortline_v1.py:1607-1810`

- [ ] **Step 1: Write failing lifecycle parity tests**

Create lifecycle input with one eligible row, one `risk_watch`, and one `hard_reject`. Assert:

```python
assert set(result.candidates["ts_code"]) == {"ELIGIBLE.SZ"}
assert not set(account_trades.loc[account_trades.account_trade_status.eq("filled"), "ts_code"]).intersection(
    {"RISK.SZ", "REJECT.SZ"}
)
```

Add an invariant test that fails when a downstream row lacks or contradicts `eligibility_contract_version`.

- [ ] **Step 2: Run lifecycle tests and verify RED**

Run: `rtk .venv/bin/pytest -q tests/test_lhb_shortline_v1.py -k 'eligibility or rejected or parity'`

Expected: FAIL because lifecycle/account code does not consume contract decisions.

- [ ] **Step 3: Propagate and assert decision columns**

Carry contract fields through selected trades, phase12A decisions, lifecycle trades, phase18C candidates, and account trades. Filter before entry construction and add a defensive assertion immediately before account fills:

```python
invalid = trades[~trades["backtest_entry_eligible"].fillna(False).astype(bool)]
if not invalid.empty:
    raise ValueError("LHB eligibility parity violation before account entry")
```

Rejected events remain in the separate audit artifact, not in the account candidate frame.

Write `lhb_eligibility_parity_audit_v2.csv` with one row per `trade_date + ts_code`, the decision observed at each pipeline stage, and `parity_status` equal to `match` or `mismatch`.

- [ ] **Step 4: Run lifecycle tests**

Run: `rtk .venv/bin/pytest -q tests/test_lhb_shortline_v1.py tests/test_lhb_data.py -k 'lhb or eligibility or lifecycle or account'`

Expected: PASS.

- [ ] **Step 5: Commit Task 6**

```bash
rtk git add src/stock_research/lhb_shortline_v1.py src/stock_research/lhb_data.py tests/test_lhb_shortline_v1.py tests/test_lhb_data.py
rtk git commit -m "fix: enforce LHB eligibility through account entry"
```

### Task 7: Make EOD publication consume upstream decisions

**Files:**
- Modify: `tests/test_strategy_eod_publish.py`
- Modify: `tests/test_strategy_score_audit.py`
- Modify: `src/stock_research/lhb_review_policy.py`
- Modify: `src/stock_research/strategy_eod_publish.py:754-950`
- Modify: `src/stock_research/strategy_score_audit.py`

- [ ] **Step 1: Add failing publication parity tests**

Assert that a candidate carrying `lhb_eligibility_v2` fields is published unchanged, and that a contradictory recomputation raises a parity error rather than silently changing the decision.

```python
assert row["eligibility_contract_version"] == "lhb_eligibility_v2"
assert row["eligibility_status"] == "risk_watch"
assert row["top5_eligible"] is False
assert row["eligibility_reason_codes"] == ["near_limit_down_followthrough_risk"]
```

- [ ] **Step 2: Run tests and verify RED**

Run: `rtk .venv/bin/pytest -q tests/test_strategy_eod_publish.py tests/test_strategy_score_audit.py -k 'eligibility or parity or limit_down'`

Expected: FAIL because EOD currently calls its own policy and does not emit contract version/reason arrays.

- [ ] **Step 3: Convert the old policy into a compatibility adapter**

`lhb_review_policy.apply_lhb_top5_gate` may support legacy callers by invoking the new contract only when upstream fields are absent. Official fresh LHB results must already contain contract decisions. Publication checks parity, ranks only upstream `top5_eligible` rows, and preserves risk-watch events.

- [ ] **Step 4: Add audit fields**

Carry these fields through review CSV, combined review manifest, score audit, and Dashboard reader inputs:

```text
eligibility_status
top5_eligible
backtest_entry_eligible
eligibility_reason_codes
eligibility_warning_codes
eligibility_contract_version
price_limit_regime
near_limit_down_threshold
data_quality_status
```

- [ ] **Step 5: Run publication and audit tests**

Run: `rtk .venv/bin/pytest -q tests/test_strategy_eod_publish.py tests/test_strategy_score_audit.py tests/test_dashboard_review_queue.py`

Expected: PASS.

- [ ] **Step 6: Commit Task 7**

```bash
rtk git add src/stock_research/lhb_review_policy.py src/stock_research/strategy_eod_publish.py src/stock_research/strategy_score_audit.py tests/test_strategy_eod_publish.py tests/test_strategy_score_audit.py
rtk git commit -m "fix: publish upstream LHB eligibility decisions"
```

### Task 8: Run Phase A historical replay and parity audit

**Files:**
- Generated: new LHB run directory under `outputs/research/web_lhb_shortline_v1_runs/`
- Generated: `outputs/research/strategy_daily_eod/2026-07-14/` runtime artifacts
- Create: `docs/quant_system/2026-07-15-lhb-rule-governance-phase-a-completion.md`

- [ ] **Step 1: Run the focused regression suite**

```bash
rtk .venv/bin/pytest -q \
  tests/test_lhb_eligibility.py \
  tests/test_core_data.py \
  tests/test_lhb_data.py \
  tests/test_lhb_shortline_v1.py \
  tests/test_lhb_review_policy.py \
  tests/test_strategy_eod_publish.py \
  tests/test_strategy_score_audit.py \
  tests/test_dashboard_review_queue.py
```

Expected: all tests PASS.

- [ ] **Step 2: Rebuild asset status for the replay period**

```bash
rtk .venv/bin/python -c "from stock_research.core_data import build_asset_status_daily_for_service as run; run('2026-01-05','2026-07-14'); print('asset_status_rebuilt')"
```

Expected: `asset_status_rebuilt` and no SQL error.

- [ ] **Step 3: Run the official LHB fresh backtest**

Run:

```bash
rtk .venv/bin/python -c "from stock_research.lhb_shortline_v1 import run_lhb_shortline_v1_backtest_for_dashboard as run; result=run({'start_date':'2026-01-05','end_date':'2026-07-14','top_n':5,'risk_profile':'balanced','adjust_type':'hfq','output_dir':'outputs/research/lhb_rule_governance_phase_a_20260105_20260714'}); print(result['summary']); print(result['artifacts'])"
```

Do not overwrite the baseline run.

Expected: new candidates, rejected-event audit, lifecycle, account, summary, and parity artifacts.

- [ ] **Step 4: Assert the safety invariants**

Run:

```bash
rtk .venv/bin/python -c "from pathlib import Path; import pandas as pd; root=Path('outputs/research/lhb_rule_governance_phase_a_20260105_20260714'); account=pd.read_csv(root/'lhb_phase18c_account_trades_v1.csv',low_memory=False); rejected=pd.read_csv(root/'lhb_full_market_pool_rejected_events_v2.csv',low_memory=False); parity=pd.read_csv(root/'lhb_eligibility_parity_audit_v2.csv',low_memory=False); filled=account[account.account_trade_status.eq('filled')]; rejected_keys=set(zip(rejected.trade_date.astype(str),rejected.ts_code.astype(str))); filled_keys=set(zip(filled.trade_date.astype(str),filled.ts_code.astype(str))); assert not rejected_keys.intersection(filled_keys); assert rejected.eligibility_reason_codes.astype(str).str.contains('delisting_period').any(); assert rejected.eligibility_reason_codes.astype(str).str.contains('near_limit_down_followthrough_risk').any(); assert parity.parity_status.eq('match').all(); assert parity.eligibility_contract_version.eq('lhb_eligibility_v2').all(); print({'filled_rejected_overlap':0,'parity_mismatches':0,'contract_missing':0,'rejected_rows':len(rejected)})"
```

Expected: `filled_rejected_overlap`, `parity_mismatches`, and `contract_missing` are all zero.

Report baseline versus v2 final equity, total return, maximum drawdown, trade count, and the PnL removed by delisting and limit-down exclusions.

- [ ] **Step 5: Republish 2026-07-14**

```bash
rtk .venv/bin/python -m stock_research.strategy_eod_publish \
  --trade-date 2026-07-14 \
  --output-root outputs
```

Expected: exit code 0, LHB contract version `lhb_eligibility_v2`, 惠科股份 retained as an auditable risk-watch event, and zero parity anomalies.

- [ ] **Step 6: Run final checks and document Phase A**

Run:

```bash
rtk git diff --check -- src tests docs
rtk git status --short
```

Preserve the three pre-existing `tech_bottleneck_review_universe_frontend_*` modifications. Record exact commands, test counts, replay paths, and performance deltas in the completion document.

- [ ] **Step 7: Commit the completion record only if created**

```bash
rtk git add docs/quant_system/2026-07-15-lhb-rule-governance-phase-a-completion.md
rtk git commit -m "docs: record LHB rule governance phase A replay"
```
