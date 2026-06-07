# Mid Trend Portfolio Review Evidence Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve `mid_trend_portfolio_review` so stock names fall back to proper Chinese names more reliably and evidence fields are auto-derived from structured data when research packet text is blank.

**Architecture:** Keep the existing report builder intact and add two small internal helpers inside `mid_trend_portfolio_review.py`: one for stock name resolution and one for evidence synthesis. Reuse existing placeholder-name semantics already used elsewhere in the repo, and keep research-packet-authored evidence as the highest-priority source.

**Tech Stack:** Python, pandas, pytest

---

### Task 1: Stock Name Resolution Fallback

**Files:**
- Modify: `src/stock_research/mid_trend_portfolio_review.py`
- Test: `tests/test_mid_trend_portfolio_review.py`

- [ ] **Step 1: Write the failing test**

```python
def test_portfolio_review_backfills_placeholder_stock_name_from_research_or_ts_code_lookup() -> None:
    top10 = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:688301",
                "ts_code": "688301.SH",
                "stock_name": "CN:SH:688301",
                "shadow_top10_rank": 1,
            }
        ]
    )
    research = pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:688301",
                "ts_code": "688301.SH",
                "stock_name": "奕瑞科技",
            }
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=pd.DataFrame(),
        trades=pd.DataFrame(),
        research_packet_candidates=research,
    )

    assert result["review_rows"].loc[0, "stock_name"] == "奕瑞科技"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_portfolio_review.py::test_portfolio_review_backfills_placeholder_stock_name_from_research_or_ts_code_lookup -q`
Expected: FAIL because placeholder stock name is not replaced.

- [ ] **Step 3: Write minimal implementation**

```python
def _is_placeholder_stock_name(name: Any, asset_id: Any, ts_code: Any) -> bool:
    ...


def _resolve_review_stock_name(*, top10_name: Any, research_name: Any, asset_id: Any, ts_code: Any) -> str:
    ...
```

Use `_resolve_review_stock_name(...)` in `_build_review_rows()` so placeholder values such as `CN:SH:688301`, bare code, or `688301` do not survive when a better Chinese name exists.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_portfolio_review.py::test_portfolio_review_backfills_placeholder_stock_name_from_research_or_ts_code_lookup -q`
Expected: PASS


### Task 2: Positive/Risk Evidence Auto-Synthesis

**Files:**
- Modify: `src/stock_research/mid_trend_portfolio_review.py`
- Test: `tests/test_mid_trend_portfolio_review.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_portfolio_review_derives_positive_evidence_from_structured_fields_when_blank() -> None:
    ...
    assert "主线环境" in review_row["main_positive_evidence"]
    assert "研报/PDF覆盖" in review_row["main_positive_evidence"]


def test_portfolio_review_derives_risk_evidence_from_structured_fields_when_blank() -> None:
    ...
    assert "硬风险" in review_row["main_risk_evidence"]
    assert "风险段" in review_row["main_risk_evidence"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_portfolio_review.py -k "derives_positive_evidence or derives_risk_evidence" -q`
Expected: FAIL because current implementation only passes through research packet text.

- [ ] **Step 3: Write minimal implementation**

```python
def _derive_positive_evidence(... ) -> str:
    ...


def _derive_risk_evidence(... ) -> str:
    ...
```

Rules:
- Keep research-packet-authored evidence if present.
- Otherwise build short evidence strings from:
  - `market_regime`, `mainline_status`, `mid_trend_layer`, `mid_trend_funnel_score`
  - `research_support_score_pit`, `broker_report_count_90d`, `pdf_target_price_count_90d`, `pdf_profit_forecast_count_90d`
  - `fundamental_hard_risk`, `pdf_risk_section_count_90d`, `latest_pdf_risk_summary`
- Keep outputs short, evidence-based, and deterministic.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_portfolio_review.py -k "derives_positive_evidence or derives_risk_evidence" -q`
Expected: PASS


### Task 3: Regression Verification

**Files:**
- Modify: `tests/test_mid_trend_portfolio_review.py`

- [ ] **Step 1: Run targeted suite**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_portfolio_review.py -q`
Expected: PASS

- [ ] **Step 2: Run real smoke generation for 2026-06-01**

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

Expected: report regenerates successfully and previously ugly fallback names/evidence text improve where structured inputs exist.

- [ ] **Step 3: Run full regression suite**

Run: `cd /Users/xiwei/stock_research && .venv/bin/pytest -q`
Expected: PASS
