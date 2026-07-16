# LHB V1 Safe Top5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the legacy LHB Top10 research/lifecycle path, select the final Top5 in Phase18C, block limit-down account entries without rank-6 refill, and keep ST candidates with an explicit high-risk warning.

**Architecture:** Eligibility is metadata throughout the internal Top10 research pipeline, not an early row filter. Phase18C performs the legacy final Top5 selection, records the final selection rank, then splits tradable rows from research-only rows; only tradable rows reach the cash account. ST status adds a non-blocking warning, while near-limit-down and delisting states remain blocking decisions.

**Tech Stack:** Python 3.14, pandas, pytest, React/TypeScript/Vitest, PostgreSQL-backed LHB replay.

---

### Task 1: Encode ST Warning And Buy-Signal Status In The Shared Contract

**Files:**
- Modify: `tests/test_lhb_eligibility.py`
- Modify: `src/stock_research/lhb_eligibility.py`
- Modify: `src/stock_research/lhb_shortline_v1.py`
- Modify: `src/stock_research/lhb_review_policy.py`

- [ ] **Step 1: Write failing ST and limit-down contract tests**

Add these tests to `tests/test_lhb_eligibility.py`:

```python
def test_st_candidate_remains_eligible_with_high_risk_warning():
    state = resolve_price_limit_state(
        trade_date="2026-07-14",
        ts_code="000078.SZ",
        same_day_name="ST海王",
        current_name="ST海王",
        pct_chg=1.0,
        stored_is_st=None,
        stored_status_quality="untrusted_all_false",
        list_date="1998-12-18",
        listing_age_trading_days=1000,
    )
    decision = evaluate_lhb_eligibility(
        trade_date="2026-07-14",
        ts_code="000078.SZ",
        lhb_reason="日涨幅偏离值达到7%的前5只证券",
        price_limit_state=state,
        pump_risk=0.30,
        high_to_close_drawdown=0.02,
        institution_net_buy=1.0,
        security_state="ST海王",
    )
    assert decision.eligibility_status == "eligible"
    assert decision.backtest_entry_eligible is True
    assert decision.buy_signal_status == "tradable"
    assert "st_high_risk" in decision.warning_codes


def test_st_near_limit_down_is_research_only_not_a_buy_signal():
    state = resolve_price_limit_state(
        trade_date="2026-07-14",
        ts_code="000078.SZ",
        same_day_name="ST海王",
        current_name="ST海王",
        pct_chg=-4.8,
        stored_is_st=None,
        stored_status_quality="untrusted_all_false",
        list_date="1998-12-18",
        listing_age_trading_days=1000,
    )
    decision = evaluate_lhb_eligibility(
        trade_date="2026-07-14",
        ts_code="000078.SZ",
        lhb_reason="日跌幅偏离值达到7%的前5只证券",
        price_limit_state=state,
        pump_risk=0.30,
        high_to_close_drawdown=0.02,
        institution_net_buy=1.0,
        security_state="ST海王",
    )
    assert decision.eligibility_status == "risk_watch"
    assert decision.backtest_entry_eligible is False
    assert decision.buy_signal_status == "research_only"
    assert "near_limit_down_followthrough_risk" in decision.reason_codes
    assert "st_high_risk" in decision.warning_codes
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_lhb_eligibility.py::test_st_candidate_remains_eligible_with_high_risk_warning tests/test_lhb_eligibility.py::test_st_near_limit_down_is_research_only_not_a_buy_signal -q
```

Expected: FAIL because `EligibilityDecision` has no `buy_signal_status` and ST alone does not add `st_high_risk`.

- [ ] **Step 3: Implement the minimal shared-contract change**

In `src/stock_research/lhb_eligibility.py`, add `buy_signal_status: str` to `EligibilityDecision`. At the start of `evaluate_lhb_eligibility`, append `st_high_risk` when `price_limit_state.is_st is True`. Return `buy_signal_status="tradable"` from the final eligible decision and `buy_signal_status="research_only"` from `_decision`.

Add `buy_signal_status` to `LHB_ELIGIBILITY_DECISION_COLUMNS` in `src/stock_research/lhb_shortline_v1.py` and to the decision-field propagation in `src/stock_research/lhb_review_policy.py`.

- [ ] **Step 4: Run eligibility and review-policy tests**

```bash
rtk .venv/bin/pytest tests/test_lhb_eligibility.py tests/test_lhb_review_policy.py -q
```

Expected: PASS with ST tradable unless another blocking rule applies, and all near-limit-down cases research-only.

- [ ] **Step 5: Commit the contract change**

```bash
rtk git add src/stock_research/lhb_eligibility.py src/stock_research/lhb_shortline_v1.py src/stock_research/lhb_review_policy.py tests/test_lhb_eligibility.py
rtk git commit -m "fix: separate LHB buy status from ST risk"
```

### Task 2: Restore The Legacy Internal Top10 Research Pool

**Files:**
- Modify: `tests/test_lhb_data.py`
- Modify: `tests/test_lhb_shortline_v1.py`
- Modify: `src/stock_research/lhb_data.py`
- Modify: `src/stock_research/lhb_shortline_v1.py`

- [ ] **Step 1: Write failing internal-pool regressions**

Change the lifecycle top-value assertion to:

```python
def test_lhb_lifecycle_keeps_legacy_top10_research_pool_for_top5_account():
    assert lhb_shortline_v1._lhb_shortline_v1_top_values(5) == [10]
```

Update the existing full-market eligibility test in `tests/test_lhb_data.py`. Its fixture already contains eligible, `risk_watch`, and `hard_reject` rows inside a Top10 request. Replace the assertions that unsafe rows are absent from `selected_trades` with:

```python
selected = result["selected_trades"]
assert set(selected["ts_code"]) == {"000001.SZ", "000004.SZ", "001399.SZ", "000080.SZ", "000090.SZ"}
assert set(selected["eligibility_status"]) == {"eligible", "risk_watch", "hard_reject"}
assert set(result["selected_rejected_events"]["eligibility_status"]) == {"risk_watch", "hard_reject"}
```

- [ ] **Step 2: Run the focused tests and verify RED**

```bash
rtk .venv/bin/pytest tests/test_lhb_shortline_v1.py::test_lhb_lifecycle_keeps_legacy_top10_research_pool_for_top5_account tests/test_lhb_data.py -q
```

Expected: FAIL because the current branch requests Top5 internally and removes non-tradable rows from `selected_trades` before lifecycle construction.

- [ ] **Step 3: Restore Top10 without removing eligibility metadata**

In `src/stock_research/lhb_shortline_v1.py`, restore:

```python
def _lhb_shortline_v1_top_values(top_n: int) -> list[int]:
    return [max(int(top_n), 10)]
```

In `build_lhb_full_market_pool_backtest_v1`, keep:

```python
ranked_topn = _build_lhb_full_market_pool_selected(evaluated, top_n_values=top_n_values)
selected_rejected = ranked_topn[~ranked_topn["backtest_entry_eligible"].fillna(False)].copy()
selected = ranked_topn.copy()
```

Use the complete `pool["selected_trades"]` as the lifecycle input by replacing the early filter with:

```python
selected = pool["selected_trades"].copy()
_assert_lhb_contract_versions(selected, stage="full_market_selected")
selected_rejected = pool["selected_rejected_events"].copy()
contract_decisions = selected.copy()
```

Retain downstream eligibility metadata propagation.

- [ ] **Step 4: Run pool and lifecycle tests**

```bash
rtk .venv/bin/pytest tests/test_lhb_data.py tests/test_lhb_shortline_v1.py -q
```

Expected: PASS; internal Top10 is restored and unsafe rows are carried only as research metadata.

- [ ] **Step 5: Commit the lifecycle restoration**

```bash
rtk git add src/stock_research/lhb_data.py src/stock_research/lhb_shortline_v1.py tests/test_lhb_data.py tests/test_lhb_shortline_v1.py
rtk git commit -m "fix: restore LHB legacy Top10 research lifecycle"
```

### Task 3: Filter Only After Phase18C Final Top5 Selection

**Files:**
- Modify: `tests/test_lhb_data.py`
- Modify: `src/stock_research/lhb_data.py`
- Modify: `src/stock_research/lhb_shortline_v1.py`

- [ ] **Step 1: Write the failing no-refill account test**

Add this Phase18C regression with six ordered candidates. Final rank 2 is `risk_watch`; all others are eligible.

```python
def test_phase18c_filters_final_top5_for_account_without_rank6_refill():
    lifecycle = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-14",
                "ts_code": f"00000{rank}.SZ",
                "phase12a_rule_layer": "follow_pool_core",
                "fill_status": "filled",
                "entry_trade_date": "2026-07-15",
                "exit_trade_date": "2026-07-16",
                "realized_return": 0.01 * rank,
                "top_n": 10,
                "eligibility_status": "risk_watch" if rank == 2 else "eligible",
                "backtest_entry_eligible": rank != 2,
                "buy_signal_status": "research_only" if rank == 2 else "tradable",
                "eligibility_contract_version": "lhb_eligibility_v2",
            }
            for rank in range(1, 7)
        ]
    )
    scores = pd.DataFrame(
        [
            {
                "trade_date": "2026-07-14",
                "ts_code": f"00000{rank}.SZ",
                "auction_enhanced_score": 100.0 - rank,
            }
            for rank in range(1, 7)
        ]
    )
    result = lhb_data.build_lhb_phase18c_auction_enhanced_cash_account_backtest_v1(
        lifecycle_trades=lifecycle,
        scored_candidates=scores,
        output_dir="unused",
        top_ns=[5],
        write_outputs=False,
    )
    selected = result["selected_trades"]
    rejected = result["selected_rejected_trades"]
    baseline = selected[selected["strategy"].eq("baseline_original_order")]
    assert baseline["phase18c_selection_rank"].tolist() == [1, 3, 4, 5]
    assert 6 not in set(baseline["phase18c_selection_rank"])
    assert rejected.loc[rejected["strategy"].eq("baseline_original_order"), "phase18c_selection_rank"].tolist() == [2]
    assert not result["account_trades"]["backtest_entry_eligible"].eq(False).any()
```

- [ ] **Step 2: Run the regression and verify RED**

```bash
rtk .venv/bin/pytest tests/test_lhb_data.py::test_phase18c_filters_final_top5_for_account_without_rank6_refill -q
```

Expected: FAIL because Phase18C currently passes all selected rows directly into the account and does not expose `phase18c_selection_rank` or `selected_rejected_trades`.

- [ ] **Step 3: Implement final-boundary splitting**

In `_lhb_phase18c_select_topn`, assign selection rank before any eligibility filtering:

```python
selected["phase18c_selection_rank"] = selected.groupby("trade_date").cumcount() + 1
```

In `build_lhb_phase18c_auction_enhanced_cash_account_backtest_v1`, split the already selected Top5:

```python
final_selected = _lhb_phase18c_select_topn(
    lifecycle_trades=lifecycle_trades,
    scored_candidates=scored_candidates,
    top_n=top_n,
    strategy=strategy,
)
entry_eligible = final_selected["backtest_entry_eligible"].fillna(False).astype(bool)
selected = final_selected[entry_eligible].copy()
selected_rejected = final_selected[~entry_eligible].copy()
account_trades, account_curve = _build_lhb_phase15_cash_account_frames(
    lifecycle_trades=selected,
    max_positions=max_positions,
    position_pct=position_pct,
)
```

Aggregate and return `selected_rejected_trades`, write `lhb_phase18c_selected_rejected_trades_v1.csv`, and add `cash_slot_count` to each strategy/top-n summary from the rejected-row count. Do not rerun `_lhb_phase18c_select_topn` after filtering.

In `run_lhb_shortline_v1_lifecycle_from_frames`, remove the assertion that all pre-Phase18C scored candidates are entry eligible. Keep the assertion on Phase18C `selected_trades` and `account_trades`.

- [ ] **Step 4: Run Phase18C and lifecycle tests**

```bash
rtk .venv/bin/pytest tests/test_lhb_data.py tests/test_lhb_shortline_v1.py -q
```

Expected: PASS; rank 2 becomes cash, rank 6 is not promoted, and no research-only row reaches the account.

- [ ] **Step 5: Commit the final-boundary fix**

```bash
rtk git add src/stock_research/lhb_data.py src/stock_research/lhb_shortline_v1.py tests/test_lhb_data.py
rtk git commit -m "fix: apply LHB safety gate after Phase18C Top5"
```

### Task 4: Publish Clear Tradable And Risk Semantics

**Files:**
- Modify: `tests/test_strategy_eod_publish.py`
- Modify: `tests/test_strategy_score_audit.py`
- Modify: `tests/test_dashboard_review_queue.py`
- Modify: `src/stock_research/strategy_eod_publish.py`
- Modify: `src/stock_research/strategy_score_audit.py`
- Modify: `src/stock_research/dashboard/review_queue.py`
- Modify: `dashboard/tests/review-queue-workspace.test.tsx`
- Modify: `dashboard/src/components/ReviewQueueWorkspace.tsx`

- [ ] **Step 1: Write failing publication and ST warning tests**

Build a final-review fixture containing a normal tradable row, a tradable ST row with `st_high_risk`, and a near-limit-down research-only row. Assert publication includes only Phase18C final ranks at most five, never promotes rank 6, and never labels the research-only row as tradable. Assert the ST row retains a user-visible `ST高风险` warning.

```python
assert published["phase18c_selection_rank"].max() <= 5
assert not published["buy_signal_status"].eq("research_only").any()
st_row = published[published["stock_name"].str.contains("ST")].iloc[0]
assert "st_high_risk" in st_row["eligibility_warning_codes"]
```

Add a React assertion that an ST review card displays `ST高风险`, and that no generic LHB label claims every review row is a buy recommendation.

- [ ] **Step 2: Run publication tests and verify RED**

```bash
rtk .venv/bin/pytest tests/test_strategy_eod_publish.py tests/test_strategy_score_audit.py tests/test_dashboard_review_queue.py -q
rtk npm --prefix dashboard test -- --run dashboard/tests/review-queue-workspace.test.tsx
```

Expected: FAIL because `buy_signal_status` and the ST-specific visible warning are not propagated through all publication consumers.

- [ ] **Step 3: Implement minimal publication semantics**

Publish only final Phase18C rows with `phase18c_selection_rank <= 5` and `buy_signal_status == "tradable"`. Keep research-only final selections in `lhb_phase18c_selected_rejected_trades_v1.csv` and expose that artifact path in summary/manifest metadata.

Map `st_high_risk` to the display text `ST高风险` in the review-queue read model. Retain the existing LHB V1 Safe Top5 label and neutral `按策略正式复盘范围` copy.

- [ ] **Step 4: Run backend and frontend publication suites**

```bash
rtk .venv/bin/pytest tests/test_strategy_eod_publish.py tests/test_strategy_score_audit.py tests/test_dashboard_review_queue.py -q
rtk npm --prefix dashboard test -- --run dashboard/tests/review-queue-workspace.test.tsx
```

Expected: PASS; ST is visible with risk, limit-down is never presented as a buy signal, and rank 6 is never promoted.

- [ ] **Step 5: Commit publication semantics**

```bash
rtk git add src/stock_research/strategy_eod_publish.py src/stock_research/strategy_score_audit.py src/stock_research/dashboard/review_queue.py dashboard/src/components/ReviewQueueWorkspace.tsx tests/test_strategy_eod_publish.py tests/test_strategy_score_audit.py tests/test_dashboard_review_queue.py dashboard/tests/review-queue-workspace.test.tsx
rtk git commit -m "fix: show LHB ST risk without implying buy signal"
```

### Task 5: Verify The Complete Pipeline And Replay The Authoritative Database

**Files:**
- Runtime artifacts only: `/tmp/lhb_v1_safe_top5_phase18c_20260715`
- Do not refresh production outputs in this task.

- [ ] **Step 1: Run the complete affected Python suite**

```bash
rtk .venv/bin/pytest tests/test_lhb_eligibility.py tests/test_lhb_review_policy.py tests/test_lhb_data.py tests/test_lhb_shortline_v1.py tests/test_strategy_eod_publish.py tests/test_strategy_score_audit.py tests/test_dashboard_backtests.py tests/test_dashboard_review_queue.py -q
```

Expected: zero failures.

- [ ] **Step 2: Run frontend tests and production build**

```bash
rtk npm --prefix dashboard test -- --run dashboard/tests/review-queue-workspace.test.tsx
rtk npm --prefix dashboard run build
```

Expected: both commands exit 0.

- [ ] **Step 3: Run a fresh same-database replay**

```bash
rtk env PYTHONPATH=src .venv/bin/python - <<'PY'
import json
from stock_research.lhb_shortline_v1 import run_lhb_shortline_v1_backtest_for_dashboard

result = run_lhb_shortline_v1_backtest_for_dashboard({
    "start_date": "2026-01-01",
    "end_date": "2026-07-15",
    "top_n": 5,
    "rebalance_frequency": "daily",
    "transaction_cost_bps": 10.0,
    "max_position_weight": 0.2,
    "adjust_type": "hfq",
    "risk_profile": "balanced",
    "output_dir": "/tmp/lhb_v1_safe_top5_phase18c_20260715",
})
print(json.dumps(result["summary"], ensure_ascii=False, default=str))
PY
```

Expected: a measured result with no assumed return target. Report exact return, drawdown, filled trades, cash slots, ST candidates, ST warnings, ST limit-down rejections, and all near-limit-down research-only rows. Compare it with legacy 182.33%, refill 90.25%, and invalid early-cutoff 17.33%.

- [ ] **Step 4: Audit no-refill and account safety invariants**

```bash
rtk env PYTHONPATH=src .venv/bin/python - <<'PY'
from pathlib import Path
import pandas as pd

base = Path("/tmp/lhb_v1_safe_top5_phase18c_20260715")
selected = pd.read_csv(base / "lhb_phase18c_selected_trades_v1.csv")
rejected = pd.read_csv(base / "lhb_phase18c_selected_rejected_trades_v1.csv")
account = pd.read_csv(base / "lhb_phase18c_account_trades_v1.csv")
assert selected["phase18c_selection_rank"].max() <= 5
assert rejected["phase18c_selection_rank"].max() <= 5
assert not account["backtest_entry_eligible"].eq(False).any()
assert not selected["buy_signal_status"].eq("research_only").any()
assert not rejected["buy_signal_status"].eq("tradable").any()
print({"tradable": len(selected), "cash_slots": len(rejected), "account_rows": len(account)})
PY
```

Expected: all assertions pass.

- [ ] **Step 5: Run final repository checks**

```bash
rtk git diff --check
rtk git status --short
```

Expected: no whitespace errors and only intentional branch changes. Production output refresh remains a separate approval step after the replay result is reviewed.
