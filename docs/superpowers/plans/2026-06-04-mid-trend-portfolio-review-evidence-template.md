# Mid Trend Portfolio Review Evidence Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four structured evidence categories to `mid_trend_portfolio_review` while preserving the current report outputs and label logic.

**Architecture:** Extend `review_rows` in `mid_trend_portfolio_review.py` with four evidence groups: trend, research, risk, and rebalance. Each group exposes tags, raw values, and a summary string. Existing `main_positive_evidence` and `main_risk_evidence` become display-layer aggregations built from the new summary fields.

**Tech Stack:** Python, pandas, pytest

---

### Task 1: Add failing tests for structured evidence fields

**Files:**
- Modify: `tests/test_mid_trend_portfolio_review.py`
- Test: `tests/test_mid_trend_portfolio_review.py`

- [ ] **Step 1: Write the failing tests**

Add tests that assert:

```python
def test_portfolio_review_emits_structured_evidence_fields() -> None:
    ...
    assert row["trend_market_regime_tag"] == "mainline"
    assert row["research_support_band_tag"] == "high_support"
    assert row["risk_research_gap_tag"] == "supported"
    assert row["rebalance_action_tag"] == "hold_no_trade"


def test_portfolio_review_emits_rebalance_evidence_on_holding_day() -> None:
    ...
    assert row["rebalance_reason_evidence_summary"] != ""


def test_portfolio_review_aggregates_main_evidence_from_new_summaries() -> None:
    ...
    assert "主线环境" in row["main_positive_evidence"]
    assert "研报/PDF覆盖" in row["main_positive_evidence"]
    assert "动作:" in row["main_risk_evidence"] or "风险段:" in row["main_risk_evidence"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_portfolio_review.py -k "structured_evidence_fields or rebalance_evidence_on_holding_day or aggregates_main_evidence" -q`
Expected: FAIL because the new fields do not exist yet.


### Task 2: Implement evidence tags, raw values, and summaries

**Files:**
- Modify: `src/stock_research/mid_trend_portfolio_review.py`
- Test: `tests/test_mid_trend_portfolio_review.py`

- [ ] **Step 1: Add minimal helper functions**

Add helpers for:

```python
def _build_trend_evidence(... ) -> dict[str, Any]:
    ...


def _build_research_evidence(... ) -> dict[str, Any]:
    ...


def _build_risk_evidence(... ) -> dict[str, Any]:
    ...


def _build_rebalance_evidence(... ) -> dict[str, Any]:
    ...
```

Each helper must return tags, raw values, and a summary string only from current report inputs.

- [ ] **Step 2: Wire evidence fields into `_build_review_rows()`**

Update the row assembly so each row includes:

```python
"trend_market_regime_tag": ...,
"trend_market_regime_value": ...,
"trend_evidence_summary": ...,
"research_support_band_tag": ...,
"research_support_score_value": ...,
"research_evidence_summary": ...,
"risk_fundamental_hard_risk_tag": ...,
"risk_evidence_summary": ...,
"rebalance_action_tag": ...,
"rebalance_reason_evidence_summary": ...,
```

- [ ] **Step 3: Rebuild legacy display fields from evidence summaries**

Set:

```python
"main_positive_evidence": _join_nonempty([
    trend_evidence["trend_evidence_summary"],
    research_evidence["research_evidence_summary"],
]),
"main_risk_evidence": _join_nonempty([
    risk_evidence["risk_evidence_summary"],
    rebalance_evidence["rebalance_reason_evidence_summary"],
]),
```

Do not change `final_label`.

- [ ] **Step 4: Run targeted tests to verify they pass**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_portfolio_review.py -k "structured_evidence_fields or rebalance_evidence_on_holding_day or aggregates_main_evidence" -q`
Expected: PASS


### Task 3: Regression verification and real artifact refresh

**Files:**
- Modify: `src/stock_research/mid_trend_portfolio_review.py`
- Modify: `tests/test_mid_trend_portfolio_review.py`

- [ ] **Step 1: Run the full module test file**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_portfolio_review.py -q`
Expected: PASS

- [ ] **Step 2: Regenerate the 2026-06-01 real report**

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

Expected: report rebuilds with new evidence columns in CSV and unchanged command surface.

- [ ] **Step 3: Run full regression suite**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest -q`
Expected: PASS
