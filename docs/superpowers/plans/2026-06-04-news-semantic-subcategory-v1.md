# News Semantic Subcategory v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine the existing deterministic news semantic layer with title-level subcategories so TopN enrichment and dossier outputs become more specific while keeping the current 3-day primary window and existing public-news pipeline intact.

**Architecture:** Extend `news_features.py` with 3-day subcategory count fields under the existing four semantic buckets, then update `topn_news_enrichment.py` to prefer subcategory-specific wording before falling back to the current category-level summaries and finally to the quiet fallback. Keep `3d` as the only summary window in this phase; `5d` remains a future display-layer extension.

**Tech Stack:** Python, pandas, pytest

---

### Task 1: Add title-level semantic subcategory counts

**Files:**
- Modify: `src/stock_research/news_features.py`
- Test: `tests/test_news_features.py`

- [ ] **Step 1: Write failing tests for subcategory count fields**

Add focused tests in `tests/test_news_features.py` for at least:

- `main_force_flow`
- `margin_flow`
- `gold_stock`
- `rating_action`
- `broker_positive_view`
- `order_bid`
- `product_breakthrough`
- `industry_boom`
- `regulatory_inquiry`
- `shareholder_reduction`
- `litigation_penalty`
- `loss_warning`

Each test should build a minimal `mentions` frame and assert the corresponding `headline_*_count_3d` field equals `1`.

- [ ] **Step 2: Verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_news_features.py -q
```

Expected:
- FAIL because the new subcategory count columns do not exist yet.

- [ ] **Step 3: Implement subcategory fields in `news_features.py`**

Add to `NEWS_FEATURE_COLUMNS`:

```python
"headline_main_force_flow_count_3d",
"headline_margin_flow_count_3d",
"headline_capital_flow_generic_count_3d",
"headline_gold_stock_count_3d",
"headline_rating_action_count_3d",
"headline_broker_positive_view_count_3d",
"headline_order_bid_count_3d",
"headline_product_breakthrough_count_3d",
"headline_industry_boom_count_3d",
"headline_regulatory_inquiry_count_3d",
"headline_shareholder_reduction_count_3d",
"headline_litigation_penalty_count_3d",
"headline_loss_warning_count_3d",
```

Add deterministic keyword tuples in `news_features.py` per the spec and compute each count from `title_3d`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_news_features.py -q
```

Expected:
- PASS

### Task 2: Prefer subcategory wording in TopN news enrichment

**Files:**
- Modify: `src/stock_research/topn_news_enrichment.py`
- Test: `tests/test_topn_news_enrichment.py`

- [ ] **Step 1: Write failing tests for subcategory-priority summaries**

Add focused tests for:

- `gold_stock` -> `近3日券商金股/推荐新闻X条，关注度{attention}`
- `rating_action` -> `近3日评级/目标价新闻X条，关注度{attention}`
- `broker_positive_view` -> `近3日券商看好类新闻X条，关注度{attention}`
- `main_force_flow` -> `近3日主力资金关注新闻X条，关注度{attention}`
- `margin_flow` -> `近3日融资/杠杆资金新闻X条，关注度{attention}`
- `capital_flow_generic` -> `近3日资金关注类新闻X条，关注度{attention}`
- `order_bid` -> `近3日订单/中标新闻X条，关注度{attention}`
- `product_breakthrough` -> `近3日新品/突破新闻X条，关注度{attention}`
- `industry_boom` -> `近3日行业景气新闻X条，关注度{attention}`
- `regulatory_inquiry` -> `近3日监管问询/风险提示新闻X条`
- `shareholder_reduction` -> `近3日减持类风险新闻X条`
- `litigation_penalty` -> `近3日诉讼/处罚类风险新闻X条`
- `loss_warning` -> `近3日亏损/业绩风险新闻X条`

Also keep coverage for:

- no coverage => blank summaries + `unknown`
- covered quiet fallback
- mixed-schema rows
- dirty subcategory values

- [ ] **Step 2: Verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_topn_news_enrichment.py -q
```

Expected:
- FAIL because the subcategory columns are ignored today.

- [ ] **Step 3: Implement subcategory summary priority**

In `topn_news_enrichment.py`:

1. Add subcategory field names and safe parsing.
2. Keep semantic mode and dirty-value handling from the current category-level implementation.
3. Replace category-level wording priority with subcategory-level priority per the spec.
4. If no subcategory hits but the row is still a semantic row, fall back to the current category-level summary logic or quiet fallback as appropriate.
5. Keep `overnight_catalyst_note` semantics unchanged.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_topn_news_enrichment.py -q
```

Expected:
- PASS

### Task 3: Refresh focused verification and real artifacts

**Files:**
- Inspect: `outputs/research/public_news_fallback_20260602_refresh_v3/...`

- [ ] **Step 1: Run the focused suite**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  /Users/xiwei/stock_research/tests/test_news_source_backfill.py \
  /Users/xiwei/stock_research/tests/test_news_features.py \
  /Users/xiwei/stock_research/tests/test_topn_news_enrichment.py \
  /Users/xiwei/stock_research/tests/test_mid_trend_position_dossier.py \
  /Users/xiwei/stock_research/tests/test_public_news_fallback_adapter.py -q
```

Expected:
- PASS

- [ ] **Step 2: Refresh the real `2026-06-02` public fallback chain**

Run in order:

```bash
PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  topn-news-source-backfill \
  --candidates-path /Users/xiwei/stock_research/outputs/research/mid_trend_research_packet_20260602_pdf_enriched/mid_trend_research_packet_candidates.csv \
  --provider akshare_stock_news_em \
  --trade-date 2026-06-02 \
  --output-dir /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260602_refresh_v3/source
```

```bash
PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  news-feature-backfill \
  --events-path /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260602_refresh_v3/source/news_source_backfill_events.csv \
  --start-date 2026-06-01 \
  --end-date 2026-06-02 \
  --mode replay \
  --output-dir /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260602_refresh_v3/features
```

```bash
PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  topn-news-enrichment \
  --candidates-path /Users/xiwei/stock_research/outputs/research/mid_trend_research_packet_20260602_pdf_enriched/mid_trend_research_packet_candidates.csv \
  --news-features-path /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260602_refresh_v3/features/news_feature_daily.csv \
  --output-dir /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260602_refresh_v3/enrichment
```

```bash
PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  build-mid-trend-position-dossier \
  --trade-date 2026-06-02 \
  --mode replay \
  --portfolio-review-path /Users/xiwei/stock_research/outputs/research/mid_trend_portfolio_review_20260604_current_holdings/mid_trend_portfolio_review_2026-06-02.csv \
  --research-packet-path /Users/xiwei/stock_research/outputs/research/mid_trend_research_packet_20260602_pdf_enriched/mid_trend_research_packet_candidates.csv \
  --news-enrichment-path /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260602_refresh_v3/enrichment/topn_news_enrichment.csv \
  --output-dir /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260602_refresh_v3/dossier
```

- [ ] **Step 3: Inspect output wording**

Confirm the refreshed enrichment/dossier uses more specific wording than v2, for example:

- `近3日主力资金关注新闻1条`
- `近3日券商金股/推荐新闻1条`
- `近3日评级/目标价新闻1条`
- `近3日订单/中标催化新闻1条`
- `近3日监管问询/风险提示新闻1条`
