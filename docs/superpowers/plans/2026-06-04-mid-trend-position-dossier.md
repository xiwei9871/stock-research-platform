# Mid Trend Position Dossier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new upper-layer `mid_trend_position_dossier` module that turns structured `portfolio_review + research_packet` inputs into a human-readable formal holding/rebalance report with `replay` and `live` modes.

**Architecture:** Keep `mid_trend_portfolio_review` as the structured base layer. Add a new dossier builder module that loads `portfolio_review`, `research_packet`, and available research/company-note fields, derives current-holding / candidate-add / candidate-reduce cohorts, and renders a decision-first Markdown dossier plus a compact CSV summary. CLI wiring stays separate from existing review/report commands.

**Tech Stack:** Python, pandas, pytest

---

### Task 1: Create failing tests for dossier structure and mode handling

**Files:**
- Create: `tests/test_mid_trend_position_dossier.py`
- Test: `tests/test_mid_trend_position_dossier.py`

- [ ] **Step 1: Write the failing tests**

Add tests for:

```python
def test_position_dossier_builds_required_sections() -> None:
    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=portfolio_review,
        research_packet_candidates=research_packet,
    )
    markdown = result["markdown"]
    assert "## 组合级执行摘要" in markdown
    assert "## 当前持仓 Top5" in markdown
    assert "## 候选调入名单" in markdown
    assert "## 候选调出名单" in markdown
    assert "## 附录：结构化证据摘要表" in markdown


def test_position_dossier_live_mode_accepts_enhanced_fields() -> None:
    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-04",
        mode="live",
        portfolio_review=portfolio_review,
        research_packet_candidates=research_packet,
    )
    assert result["summary"]["mode"] == "live"


def test_position_dossier_replay_mode_filters_future_research_rows() -> None:
    filtered = _normalize_dossier_research(research_packet, trade_date="2026-06-04", mode="replay")
    assert filtered["trade_date"].max() <= pd.Timestamp("2026-06-04")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_position_dossier.py -q`
Expected: FAIL because the new module and tests do not exist yet.


### Task 2: Implement dossier builder and data normalization

**Files:**
- Create: `src/stock_research/mid_trend_position_dossier.py`
- Test: `tests/test_mid_trend_position_dossier.py`

- [ ] **Step 1: Add the new module skeleton**

Create:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def run_mid_trend_position_dossier(... ) -> dict[str, Any]:
    ...


def build_mid_trend_position_dossier_from_frames(... ) -> dict[str, Any]:
    ...
```

- [ ] **Step 2: Add minimal normalization helpers**

Implement:

```python
def _normalize_dossier_portfolio_review(... ) -> pd.DataFrame:
    ...


def _normalize_dossier_research(... ) -> pd.DataFrame:
    ...


def _partition_dossier_rows(... ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ...
```

Rules:
- `replay` mode: research rows must be `<= trade_date`
- `live` mode: allow same-day enhanced rows, but not missing-date garbage
- Current holdings come from `portfolio_review.is_current_holding == True`
- Candidate additions come from non-holding rows with strongest action/discussion value
- Candidate reductions come from holding rows with weakest decision/support profile

- [ ] **Step 3: Run the new tests again**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_position_dossier.py -q`
Expected: still FAIL on rendering/content details, but import and basic module shape should be correct.


### Task 3: Implement Markdown dossier rendering

**Files:**
- Modify: `src/stock_research/mid_trend_position_dossier.py`
- Test: `tests/test_mid_trend_position_dossier.py`

- [ ] **Step 1: Add rendering helpers**

Implement:

```python
def _render_dossier_markdown(summary, holdings, candidate_adds, candidate_reduces) -> str:
    ...


def _render_executive_summary(... ) -> list[str]:
    ...


def _render_holding_section(... ) -> list[str]:
    ...


def _render_candidate_add_section(... ) -> list[str]:
    ...


def _render_candidate_reduce_section(... ) -> list[str]:
    ...


def _render_appendix_table(... ) -> list[str]:
    ...
```

- [ ] **Step 2: Encode the two-layer holding narrative**

Each holding section must include:

```python
"当前结论"
"一句话判断"
"支持持有的 3 条核心证据"
"反对持有的 2 条核心证据"
"今天最关键观察点"
"它在涨什么"
"行业/主线位置"
"行业地位与产品地位"
"机构支持逻辑与分歧点"
"技术与趋势状态"
"主要风险与反例"
"证伪条件 / 继续跟踪点"
```

For v1, derive these from existing structured fields plus available research notes. Where data is missing, degrade gracefully with concise placeholders such as `信息不足，需补充` instead of crashing.

- [ ] **Step 3: Run tests to verify dossier Markdown passes**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_position_dossier.py -q`
Expected: PASS


### Task 4: Add CSV summary output and CLI wiring

**Files:**
- Modify: `src/stock_research/mid_trend_position_dossier.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_mid_trend_position_dossier.py`

- [ ] **Step 1: Add CSV summary builder**

Implement:

```python
def _build_dossier_summary_rows(... ) -> pd.DataFrame:
    ...
```

Include:
- stock identifiers
- current decision
- one-line judgment
- core support points
- core opposition points
- candidate add/reduce flags
- trend/research/risk/rebalance tags

- [ ] **Step 2: Add CLI command**

In `cli.py`, add:

```python
mid_trend_position_dossier = subparsers.add_parser("build-mid-trend-position-dossier")
mid_trend_position_dossier.add_argument("--trade-date", required=True)
mid_trend_position_dossier.add_argument("--mode", choices=["replay", "live"], default="replay")
mid_trend_position_dossier.add_argument("--portfolio-review-path", required=True)
mid_trend_position_dossier.add_argument("--research-packet-path", required=True)
mid_trend_position_dossier.add_argument("--output-dir", default="outputs/research")
```

Wire dispatch to `run_mid_trend_position_dossier(...)`.

- [ ] **Step 3: Add CLI dispatch test**

Add a test similar to existing CLI tests:

```python
def test_cli_dispatches_mid_trend_position_dossier(...):
    ...
```

- [ ] **Step 4: Run targeted tests**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_position_dossier.py -q`
Expected: PASS


### Task 5: Refresh real artifact and run regression verification

**Files:**
- Modify: `src/stock_research/mid_trend_position_dossier.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_mid_trend_position_dossier.py`

- [ ] **Step 1: Run module tests**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_position_dossier.py -q`
Expected: PASS

- [ ] **Step 2: Generate a real dossier artifact**

Run:

```bash
cd /Users/xiwei/stock_research && PYTHONPATH=/Users/xiwei/stock_research/src .venv/bin/python -m stock_research.cli build-mid-trend-position-dossier \
  --trade-date 2026-06-02 \
  --mode replay \
  --portfolio-review-path outputs/research/mid_trend_portfolio_review_20260604_current_holdings/mid_trend_portfolio_review_2026-06-02.csv \
  --research-packet-path outputs/research/mid_trend_research_packet_20260602_pdf_enriched/mid_trend_research_packet_candidates.csv \
  --output-dir outputs/research/mid_trend_position_dossier_20260602
```

Expected: dossier Markdown + CSV are created successfully.

- [ ] **Step 3: Run full regression suite**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest -q`
Expected: PASS
