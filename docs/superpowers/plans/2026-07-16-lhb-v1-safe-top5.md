# LHB V1 Safe Top5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the original LHB Top5 strategy identity while retaining the eligibility safety contract: select original Top5, reject unsafe names, leave cash, and never refill from ranks 6-10.

**Architecture:** Change the full-market pool boundary so ranking happens on the evaluated universe, original ranks are assigned, and eligibility filtering happens only after original TopN selection. Keep full-universe and selected-TopN rejection artifacts separate. Publish only eligible original-Top5 rows as official LHB review entries, keep risk rows in audit artifacts, and label the platform with strategy-specific scope and selection-policy metadata.

**Tech Stack:** Python 3.14, pandas, pytest, FastAPI dashboard read models, React/TypeScript/Vitest, PostgreSQL-backed fresh LHB replay.

---

### Task 1: Select Original TopN Before Eligibility Filtering

**Files:**
- Modify: `tests/test_lhb_data.py`
- Modify: `src/stock_research/lhb_data.py`

- [ ] **Step 1: Replace the pre-ranking eligibility regression with a no-refill regression**

Create a fixture containing six ranked candidates where rank 2 is `risk_watch`. Assert that `top_n_values=[5]` produces eligible ranks `{1, 3, 4, 5}`, excludes rank 6, and returns the rejected rank-2 row in `selected_rejected_events`.

```python
def test_build_lhb_full_market_pool_backtest_v1_filters_after_original_topn_without_refill(tmp_path):
    result = lhb_data.build_lhb_full_market_pool_backtest_v1(
        lhb_features=_safe_top5_fixture_with_rejected_rank2(),
        daily_bars=_safe_top5_daily_bars(),
        start_date="2026-07-14",
        end_date="2026-07-14",
        top_n_values=[5],
        output_dir=tmp_path,
    )
    selected = result["selected_trades"]
    rejected = result["selected_rejected_events"]
    assert selected["selection_rank"].tolist() == [1, 3, 4, 5]
    assert 6 not in set(selected["selection_rank"])
    assert rejected["selection_rank"].tolist() == [2]
```

- [ ] **Step 2: Run the regression and verify RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_lhb_data.py::test_build_lhb_full_market_pool_backtest_v1_filters_after_original_topn_without_refill -q
```

Expected: FAIL because the current implementation filters eligibility before ranking and refills from rank 6.

- [ ] **Step 3: Implement original-rank selection and selected-risk split**

In `build_lhb_full_market_pool_backtest_v1`, rank `evaluated` first and split the ranked output:

```python
ranked_topn = _build_lhb_full_market_pool_selected(evaluated, top_n_values=top_n_values)
selected_rejected = ranked_topn[~ranked_topn["backtest_entry_eligible"].fillna(False)].copy()
selected = ranked_topn[ranked_topn["backtest_entry_eligible"].fillna(False)].copy()
```

Continue exposing full-universe `eligible_candidates` and `rejected_events`, add `selected_rejected_events` to the return payload, and write `lhb_full_market_pool_selected_rejected_events_v1.csv`. Do not renumber `selection_rank` after filtering.

- [ ] **Step 4: Run focused and adjacent tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_lhb_data.py -q
```

Expected: all `test_lhb_data.py` tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
rtk git add src/stock_research/lhb_data.py tests/test_lhb_data.py
rtk git commit -m "fix: preserve original LHB Top5 before safety filtering"
```

### Task 2: Keep No-Refill Semantics Through The Lifecycle

**Files:**
- Modify: `tests/test_lhb_shortline_v1.py`
- Modify: `src/stock_research/lhb_shortline_v1.py`

- [ ] **Step 1: Add lifecycle tests for original rank preservation**

Test `_build_lhb_review_candidates` and the lifecycle boundary with eligible original ranks 1, 3, and 5 plus risk-watch rank 2. Assert the official review candidates contain only 1, 3, and 5, and no risk-watch or rank above 5 is introduced.

```python
def test_build_lhb_review_candidates_keeps_only_eligible_original_top5_without_refill():
    review = _build_lhb_review_candidates(
        scored_candidates=_eligible_scored_rows_at_original_ranks_1_3_5(),
        risk_watch_candidates=_risk_watch_row_at_original_rank_2(),
        top_n=5,
    )
    assert review["selection_rank"].tolist() == [1, 3, 5]
    assert review["eligibility_status"].eq("eligible").all()
```

- [ ] **Step 2: Run the lifecycle regression and verify RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_lhb_shortline_v1.py::test_build_lhb_review_candidates_keeps_only_eligible_original_top5_without_refill -q
```

Expected: FAIL because current review construction appends risk-watch candidates.

- [ ] **Step 3: Stop mixing risk-watch rows into official review candidates**

Update `_build_lhb_review_candidates` to filter `scored_candidates` to `backtest_entry_eligible=true` and original rank `<= top_n`, while leaving risk-watch rows in the pool audit artifacts produced by Task 1. Add summary metadata:

```python
summary["selection_policy"] = "original_topn_then_eligibility_no_refill"
summary["strategy_version"] = "lhb_v1_safe_top5"
summary["cash_slot_count"] = selected_rejected_count
```

Pass the selected-rejection count/path from pool results into the summary and returned paths.

- [ ] **Step 4: Verify lifecycle and eligibility suites**

Run:

```bash
rtk .venv/bin/pytest tests/test_lhb_shortline_v1.py tests/test_lhb_eligibility.py -q
```

Expected: all tests pass and eligibility parity assertions remain active.

- [ ] **Step 5: Commit Task 2**

```bash
rtk git add src/stock_research/lhb_shortline_v1.py tests/test_lhb_shortline_v1.py
rtk git commit -m "fix: keep LHB safety gaps as cash"
```

### Task 3: Publish Only Official Safe-Top5 Review Rows

**Files:**
- Modify: `tests/test_strategy_eod_publish.py`
- Modify: `tests/test_strategy_score_audit.py`
- Modify: `src/stock_research/lhb_review_policy.py`
- Modify: `src/stock_research/strategy_eod_publish.py`
- Modify: `src/stock_research/strategy_score_audit.py`

- [ ] **Step 1: Add publication regressions**

Add a review frame containing eligible original ranks 1, 3, 5, risk-watch rank 2, and eligible rank 6. Assert official publication returns only ranks 1, 3, 5, preserves their ranks, and reports `selected_count=3` rather than counting audit rows.

```python
assert published["rank"].tolist() == [1, 3, 5]
assert published["eligibility_status"].eq("eligible").all()
assert audit_summary["selected_count"] == 3
```

- [ ] **Step 2: Run publication regressions and verify RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_strategy_eod_publish.py tests/test_strategy_score_audit.py -q
```

Expected: at least one new assertion fails because the current publisher includes risk-watch rows and compacts eligible ranks.

- [ ] **Step 3: Preserve upstream original rank and filter official output**

Change `apply_lhb_top5_gate` so an upstream `selection_rank`/`source_rank` is authoritative. Do not compute an `eligible_rank` counter. In `strategy_eod_publish`, retain only rows satisfying all of:

```python
eligibility_status == "eligible"
backtest_entry_eligible is True
original_rank <= 5
```

Keep rejected rows referenced through the separate audit artifact path in manifest metadata. Update score-audit selection logic so only published official rows count as selected.

- [ ] **Step 4: Verify strategy publication suites**

Run:

```bash
rtk .venv/bin/pytest tests/test_strategy_eod_publish.py tests/test_strategy_score_audit.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
rtk git add src/stock_research/lhb_review_policy.py src/stock_research/strategy_eod_publish.py src/stock_research/strategy_score_audit.py tests/test_strategy_eod_publish.py tests/test_strategy_score_audit.py
rtk git commit -m "fix: publish only official LHB safe Top5 rows"
```

### Task 4: Correct Platform Scope And Version Labels

**Files:**
- Modify: `tests/test_dashboard_backtests.py`
- Modify: `tests/test_dashboard_review_queue.py`
- Modify: `src/stock_research/dashboard/backtests.py`
- Modify: `src/stock_research/dashboard/review_queue.py`
- Modify: `dashboard/tests/review-queue-workspace.test.tsx`
- Modify: `dashboard/src/components/ReviewQueueWorkspace.tsx`

- [ ] **Step 1: Add backend and frontend label regressions**

Assert LHB metrics expose `strategy_version=lhb_v1_safe_top5` and `selection_policy=original_topn_then_eligibility_no_refill`. Assert the review workspace no longer displays the generic `启用策略 Top10` label and instead displays `按策略正式复盘范围`.

- [ ] **Step 2: Run regressions and verify RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_backtests.py tests/test_dashboard_review_queue.py -q
rtk npm --prefix dashboard test -- --run dashboard/tests/review-queue-workspace.test.tsx
```

Expected: new metadata and label assertions fail.

- [ ] **Step 3: Surface selection-policy metadata and neutral platform copy**

Extend `_metrics_from_eod_summary` with the two string fields and include the strategy version in `_eod_strategy_evidence`. Replace the shared Top10 copy with `按策略正式复盘范围`; group labels and counts continue to come from backend strategy-specific data.

- [ ] **Step 4: Verify dashboard suites**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_backtests.py tests/test_dashboard_review_queue.py -q
rtk npm --prefix dashboard test -- --run dashboard/tests/review-queue-workspace.test.tsx
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 4**

```bash
rtk git add src/stock_research/dashboard/backtests.py src/stock_research/dashboard/review_queue.py tests/test_dashboard_backtests.py tests/test_dashboard_review_queue.py dashboard/src/components/ReviewQueueWorkspace.tsx dashboard/tests/review-queue-workspace.test.tsx
rtk git commit -m "fix: label LHB safe Top5 metrics explicitly"
```

### Task 5: Full Verification And Same-Database Replay

**Files:**
- Create runtime artifacts only under: `/tmp/lhb_v1_safe_top5_20260715`
- Refresh after acceptance: `outputs/research/strategy_daily_eod/2026-07-15`

- [ ] **Step 1: Run the full affected Python suite**

```bash
rtk .venv/bin/pytest tests/test_lhb_data.py tests/test_lhb_shortline_v1.py tests/test_lhb_eligibility.py tests/test_strategy_eod_publish.py tests/test_strategy_score_audit.py tests/test_dashboard_backtests.py tests/test_dashboard_review_queue.py -q
```

Expected: zero failures.

- [ ] **Step 2: Run frontend tests and build**

```bash
rtk npm --prefix dashboard test -- --run dashboard/tests/review-queue-workspace.test.tsx
rtk npm --prefix dashboard run build
```

Expected: test and build exit 0.

- [ ] **Step 3: Run fresh safe-Top5 replay against the authoritative database**

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
    "output_dir": "/tmp/lhb_v1_safe_top5_20260715",
})
print(json.dumps(result["summary"], ensure_ascii=False, default=str))
PY
```

Expected: `strategy_version=lhb_v1_safe_top5`, `selection_policy=original_topn_then_eligibility_no_refill`, no official entry with rank above five, and complete return/drawdown/trade-count metrics suitable for an exact comparison with the frozen legacy and refill variants. No numerical ordering is assumed before measurement.

- [ ] **Step 4: Audit replay artifacts**

Verify:

```bash
rtk .venv/bin/python - <<'PY'
import pandas as pd
base = "/tmp/lhb_v1_safe_top5_20260715"
trades = pd.read_csv(f"{base}/lhb_shortline_v1_trades.csv")
rejected = pd.read_csv(f"{base}/lhb_full_market_pool_selected_rejected_events_v1.csv")
assert trades["selection_rank"].max() <= 5
assert rejected["selection_rank"].between(1, 5).all()
assert not trades["backtest_entry_eligible"].eq(False).any()
print({"trade_rows": len(trades), "cash_slots": len(rejected)})
PY
```

Expected: assertions pass.

- [ ] **Step 5: Refresh 0715 strategy EOD and platform-ready checks after replay acceptance**

```bash
rtk .venv/bin/python -m stock_research.cli run-strategy-daily-eod --trade-date 2026-07-15 --output-root outputs/research/strategy_daily_eod
rtk .venv/bin/python -m stock_research.platform_ready --trade-date 2026-07-15 --json-output outputs/research/platform_ready/2026-07-15.json
```

Expected: strategy daily EOD succeeds, LHB official review count is at most five, and platform status is `ready`.

- [ ] **Step 6: Final diff and repository checks**

```bash
rtk git diff --check
rtk git status --short
```

Expected: no whitespace errors; only intentional implementation files and generated accepted artifacts are present.
