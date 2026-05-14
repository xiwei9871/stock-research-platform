# Dragon Strategy Research V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a diagnostic-first hot-industry leader identification module that computes `dragon_score`, assigns `dragon_role`, and writes CSV plus Markdown diagnostics without Dragon-Tiger List data or trading logic.

**Architecture:** Add a standalone `dragon_strategy_research.py` module with pure DataFrame helpers for scoring, role labels, summaries, and report writing, plus SQL loaders and one CLI wrapper. Keep industry mainline logic in existing industry modules and treat future returns as diagnostic columns appended after scoring.

**Tech Stack:** Python, pandas, PostgreSQL via existing `connect`/`fetch_all`, argparse CLI in `stock_research.cli`, pytest.

---

### Task 1: Add Pure Dragon Scoring Tests

**Files:**
- Create: `tests/test_dragon_strategy_research.py`
- Create: `src/stock_research/dragon_strategy_research.py`

- [ ] **Step 1: Write failing tests for scoring and role labels**

Add tests that import:

```python
from stock_research.dragon_strategy_research import (
    DRAGON_DIAGNOSTIC_COLUMNS,
    assign_dragon_roles,
    compute_dragon_scores,
    effective_membership_for_dates,
)
```

Test cases:

```python
def test_dragon_score_ignores_future_return_columns():
    base = _sample_feature_frame()
    with_future = base.assign(
        future_1d_return=[99.0, -99.0, 50.0, -50.0],
        future_20d_return=[99.0, -99.0, 50.0, -50.0],
    )
    scored_base = compute_dragon_scores(base)
    scored_future = compute_dragon_scores(with_future)
    assert scored_base["dragon_score"].tolist() == scored_future["dragon_score"].tolist()


def test_effective_membership_uses_trade_date_window():
    memberships = pd.DataFrame(
        [
            {"asset_id": "A", "industry_name": "Old", "start_date": "2024-01-01", "end_date": "2024-06-30"},
            {"asset_id": "A", "industry_name": "New", "start_date": "2024-07-01", "end_date": None},
        ]
    )
    dates = pd.DataFrame(
        [
            {"asset_id": "A", "trade_date": "2024-06-28"},
            {"asset_id": "A", "trade_date": "2024-07-02"},
        ]
    )
    result = effective_membership_for_dates(dates, memberships)
    assert result["industry_name"].tolist() == ["Old", "New"]


def test_assign_dragon_roles_for_representative_rows():
    scored = compute_dragon_scores(_sample_feature_frame())
    roles = assign_dragon_roles(scored)
    assert dict(zip(roles["asset_id"], roles["dragon_role"])) == {
        "LEADER": "dragon_leader",
        "HOT": "overheated_leader",
        "CATCH": "laggard_catchup",
        "FOLLOW": "follower",
    }
```

- [ ] **Step 2: Run tests to verify missing module failure**

Run: `.venv/bin/pytest tests/test_dragon_strategy_research.py -q`

Expected: FAIL because `stock_research.dragon_strategy_research` is missing.

- [ ] **Step 3: Add minimal module constants and functions**

Create `src/stock_research/dragon_strategy_research.py` with:

- `DRAGON_DIAGNOSTIC_COLUMNS`
- `compute_dragon_scores(frame: pd.DataFrame) -> pd.DataFrame`
- `assign_dragon_roles(frame: pd.DataFrame) -> pd.DataFrame`
- `effective_membership_for_dates(dates: pd.DataFrame, memberships: pd.DataFrame) -> pd.DataFrame`

- [ ] **Step 4: Run tests and make them pass**

Run: `.venv/bin/pytest tests/test_dragon_strategy_research.py -q`

Expected: PASS.

### Task 2: Add Penalty And Summary Tests

**Files:**
- Modify: `tests/test_dragon_strategy_research.py`
- Modify: `src/stock_research/dragon_strategy_research.py`

- [ ] **Step 1: Write failing tests for penalties and role effectiveness**

Add tests for:

```python
def test_overheat_penalty_rises_for_extreme_short_term_move():
    frame = _sample_feature_frame()
    normal = compute_dragon_scores(frame)
    extreme = frame.copy()
    extreme.loc[extreme["asset_id"] == "LEADER", "stock_return_5d"] = 0.35
    extreme.loc[extreme["asset_id"] == "LEADER", "amount_vs_20d"] = 4.0
    heated = compute_dragon_scores(extreme)
    assert heated.loc[heated["asset_id"] == "LEADER", "overheat_penalty"].iloc[0] > normal.loc[normal["asset_id"] == "LEADER", "overheat_penalty"].iloc[0]


def test_follower_penalty_rises_when_stock_lags_hot_industry():
    frame = _sample_feature_frame()
    scored = compute_dragon_scores(frame)
    follower_penalty = scored.loc[scored["asset_id"] == "FOLLOW", "follower_penalty"].iloc[0]
    leader_penalty = scored.loc[scored["asset_id"] == "LEADER", "follower_penalty"].iloc[0]
    assert follower_penalty > leader_penalty


def test_role_effectiveness_statistics_are_correct():
    diagnostics = pd.DataFrame([...])
    summary = summarize_role_effectiveness(diagnostics)
    leader = summary[summary["role"] == "dragon_leader"].iloc[0]
    assert leader["sample_count"] == 2
    assert leader["avg_future_5d_return"] == pytest.approx(0.04)
    assert leader["win_rate_10d"] == pytest.approx(0.5)
```

- [ ] **Step 2: Run tests to verify missing summary failure**

Run: `.venv/bin/pytest tests/test_dragon_strategy_research.py -q`

Expected: FAIL because `summarize_role_effectiveness` or penalty behavior is missing.

- [ ] **Step 3: Implement penalties and summaries**

Add:

- `summarize_role_effectiveness(diagnostics: pd.DataFrame) -> pd.DataFrame`
- explicit `ROLE_EFFECTIVENESS_COLUMNS`
- helper functions for clipping/ranking.

- [ ] **Step 4: Run focused tests**

Run: `.venv/bin/pytest tests/test_dragon_strategy_research.py -q`

Expected: PASS.

### Task 3: Add Diagnostics Builder And Report Tests

**Files:**
- Modify: `tests/test_dragon_strategy_research.py`
- Modify: `src/stock_research/dragon_strategy_research.py`

- [ ] **Step 1: Write failing tests for diagnostic builder and Markdown report**

Add tests for:

- `build_dragon_diagnostics(...)` merges bars, effective memberships, industry diagnostics, lifecycle samples, and appends future returns after scoring.
- `write_dragon_report(...)` writes required Markdown sections.

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/test_dragon_strategy_research.py -q`

Expected: FAIL due missing builder/report functions.

- [ ] **Step 3: Implement builder and report writer**

Add:

- `build_dragon_diagnostics(...)`
- `summarize_monthly(...)`
- `summarize_yearly(...)`
- `write_dragon_outputs(...)`
- `_markdown_report(...)`

- [ ] **Step 4: Run focused tests**

Run: `.venv/bin/pytest tests/test_dragon_strategy_research.py -q`

Expected: PASS.

### Task 4: Add SQL Loaders And CLI

**Files:**
- Modify: `src/stock_research/dragon_strategy_research.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_dragon_strategy_research.py` or create `tests/test_dragon_strategy_research_cli.py`

- [ ] **Step 1: Write failing CLI/parser test**

Verify `build_parser()` accepts:

```bash
stock-research dragon-research-v1 --start-date 2024-05-27 --end-date 2026-05-12
```

- [ ] **Step 2: Run targeted CLI test**

Run: `.venv/bin/pytest tests/test_dragon_strategy_research.py -q`

Expected: FAIL because command is missing.

- [ ] **Step 3: Implement loader and CLI integration**

Add:

- `DragonResearchConfig`
- `run_dragon_research_v1(...)`
- `load_dragon_bars(...)`
- `load_dragon_memberships(...)`
- `load_asset_names(...)`
- optional CSV loaders for `--industry-diagnostics-path`, `--candidate-scores-path`, `--lifecycle-samples-path`.

Add parser and command handler in `cli.py`.

- [ ] **Step 4: Run focused tests**

Run: `.venv/bin/pytest tests/test_dragon_strategy_research.py -q`

Expected: PASS.

### Task 5: Full Verification

**Files:**
- All changed files.

- [ ] **Step 1: Run focused tests**

Run: `.venv/bin/pytest tests/test_dragon_strategy_research.py -q`

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run: `.venv/bin/pytest`

Expected: PASS, or report exact failures if unrelated existing tests fail.

- [ ] **Step 3: Inspect diff**

Run: `git diff -- docs/superpowers/specs/2026-05-13-dragon-strategy-research-v1-design.md docs/superpowers/plans/2026-05-13-dragon-strategy-research-v1.md src/stock_research/dragon_strategy_research.py src/stock_research/cli.py tests/test_dragon_strategy_research.py`

Expected: Changes only implement Dragon Strategy Research v1.
