# News Title Semantic Classification v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic title-level news semantic categories and use them to generate more readable TopN news summaries without changing source adapters, schemas, or strategy scoring.

**Architecture:** Extend `news_features.py` with four new 3-day title-count fields derived from keyword buckets, then teach `topn_news_enrichment.py` to prioritize those category counts when composing dossier-facing summaries. Keep missing-coverage semantics unchanged: unmatched candidates still stay `unknown` with empty summaries.

**Tech Stack:** Python, pandas, pytest

---

### Task 1: Add semantic category counts to daily news features

**Files:**
- Modify: `src/stock_research/news_features.py`
- Test: `tests/test_news_features.py`

- [ ] **Step 1: Write failing tests for title semantic category counts**

Add tests in `tests/test_news_features.py` that build a tiny mentions frame and assert `build_news_feature_daily(...)` produces the new fields:

```python
def test_build_news_feature_daily_counts_title_semantic_categories() -> None:
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "evt-1",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 09:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "主力资金抢筹 生益科技获融资客加仓",
                "content": "",
            },
            {
                "source_event_id": "evt-2",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 10:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "澎湃新闻",
                "title": "券商推荐 生益科技进入6月金股名单",
                "content": "",
            },
            {
                "source_event_id": "evt-3",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 11:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "生益科技订单突破 景气度提升",
                "content": "",
            },
            {
                "source_event_id": "evt-4",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2026-06-02",
                "published_at": "2026-06-02 13:10:00",
                "source_name": "akshare_stock_news_em",
                "source_channel": "证券时报网",
                "title": "生益科技风险提示：监管问询与减持压力",
                "content": "",
            },
        ]
    )

    features = build_news_feature_daily(
        mentions=mentions,
        trade_dates=["2026-06-02"],
        mode="replay",
    )

    assert features.loc[0, "headline_capital_flow_count_3d"] == 1
    assert features.loc[0, "headline_broker_reco_count_3d"] == 1
    assert features.loc[0, "headline_business_catalyst_count_3d"] == 1
    assert features.loc[0, "headline_risk_event_count_3d"] == 1
```

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_news_features.py -q
```

Expected:
- FAIL because the new category columns do not exist yet.

- [ ] **Step 3: Implement the semantic category fields**

In `src/stock_research/news_features.py`:

1. Extend `NEWS_FEATURE_COLUMNS` with:

```python
"headline_capital_flow_count_3d",
"headline_broker_reco_count_3d",
"headline_business_catalyst_count_3d",
"headline_risk_event_count_3d",
```

2. Add deterministic keyword tuples:

```python
CAPITAL_FLOW_HEADLINE_KEYWORDS = (
    "主力",
    "资金",
    "抢筹",
    "加仓",
    "融资",
    "融资客",
    "杠杆",
)

BROKER_RECO_HEADLINE_KEYWORDS = (
    "券商",
    "金股",
    "推荐",
    "看好",
    "评级",
    "上调",
    "增持",
)

BUSINESS_CATALYST_HEADLINE_KEYWORDS = (
    "订单",
    "中标",
    "新品",
    "景气",
    "扩产",
    "突破",
    "签约",
)

RISK_EVENT_HEADLINE_KEYWORDS = (
    "风险",
    "减持",
    "监管",
    "诉讼",
    "亏损",
    "停牌",
    "问询",
)
```

3. In `build_news_feature_daily(...)`, derive counts from `title_3d`:

```python
capital_flow_count = int(
    title_3d.map(lambda text: _contains_keyword(text, CAPITAL_FLOW_HEADLINE_KEYWORDS)).astype(int).sum()
)
broker_reco_count = int(
    title_3d.map(lambda text: _contains_keyword(text, BROKER_RECO_HEADLINE_KEYWORDS)).astype(int).sum()
)
business_catalyst_count = int(
    title_3d.map(lambda text: _contains_keyword(text, BUSINESS_CATALYST_HEADLINE_KEYWORDS)).astype(int).sum()
)
risk_event_count = int(
    title_3d.map(lambda text: _contains_keyword(text, RISK_EVENT_HEADLINE_KEYWORDS)).astype(int).sum()
)
```

4. Add those values to the emitted row dict.

- [ ] **Step 4: Run the focused test to verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_news_features.py -q
```

Expected:
- PASS

### Task 2: Use semantic categories in TopN enrichment summaries

**Files:**
- Modify: `src/stock_research/topn_news_enrichment.py`
- Test: `tests/test_topn_news_enrichment.py`

- [ ] **Step 1: Write failing tests for semantic-summary priority**

Add tests in `tests/test_topn_news_enrichment.py` covering priority and fallback:

```python
def test_build_topn_news_enrichment_prefers_broker_reco_summary() -> None:
    candidates = pd.DataFrame(
        [{"asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技", "trade_date": "2026-06-02"}]
    )
    features = pd.DataFrame(
        [{
            "trade_date": "2026-06-02",
            "asset_id": "CN:SH:600183",
            "news_attention_level": "low",
            "headline_broker_reco_count_3d": 1,
            "headline_capital_flow_count_3d": 0,
            "headline_business_catalyst_count_3d": 0,
            "headline_risk_event_count_3d": 0,
        }]
    )

    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert enriched.loc[0, "news_consensus_summary"] == "近3日券商推荐类新闻1条，关注度low"
    assert enriched.loc[0, "theme_catalyst_summary"] == "近3日券商催化类新闻1条"
```

Add similar focused tests for:
- `capital_flow`
- `business_catalyst`
- `risk_event`
- fallback when feature exists but all category counts are zero

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_topn_news_enrichment.py -q
```

Expected:
- FAIL because semantic category columns are ignored today.

- [ ] **Step 3: Implement semantic summary priority**

In `src/stock_research/topn_news_enrichment.py`:

1. Read the four new feature columns safely with the existing int-normalization path.
2. Apply summary priority exactly as specified in the design:

```python
if broker_reco_count > 0:
    news_consensus_summary = f"近3日券商推荐类新闻{broker_reco_count}条，关注度{attention_level}"
elif capital_flow_count > 0:
    news_consensus_summary = f"近3日资金关注类新闻{capital_flow_count}条，关注度{attention_level}"
elif business_catalyst_count > 0:
    news_consensus_summary = f"近3日经营催化类新闻{business_catalyst_count}条，关注度{attention_level}"
elif has_news_feature:
    news_consensus_summary = f"近3日未见明显正向新闻，关注度{attention_level}"
else:
    news_consensus_summary = ""
```

Similarly implement:

```python
if risk_event_count > 0:
    news_risk_summary = f"近3日风险事件类新闻{risk_event_count}条"
elif has_news_feature:
    news_risk_summary = "近3日未见风险关键词新闻"
else:
    news_risk_summary = ""
```

And:

```python
if business_catalyst_count > 0:
    theme_catalyst_summary = f"近3日经营/主题催化新闻{business_catalyst_count}条"
elif broker_reco_count > 0:
    theme_catalyst_summary = f"近3日券商催化类新闻{broker_reco_count}条"
elif capital_flow_count > 0:
    theme_catalyst_summary = f"近3日资金关注类新闻{capital_flow_count}条"
elif has_news_feature:
    theme_catalyst_summary = "近3日未见重大/主线催化新闻"
else:
    theme_catalyst_summary = ""
```

3. Preserve current behavior for unmatched candidates:
- `news_attention_level = unknown`
- empty summaries
- `news_risk_attention_flag = None`

- [ ] **Step 4: Run the focused test to verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_topn_news_enrichment.py -q
```

Expected:
- PASS

### Task 3: Verify the combined news chain and refresh real artifacts

**Files:**
- Inspect: `outputs/research/public_news_fallback_20260602_refresh/...`

- [ ] **Step 1: Run the combined focused suite**

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

- [ ] **Step 2: Refresh the real fallback chain for `2026-06-02`**

Run:

```bash
PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  topn-news-source-backfill \
  --candidates-path /Users/xiwei/stock_research/outputs/research/mid_trend_research_packet_20260602_pdf_enriched/mid_trend_research_packet_candidates.csv \
  --provider akshare_stock_news_em \
  --trade-date 2026-06-02 \
  --output-dir /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260602_refresh_v2/source
```

Then:

```bash
PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  news-feature-backfill \
  --events-path /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260602_refresh_v2/source/news_source_backfill_events.csv \
  --start-date 2026-06-01 \
  --end-date 2026-06-02 \
  --mode replay \
  --output-dir /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260602_refresh_v2/features
```

Then:

```bash
PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  topn-news-enrichment \
  --candidates-path /Users/xiwei/stock_research/outputs/research/mid_trend_research_packet_20260602_pdf_enriched/mid_trend_research_packet_candidates.csv \
  --news-features-path /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260602_refresh_v2/features/news_feature_daily.csv \
  --output-dir /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260602_refresh_v2/enrichment
```

Then:

```bash
PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  build-mid-trend-position-dossier \
  --trade-date 2026-06-02 \
  --mode replay \
  --portfolio-review-path /Users/xiwei/stock_research/outputs/research/mid_trend_portfolio_review_20260604_current_holdings/mid_trend_portfolio_review_2026-06-02.csv \
  --research-packet-path /Users/xiwei/stock_research/outputs/research/mid_trend_research_packet_20260602_pdf_enriched/mid_trend_research_packet_candidates.csv \
  --news-enrichment-path /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260602_refresh_v2/enrichment/topn_news_enrichment.csv \
  --output-dir /Users/xiwei/stock_research/outputs/research/public_news_fallback_20260602_refresh_v2/dossier
```

- [ ] **Step 3: Inspect the refreshed artifacts**

Confirm the refreshed enrichment or dossier now uses category-specific summaries such as:

- `近3日资金关注类新闻1条，关注度low`
- `近3日券商推荐类新闻1条，关注度low`
- `近3日经营/主题催化新闻1条`

instead of only the generic quiet fallback wording.
