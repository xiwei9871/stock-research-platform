# Mid Trend Portfolio Review Markdown Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change `mid_trend_portfolio_review` Markdown output so `Top5` renders as per-stock sections with evidence blocks while `Top6-10` remains a compact table.

**Architecture:** Keep the existing CSV unchanged and only refactor Markdown rendering helpers in `mid_trend_portfolio_review.py`. Add a small set of Markdown-specific helper functions for summary sections, per-stock rendering, and the retained `Top6-10` compact table.

**Tech Stack:** Python, pandas, pytest

---

### Task 1: Add failing tests for the new Markdown layout

**Files:**
- Modify: `tests/test_mid_trend_portfolio_review.py`
- Test: `tests/test_mid_trend_portfolio_review.py`

- [ ] **Step 1: Write the failing tests**

Add tests that assert Markdown now contains:

```python
def test_portfolio_review_markdown_renders_top5_as_per_stock_sections() -> None:
    ...
    assert "## Top5 Overview" in markdown
    assert "## Evidence Snapshot" in markdown
    assert "### 1. 生益科技 / 600183.SH" in markdown
    assert "**Trend Evidence**" in markdown
    assert "**Research Evidence**" in markdown
    assert "**Risk Evidence**" in markdown
    assert "**Rebalance Reason Evidence**" in markdown


def test_portfolio_review_markdown_keeps_top6_10_as_compact_table() -> None:
    ...
    assert "## Top6-10 Discussion Pool" in markdown
    assert "| candidate_rank | stock_name | ts_code |" in markdown
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_portfolio_review.py -k "per_stock_sections or compact_table" -q`
Expected: FAIL because current Markdown still uses full tables.


### Task 2: Implement the new Markdown layout

**Files:**
- Modify: `src/stock_research/mid_trend_portfolio_review.py`
- Test: `tests/test_mid_trend_portfolio_review.py`

- [ ] **Step 1: Add markdown helper functions**

Add minimal helpers:

```python
def _render_top5_overview(top5: pd.DataFrame) -> list[str]:
    ...


def _render_evidence_snapshot(top5: pd.DataFrame) -> list[str]:
    ...


def _render_top5_stock_sections(top5: pd.DataFrame) -> list[str]:
    ...


def _render_top6_10_table(top6_10: pd.DataFrame) -> list[str]:
    ...
```

- [ ] **Step 2: Update `_render_markdown()`**

Change the output flow to:

```python
lines = [
    f"# Mid Trend Portfolio Review {trade_date}",
    "",
    "## Portfolio Summary",
    ...
    "## Top5 Overview",
    ...
    "## Evidence Snapshot",
    ...
    "## Top5 Execution Pool",
    ...
    "## Top6-10 Discussion Pool",
    ...
]
```

- [ ] **Step 3: Keep CSV untouched**

Do not modify:

```python
review_rows.to_csv(...)
```

Do not change `review_rows` column order solely for Markdown purposes.

- [ ] **Step 4: Run targeted tests to verify they pass**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_portfolio_review.py -k "per_stock_sections or compact_table" -q`
Expected: PASS


### Task 3: Regression verification and real report refresh

**Files:**
- Modify: `src/stock_research/mid_trend_portfolio_review.py`
- Modify: `tests/test_mid_trend_portfolio_review.py`

- [ ] **Step 1: Run the full module test file**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_portfolio_review.py -q`
Expected: PASS

- [ ] **Step 2: Regenerate the real 2026-06-01 report**

Run:

```bash
cd /Users/xiwei/stock_research && PYTHONPATH=/Users/xiwei/stock_research/src .venv/bin/python -m stock_research.cli build-mid-trend-portfolio-review \
  --trade-date 2026-06-01 \
  --strategy-variant top5_weekly_max_2_replacements \
  --top10-path outputs/research/mid_trend_shadow_top10_context_fixed_20260601/mid_trend_shadow_top10.csv \
  --holdings-path outputs/research/mid_trend_shadow_weekly_control_context_fixed_20260602/mid_trend_shadow_weekly_control_positions.csv \
  --trades-path outputs/research/mid_trend_shadow_weekly_control_context_fixed_20260602/mid_trend_shadow_weekly_control_trades.csv \
  --research-packet-path outputs/research/mid_trend_research_packet_20260601_pdf_enriched/mid_trend_research_packet_candidates.csv \
  --output-dir outputs/research/mid_trend_portfolio_review_20260601
```

Expected: Markdown regenerates with the new `Top5` section layout and unchanged CSV path/output behavior.

- [ ] **Step 3: Run the full regression suite**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest -q`
Expected: PASS
