# Industry Mainline Regime Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a point-in-time diagnostic layer that separates market regime from industry mainline quality before any strategy/backtest integration.

**Architecture:** Add a focused `industry_mainline_regime.py` module that consumes existing V2 diagnostics CSV rows and optionally existing backtest/effectiveness CSV outputs. The module computes daily market regime labels, a new `industry_mainline_score_v1`, regime-conditioned future effectiveness tables, and a Markdown research report. CLI wiring follows the existing `stock-research <command>` parser style.

**Tech Stack:** Python, pandas, existing `stock_research.cli`, pytest, CSV outputs under `outputs/research`.

---

### Task 1: Market Regime Classification

**Files:**
- Create: `src/stock_research/industry_mainline_regime.py`
- Test: `tests/test_industry_mainline_regime.py`

- [ ] **Step 1: Write the failing test**

```python
def test_classify_market_regime_distinguishes_mainline_and_rotation():
    diagnostics = pd.DataFrame([...])
    regimes = build_market_regime_diagnostics(diagnostics)
    assert regimes.loc[regimes["rebalance_date"] == "2026-01-01", "market_regime"].iloc[0] == "mainline"
    assert regimes.loc[regimes["rebalance_date"] == "2026-01-02", "market_regime"].iloc[0] == "rotation"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_industry_mainline_regime.py::test_classify_market_regime_distinguishes_mainline_and_rotation -q`

Expected: FAIL because `industry_mainline_regime` does not exist.

- [ ] **Step 3: Write minimal implementation**

Implement `build_market_regime_diagnostics(diagnostics)` using only same-date diagnostic columns:
- `mainline` when top industry score spread is high, top3 concentration is high, and median overheat is not excessive.
- `rotation` when score spread is low or top groups change without dominance.
- `weak_market` when median future-independent recent strength columns are weak.
- `broad_market` when breadth is high and industry dispersion is low.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_industry_mainline_regime.py -q`

Expected: PASS.

### Task 2: Industry Mainline Score V1

**Files:**
- Modify: `src/stock_research/industry_mainline_regime.py`
- Test: `tests/test_industry_mainline_regime.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_mainline_score_rewards_persistence_density_and_expansion():
    scored = build_industry_mainline_scores(sample_diagnostics)
    strong = scored[scored["industry_name"] == "持续扩散行业"].iloc[0]
    hot = scored[scored["industry_name"] == "过热行业"].iloc[0]
    assert strong["industry_mainline_score_v1"] > hot["industry_mainline_score_v1"]

def test_mainline_score_does_not_use_future_columns():
    score_a = build_industry_mainline_scores(base)
    score_b = build_industry_mainline_scores(base.assign(future_20d_return=-0.5, future_20d_excess_return=-0.5))
    assert score_a["industry_mainline_score_v1"].tolist() == score_b["industry_mainline_score_v1"].tolist()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_industry_mainline_regime.py -q`

Expected: FAIL because scoring function is missing.

- [ ] **Step 3: Write minimal implementation**

Implement `build_industry_mainline_scores(diagnostics)` with:
- `mainline_persistence_score`
- `mainline_amount_quality_score`
- `mainline_candidate_quality_score`
- `mainline_breadth_quality_score`
- `mainline_expansion_quality_score`
- `mainline_overheat_risk`
- `mainline_concentration_risk`
- `industry_mainline_score_v1`
- `mainline_tag`

Only use current or historical diagnostic columns, never `future_20d_*`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_industry_mainline_regime.py -q`

Expected: PASS.

### Task 3: Regime-Conditioned Effectiveness Tables

**Files:**
- Modify: `src/stock_research/industry_mainline_regime.py`
- Test: `tests/test_industry_mainline_regime.py`

- [ ] **Step 1: Write failing tests**

```python
def test_regime_effectiveness_groups_future_returns_by_regime_and_bucket():
    scored = build_industry_mainline_scores(sample_diagnostics)
    regimes = build_market_regime_diagnostics(sample_diagnostics)
    table = build_regime_effectiveness(scored, regimes)
    assert {"market_regime", "score_bucket", "avg_future_20d_excess_return"}.issubset(table.columns)
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/pytest tests/test_industry_mainline_regime.py -q`

Expected: FAIL because effectiveness function is missing.

- [ ] **Step 3: Implement summaries**

Implement:
- `build_regime_effectiveness(scored, regimes)`
- `build_mainline_tag_effectiveness(scored)`
- `write_industry_mainline_report(...)`

- [ ] **Step 4: Run tests**

Run: `.venv/bin/pytest tests/test_industry_mainline_regime.py -q`

Expected: PASS.

### Task 4: CLI Wiring

**Files:**
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_industry_mainline_regime_cli.py`

- [ ] **Step 1: Write failing CLI test**

```python
def test_industry_mainline_regime_cli_prints_outputs(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_industry_mainline_regime_diagnostics", fake_runner)
    monkeypatch.setattr("sys.argv", ["stock-research", "industry-mainline-regime-diagnostics", "--diagnostics-path", "/tmp/diag.csv", "--start-date", "2024-05-27", "--end-date", "2026-05-12"])
    cli.main()
    assert "industry_mainline_regime|diagnostics|" in capsys.readouterr().out
```

- [ ] **Step 2: Run CLI test**

Run: `.venv/bin/pytest tests/test_industry_mainline_regime_cli.py -q`

Expected: FAIL because CLI command is missing.

- [ ] **Step 3: Implement CLI**

Add command:

```bash
stock-research industry-mainline-regime-diagnostics \
  --diagnostics-path outputs/research/industry_focus_score_v2_diagnostics.csv \
  --start-date 2024-05-27 \
  --end-date 2026-05-12 \
  --output-dir outputs/research
```

- [ ] **Step 4: Run CLI tests**

Run: `.venv/bin/pytest tests/test_industry_mainline_regime_cli.py tests/test_industry_mainline_regime.py -q`

Expected: PASS.

### Task 5: Generate Real Outputs and Verify

**Files:**
- Output: `outputs/research/industry_mainline_regime_diagnostics.csv`
- Output: `outputs/research/market_regime_industry_effectiveness.csv`
- Output: `outputs/research/industry_mainline_tag_effectiveness.csv`
- Output: `outputs/research/industry_mainline_regime_report.md`

- [ ] **Step 1: Run diagnostics**

Run:

```bash
.venv/bin/stock-research industry-mainline-regime-diagnostics \
  --diagnostics-path outputs/research/industry_focus_score_v2_diagnostics.csv \
  --start-date 2024-05-27 \
  --end-date 2026-05-12 \
  --output-dir outputs/research
```

- [ ] **Step 2: Inspect summaries**

Run:

```bash
.venv/bin/python -c "import pandas as pd; print(pd.read_csv('outputs/research/market_regime_industry_effectiveness.csv').to_string(index=False))"
```

- [ ] **Step 3: Full verification**

Run: `.venv/bin/pytest`

Expected: all tests pass.

### Self-Review

- Scope is limited to diagnostics and reporting. No strategy integration, backtest replacement, live trading, broker code, or tuning loop is included.
- All scoring functions are point-in-time by construction and tests verify future columns do not affect scores.
- Outputs are research artifacts under `outputs/research`, consistent with existing industry factor reports.
