# News Compact Summary v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic one-line `news_compact_summary` that combines multiple 3-day news subcategories into a more human-readable sentence, and surface it at the top of the dossier news block.

**Architecture:** Extend `topn_news_enrichment.py` with one additional computed field driven entirely by existing subcategory hits, then expose that field in `mid_trend_position_dossier.py` without changing any existing source/feature logic. The compact summary sits above the existing structured news fields; it does not replace them.

**Tech Stack:** Python, pandas, pytest

---

### Task 1: Add `news_compact_summary` composition to TopN news enrichment

**Files:**
- Modify: `src/stock_research/topn_news_enrichment.py`
- Test: `tests/test_topn_news_enrichment.py`

- [ ] **Step 1: Write failing tests for compact summary composition**

Add focused tests in `tests/test_topn_news_enrichment.py` for:

1. `资金 + 券商` 共振
   - expected: `近3日主力资金关注 + 券商金股推荐共振`

2. `经营催化 + 资金`
   - expected: `近3日订单/中标催化 + 主力资金关注`

3. `风险但无催化`
   - expected: `近3日监管问询但无新增催化`

4. 单一子类
   - expected: `近3日主力资金关注`

5. covered quiet
   - expected: `近3日无明显新增催化`

6. no coverage
   - expected: `news_compact_summary == ""`

- [ ] **Step 2: Verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_topn_news_enrichment.py -q
```

Expected:
- FAIL because `news_compact_summary` does not exist yet.

- [ ] **Step 3: Implement compact summary field and composition rules**

In `src/stock_research/topn_news_enrichment.py`:

1. Add `news_compact_summary` to `TOPN_NEWS_ENRICHMENT_COLUMNS`.
2. Add deterministic subtype -> phrase mapping.
3. Compose according to the approved priority:
   - positive resonance
   - catalyst + capital
   - risk without new catalyst
   - single subtype
   - covered quiet
   - no coverage blank

Keep all existing summary fields and missing-coverage semantics unchanged.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_topn_news_enrichment.py -q
```

Expected:
- PASS

### Task 2: Render the compact summary in dossier news blocks

**Files:**
- Modify: `src/stock_research/mid_trend_position_dossier.py`
- Test: `tests/test_mid_trend_position_dossier.py`

- [ ] **Step 1: Write failing test for dossier rendering**

Add a focused test ensuring the news block now includes:

```text
- 新闻/催化跟踪
  - 新闻短摘要：...
```

And that it appears before:

- `新闻关注度`
- `新闻共识`
- `新闻风险`

- [ ] **Step 2: Verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_mid_trend_position_dossier.py -q
```

Expected:
- FAIL because the dossier does not render the compact summary yet.

- [ ] **Step 3: Implement dossier display**

In `src/stock_research/mid_trend_position_dossier.py`:

1. Extend news normalization to preserve `news_compact_summary`.
2. Update `_render_news_section(...)` so the first line inside the news block is:

```python
f"  - 新闻短摘要：{_render_news_text(row.get('news_compact_summary'))}"
```

3. Keep existing display lines intact after it.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_mid_trend_position_dossier.py -q
```

Expected:
- PASS

### Task 3: Focused verification and refreshed real artifacts

**Files:**
- Inspect: `outputs/research/public_news_fallback_20260605_compact/...`

- [ ] **Step 1: Run focused verification**

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
  --output-dir /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260605_compact/source
```

```bash
PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  news-feature-backfill \
  --events-path /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260605_compact/source/news_source_backfill_events.csv \
  --start-date 2026-06-01 \
  --end-date 2026-06-02 \
  --mode replay \
  --output-dir /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260605_compact/features
```

```bash
PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  topn-news-enrichment \
  --candidates-path /Users/xiwei/stock_research/outputs/research/mid_trend_research_packet_20260602_pdf_enriched/mid_trend_research_packet_candidates.csv \
  --news-features-path /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260605_compact/features/news_feature_daily.csv \
  --output-dir /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260605_compact/enrichment
```

```bash
PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  build-mid-trend-position-dossier \
  --trade-date 2026-06-02 \
  --mode replay \
  --portfolio-review-path /Users/xiwei/stock_research/outputs/research/mid_trend_portfolio_review_20260604_current_holdings/mid_trend_portfolio_review_2026-06-02.csv \
  --research-packet-path /Users/xiwei/stock_research/outputs/research/mid_trend_research_packet_20260602_pdf_enriched/mid_trend_research_packet_candidates.csv \
  --news-enrichment-path /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260605_compact/enrichment/topn_news_enrichment.csv \
  --output-dir /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260605_compact/dossier
```

- [ ] **Step 3: Inspect the refreshed wording**

Confirm the real dossier now contains one-line summaries such as:

- `近3日主力资金关注 + 券商金股推荐共振`
- `近3日监管问询但无新增催化`
- `近3日无明显新增催化`
