# Research Narrative Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable `research_narrative` middle layer that turns existing structured research inputs into `research_fact_sheet` and `research_decision_narrative`, then wire the first consumer to `mid_trend_position_dossier`.

**Architecture:** Add a new standalone module `research_narrative.py` with two deterministic stages: fact-sheet assembly and narrative synthesis. Keep the first integration narrow: `mid_trend_position_dossier` consumes the new outputs for holdings/candidate narrative, while other downstream consumers remain unchanged for now.

**Tech Stack:** Python, pandas, pytest

---

### Task 1: Create failing tests for fact-sheet and narrative outputs

**Files:**
- Create: `tests/test_research_narrative.py`
- Test: `tests/test_research_narrative.py`

- [ ] **Step 1: Write the failing tests**

Add tests for:

```python
def test_build_research_fact_sheet_from_frames_maps_core_fields() -> None:
    fact_sheet = build_research_fact_sheet_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=portfolio_review,
        research_packet_candidates=research_packet,
    )
    row = fact_sheet.set_index("asset_id").loc["CN:SH:600183"]
    assert row["report_count_90d"] == 3
    assert row["target_price_median"] == 103.5
    assert row["risk_summary_compact"] != ""
    assert bool(row["has_target_price"]) is True


def test_build_research_decision_narrative_from_fact_sheet_generates_support_and_oppose_facts() -> None:
    narrative = build_research_decision_narrative_from_fact_sheet(fact_sheet)
    row = narrative.set_index("asset_id").loc["CN:SH:600183"]
    assert row["one_line_judgment"] != ""
    assert row["support_fact_1"] != ""
    assert row["oppose_fact_1"] != ""
    assert row["narrative_quality_flag"] in {"rich", "medium", "thin"}


def test_research_fact_sheet_replay_filters_future_rows() -> None:
    fact_sheet = build_research_fact_sheet_from_frames(
        trade_date="2026-06-04",
        mode="replay",
        portfolio_review=portfolio_review,
        research_packet_candidates=research_packet,
    )
    assert "CN:SH:688301" not in set(fact_sheet["asset_id"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_research_narrative.py -q`
Expected: FAIL because the new module does not exist yet.


### Task 2: Implement `research_fact_sheet`

**Files:**
- Create: `src/stock_research/research_narrative.py`
- Test: `tests/test_research_narrative.py`

- [ ] **Step 1: Add the new module skeleton**

Create:

```python
from __future__ import annotations

from typing import Any

import pandas as pd


def build_research_fact_sheet_from_frames(... ) -> pd.DataFrame:
    ...


def build_research_decision_narrative_from_fact_sheet(... ) -> pd.DataFrame:
    ...
```

- [ ] **Step 2: Implement fact-sheet normalization and mapping**

Implement minimal helpers such as:

```python
def _normalize_research_inputs(... ) -> pd.DataFrame:
    ...


def _build_fact_sheet_rows(... ) -> pd.DataFrame:
    ...
```

Required fact-sheet fields for v1:
- identifiers: `asset_id`, `ts_code`, `stock_name`, `trade_date`
- coverage/quality:
  - `report_count_90d`
  - `broker_coverage_count`
  - `latest_rating`
  - `target_price_median`
  - `target_upside_median`
  - `profit_forecast_count`
  - `pdf_risk_section_count`
  - `research_support_score`
  - `research_confidence`
- bull facts:
  - `bull_case_summary`
  - `key_growth_driver`
  - `institution_consensus_note`
  - `positive_rating_summary`
  - `target_price_basis_note`
- bear facts:
  - `bear_case_summary`
  - `key_risk_driver`
  - `negative_research_note`
  - `institution_disagreement_note`
  - `risk_summary_compact`
- industry/company:
  - `industry_position_note`
  - `product_position_note`
  - `moat_or_scarcity_note`
  - `industry_mainline_context`
  - `theme_alignment_note`
- assumption/valuation:
  - `analyst_core_assumption`
  - `valuation_anchor_note`
  - `expectation_dependency_note`
- completeness flags:
  - `has_target_price`
  - `has_profit_forecast`
  - `has_industry_position`
  - `has_product_position`
  - `has_moat_note`
  - `has_bull_case`
  - `has_bear_case`

- [ ] **Step 3: Run tests to verify fact-sheet behavior**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_research_narrative.py -k "fact_sheet or replay_filters" -q`
Expected: PASS for fact-sheet tests, with narrative test still red or incomplete if not implemented yet.


### Task 3: Implement `research_decision_narrative`

**Files:**
- Modify: `src/stock_research/research_narrative.py`
- Test: `tests/test_research_narrative.py`

- [ ] **Step 1: Add deterministic synthesis helpers**

Implement helpers such as:

```python
def _build_support_facts(row: pd.Series) -> list[str]:
    ...


def _build_oppose_facts(row: pd.Series) -> list[str]:
    ...


def _narrative_quality_flag(row: pd.Series) -> str:
    ...
```

- [ ] **Step 2: Build narrative output rows**

Implement these v1 fields:
- `one_line_judgment`
- `support_fact_1`
- `support_fact_2`
- `support_fact_3`
- `oppose_fact_1`
- `oppose_fact_2`
- `watch_point`
- `falsification_condition`
- `what_is_working_summary`
- `industry_position_summary`
- `institution_view_summary`
- `valuation_summary`
- `risk_summary`
- `decision_confidence`
- `narrative_quality_flag`

Rules:
- deterministic only
- facts must trace to upstream fields
- degrade to `信息不足，需补充` when necessary

- [ ] **Step 3: Run full narrative tests**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_research_narrative.py -q`
Expected: PASS


### Task 4: Integrate `research_narrative` into `mid_trend_position_dossier`

**Files:**
- Modify: `src/stock_research/mid_trend_position_dossier.py`
- Modify: `tests/test_mid_trend_position_dossier.py`
- Test: `tests/test_research_narrative.py`
- Test: `tests/test_mid_trend_position_dossier.py`

- [ ] **Step 1: Replace ad hoc holding narrative derivation**

Update dossier to consume:

```python
fact_sheet = build_research_fact_sheet_from_frames(...)
narrative = build_research_decision_narrative_from_fact_sheet(fact_sheet)
```

Then join the narrative back into holdings/candidate rows for rendering.

- [ ] **Step 2: Keep dossier surface stable**

Do not change:
- CLI command shape
- output filenames
- CSV summary schema unless required to populate existing fields better

But do improve the dossier text by using:
- `one_line_judgment`
- `support_fact_*`
- `oppose_fact_*`
- `watch_point`
- `falsification_condition`
- `industry_position_summary`
- `institution_view_summary`

- [ ] **Step 3: Run focused integration tests**

Run:
`cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_research_narrative.py tests/test_mid_trend_position_dossier.py -q`
Expected: PASS


### Task 5: Refresh real dossier artifact and run full regression

**Files:**
- Modify: `src/stock_research/research_narrative.py`
- Modify: `src/stock_research/mid_trend_position_dossier.py`
- Modify: `tests/test_research_narrative.py`
- Modify: `tests/test_mid_trend_position_dossier.py`

- [ ] **Step 1: Generate a real dossier artifact**

Run:

```bash
cd /Users/xiwei/stock_research && PYTHONPATH=/Users/xiwei/stock_research/src .venv/bin/python -m stock_research.cli build-mid-trend-position-dossier \
  --trade-date 2026-06-02 \
  --mode replay \
  --portfolio-review-path outputs/research/mid_trend_portfolio_review_20260604_current_holdings/mid_trend_portfolio_review_2026-06-02.csv \
  --research-packet-path outputs/research/mid_trend_research_packet_20260602_pdf_enriched/mid_trend_research_packet_candidates.csv \
  --output-dir outputs/research/mid_trend_position_dossier_20260602
```

Expected: dossier regenerates with deeper fact/narrative content.

- [ ] **Step 2: Run full regression suite**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest -q`
Expected: PASS
