# Historical News Replacement Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unusable `2025-01..present` historical media-news source with a replay-safe historical source chain built from Eastmoney individual notices, Eastmoney research reports, and CNInfo disclosure announcements while preserving the existing near-end `stock_news_em` path.

**Architecture:** Keep the current near-end media-news pipeline unchanged for `T-3/T-5` dossier overlays. Extend the source layer with three historical providers that normalize into the existing source-event contract plus a new `event_family` field, then add deterministic family-aware feature columns and historical backfill routing so `Top10 historical news backfill` can produce non-empty replay artifacts for `2025-01-01..2026-05-19`.

**Tech Stack:** Python, pandas, existing AKShare adapters, existing CLI/subparser framework, pytest.

---

## File Structure

### Existing files to modify

- `src/stock_research/news_source_backfill.py`
  - Add provider-specific collectors for:
    - `eastmoney_individual_notice`
    - `eastmoney_research_report`
    - `cninfo_disclosure_announcement`
  - Add `event_family` to normalized source rows.
  - Extend historical backfill runner to accept multiple historical providers.

- `src/stock_research/news_features.py`
  - Preserve current near-end media logic.
  - Add deterministic family-aware feature columns for notice/report events.

- `src/stock_research/topn_news_enrichment.py`
  - Consume historical notice/report feature fields without disturbing current media-news summaries.
  - Add small, readable historical summaries for notice/report evidence.

- `src/stock_research/cli.py`
  - Extend `historical-top10-news-backfill` to accept the replacement provider set.

- `tests/test_news_source_backfill.py`
  - Add provider normalization tests for the three historical providers.

- `tests/test_public_news_fallback_adapter.py`
  - Add historical runner tests for multi-provider replacement source mode.

- `tests/test_news_features.py`
  - Add family-aware feature aggregation tests.

- `tests/test_topn_news_enrichment.py`
  - Add notice/report summary tests.

### New files to create

- None required in phase 1. Keep source adapters inside `news_source_backfill.py` unless the file becomes unreadable during implementation.

## Task 1: Add Historical Provider Normalizers

**Files:**
- Modify: `src/stock_research/news_source_backfill.py`
- Test: `tests/test_news_source_backfill.py`

- [ ] **Step 1: Write failing normalization tests for the three historical providers**

Add tests that assert normalized rows contain `event_family`, provider-specific `source_name`, stable `published_at`, and provider metadata.

```python
def test_normalize_eastmoney_individual_notice_rows():
    rows = [
        {
            "代码": "600183",
            "名称": "生益科技",
            "公告标题": "生益科技:2024年年度业绩预增公告",
            "公告类型": "业绩预告",
            "公告日期": "2025-01-24",
            "网址": "https://data.eastmoney.com/notices/detail/600183/AN1.html",
        }
    ]

    events = normalize_historical_source_rows(
        rows=rows,
        provider="eastmoney_individual_notice",
        asset_id="CN:SH:600183",
        ts_code="600183.SH",
        stock_name="生益科技",
    )

    assert events.iloc[0]["source_name"] == "eastmoney_individual_notice"
    assert events.iloc[0]["event_family"] == "disclosure_notice"
    assert events.iloc[0]["published_at"].startswith("2025-01-24")
```

```python
def test_normalize_eastmoney_research_report_rows():
    rows = [
        {
            "股票代码": "600183",
            "股票简称": "生益科技",
            "报告名称": "产品结构优化，业绩爆发式增长",
            "东财评级": "买入",
            "机构": "太平洋",
            "日期": "2025-05-27",
            "报告PDF链接": "https://pdf.dfcfw.com/pdf/abc.pdf",
        }
    ]

    events = normalize_historical_source_rows(
        rows=rows,
        provider="eastmoney_research_report",
        asset_id="CN:SH:600183",
        ts_code="600183.SH",
        stock_name="生益科技",
    )

    assert events.iloc[0]["source_name"] == "eastmoney_research_report"
    assert events.iloc[0]["event_family"] == "institution_report"
    assert events.iloc[0]["title"] == "产品结构优化，业绩爆发式增长"
```

```python
def test_normalize_cninfo_disclosure_rows():
    rows = [
        {
            "代码": "600183",
            "简称": "生益科技",
            "公告标题": "生益科技2024年年度业绩预增公告",
            "公告时间": "2025-01-24",
            "公告链接": "http://www.cninfo.com.cn/new/disclosure/detail?announcementId=1&orgId=2",
        }
    ]

    events = normalize_historical_source_rows(
        rows=rows,
        provider="cninfo_disclosure_announcement",
        asset_id="CN:SH:600183",
        ts_code="600183.SH",
        stock_name="生益科技",
    )

    assert events.iloc[0]["source_name"] == "cninfo_disclosure_announcement"
    assert events.iloc[0]["event_family"] == "disclosure_notice"
```

- [ ] **Step 2: Run the focused test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_news_source_backfill.py -q
```

Expected:

- FAIL because `normalize_historical_source_rows` and/or `event_family` handling do not exist yet.

- [ ] **Step 3: Implement the minimal provider normalizers**

In `src/stock_research/news_source_backfill.py`, add:

```python
def normalize_historical_source_rows(
    *,
    rows: list[dict[str, object]],
    provider: str,
    asset_id: str,
    ts_code: str,
    stock_name: str,
) -> pd.DataFrame:
    provider_map = {
        "eastmoney_individual_notice": _normalize_eastmoney_individual_notice_rows,
        "eastmoney_research_report": _normalize_eastmoney_research_report_rows,
        "cninfo_disclosure_announcement": _normalize_cninfo_disclosure_rows,
    }
    return provider_map[provider](
        rows=rows,
        asset_id=asset_id,
        ts_code=ts_code,
        stock_name=stock_name,
    )
```

```python
def _normalize_eastmoney_individual_notice_rows(...):
    return pd.DataFrame(
        [
            {
                "source_event_id": f"eastmoney_notice::{ts_code}::{row['公告日期']}::{idx}",
                "source_name": "eastmoney_individual_notice",
                "event_family": "disclosure_notice",
                "source_channel": "eastmoney_notice",
                "title": row.get("公告标题", ""),
                "content": "",
                "published_at": f"{row.get('公告日期', '')} 00:00:00",
                "url": row.get("网址", ""),
                "language": "zh",
                "asset_id": asset_id,
                "ts_code": ts_code,
                "stock_name": stock_name,
                "metadata": {"notice_type": row.get("公告类型", "")},
            }
            for idx, row in enumerate(rows)
        ]
    )
```

- [ ] **Step 4: Run the focused test to verify pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_news_source_backfill.py -q
```

Expected:

- PASS for the three new normalization tests.

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/news_source_backfill.py tests/test_news_source_backfill.py
git commit -m "feat: add historical notice and report source normalizers"
```

## Task 2: Add Historical Provider Fetchers and Multi-Provider Dispatch

**Files:**
- Modify: `src/stock_research/news_source_backfill.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_public_news_fallback_adapter.py`

- [ ] **Step 1: Write failing runner tests for replacement providers**

Add tests that patch provider fetchers and assert historical backfill can combine multiple providers into one source-event frame.

```python
def test_historical_backfill_combines_notice_and_report_sources(tmp_path, monkeypatch):
    candidates = pd.DataFrame(
        [
            {"trade_date": "2025-01-24", "asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"},
        ]
    )
    top10_path = tmp_path / "top10.csv"
    candidates.to_csv(top10_path, index=False)

    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_historical_candidate_events",
        lambda **kwargs: pd.DataFrame(
            [
                {"source_name": "eastmoney_individual_notice", "event_family": "disclosure_notice", "title": "业绩预增公告"},
                {"source_name": "eastmoney_research_report", "event_family": "institution_report", "title": "产品结构优化，业绩爆发式增长"},
            ]
        ),
    )

    result = run_historical_top10_news_backfill(
        top10_path=top10_path,
        start_date="2025-01-24",
        end_date="2025-01-24",
        providers=["eastmoney_individual_notice", "eastmoney_research_report"],
        output_dir=tmp_path,
    )

    assert len(result["source_events"]) == 2
    assert set(result["source_events"]["event_family"]) == {"disclosure_notice", "institution_report"}
```

- [ ] **Step 2: Run the focused test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_public_news_fallback_adapter.py -q
```

Expected:

- FAIL because `providers=[...]` and multi-provider historical dispatch do not exist yet.

- [ ] **Step 3: Implement provider fetchers and CLI argument changes**

In `src/stock_research/news_source_backfill.py`, add small provider wrappers:

```python
def fetch_historical_candidate_events(
    *,
    provider: str,
    ts_code: str,
    stock_name: str,
    asset_id: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    if provider == "eastmoney_individual_notice":
        rows = ak.stock_individual_notice_report(
            security=ts_code.split(".")[0],
            begin_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        ).to_dict("records")
        return normalize_historical_source_rows(...)
    if provider == "eastmoney_research_report":
        rows = ak.stock_research_report_em(symbol=ts_code.split(".")[0]).to_dict("records")
        return normalize_historical_source_rows(...)
    if provider == "cninfo_disclosure_announcement":
        rows = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=ts_code.split(".")[0],
            market="沪深京",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        ).to_dict("records")
        return normalize_historical_source_rows(...)
    raise ValueError(f"unsupported historical provider: {provider}")
```

Extend `run_historical_top10_news_backfill(...)` to accept:

```python
providers: list[str]
```

and concatenate all provider frames per candidate/trade-date.

In `src/stock_research/cli.py`, replace the single provider flag with:

```python
historical_top10_news_backfill.add_argument(
    "--providers",
    nargs="+",
    default=["eastmoney_individual_notice", "eastmoney_research_report"],
)
```

- [ ] **Step 4: Run the focused tests to verify pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_public_news_fallback_adapter.py -q
```

Expected:

- PASS for the new multi-provider runner test and existing historical CLI tests.

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/news_source_backfill.py src/stock_research/cli.py tests/test_public_news_fallback_adapter.py
git commit -m "feat: add multi-provider historical news replacement dispatch"
```

## Task 3: Add Family-Aware Historical Features

**Files:**
- Modify: `src/stock_research/news_features.py`
- Test: `tests/test_news_features.py`

- [ ] **Step 1: Write failing feature tests for notice/report families**

Add tests that verify disclosure notices and institution reports aggregate into separate historical feature columns.

```python
def test_build_news_feature_daily_adds_notice_and_report_counts():
    mentions = pd.DataFrame(
        [
            {
                "source_event_id": "n1",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2025-01-24",
                "published_at": "2025-01-24 00:00:00",
                "source_name": "eastmoney_individual_notice",
                "source_channel": "eastmoney_notice",
                "title": "生益科技2024年年度业绩预增公告",
                "content": "",
                "event_family": "disclosure_notice",
            },
            {
                "source_event_id": "r1",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "mapping_method": "matched_candidate",
                "trade_date": "2025-01-24",
                "published_at": "2025-01-24 00:00:00",
                "source_name": "eastmoney_research_report",
                "source_channel": "eastmoney_research",
                "title": "产品结构优化，业绩爆发式增长",
                "content": "",
                "event_family": "institution_report",
            },
        ]
    )

    features = build_news_feature_daily(mentions=mentions, trade_dates=["2025-01-24"], mode="replay")

    row = features.iloc[0]
    assert row["notice_count_3d"] == 1
    assert row["research_report_count_20d"] == 1
```

- [ ] **Step 2: Run the focused test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_news_features.py -q
```

Expected:

- FAIL because the historical family-aware columns do not exist yet.

- [ ] **Step 3: Implement minimal family-aware feature columns**

In `src/stock_research/news_features.py`:

1. extend mention rows to preserve `event_family`
2. extend feature output columns with:

```python
HISTORICAL_EVENT_FEATURE_COLUMNS = [
    "notice_count_3d",
    "notice_count_10d",
    "risk_notice_count_20d",
    "earnings_notice_count_20d",
    "governance_notice_count_20d",
    "contract_investment_notice_count_20d",
    "research_report_count_20d",
    "rating_action_count_20d",
]
```

3. inside `build_news_feature_daily(...)`, derive windows using `event_family`, `source_name`, and title keywords:

```python
notice_20d = asset_rows.loc[
    (asset_rows["published_at"] >= trade_date - pd.Timedelta(days=19))
    & (asset_rows["event_family"] == "disclosure_notice")
]
report_20d = asset_rows.loc[
    (asset_rows["published_at"] >= trade_date - pd.Timedelta(days=19))
    & (asset_rows["event_family"] == "institution_report")
]
```

- [ ] **Step 4: Run the focused test to verify pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_news_features.py -q
```

Expected:

- PASS for the new historical family-aware feature tests and existing near-end media tests.

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/news_features.py tests/test_news_features.py
git commit -m "feat: add family-aware historical notice and report features"
```

## Task 4: Add Historical Summaries to TopN Enrichment

**Files:**
- Modify: `src/stock_research/topn_news_enrichment.py`
- Test: `tests/test_topn_news_enrichment.py`

- [ ] **Step 1: Write failing enrichment tests for historical summaries**

Add tests that verify notice/report features produce human-readable historical evidence without disturbing current media-news summaries.

```python
def test_build_topn_news_enrichment_adds_historical_notice_summary():
    candidates = pd.DataFrame(
        [{"trade_date": "2025-01-24", "asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"}]
    )
    news_features = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-24",
                "asset_id": "CN:SH:600183",
                "notice_count_3d": 1,
                "earnings_notice_count_20d": 1,
                "research_report_count_20d": 2,
                "rating_action_count_20d": 1,
                "news_attention_level": "unknown",
            }
        ]
    )

    result = build_topn_news_enrichment(candidates=candidates, news_features=news_features)

    row = result.iloc[0]
    assert row["historical_event_summary"] == "近20日有1条业绩类公告 + 2篇机构研报"
```

- [ ] **Step 2: Run the focused test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_topn_news_enrichment.py -q
```

Expected:

- FAIL because `historical_event_summary` and related logic do not exist yet.

- [ ] **Step 3: Implement minimal historical summaries**

In `src/stock_research/topn_news_enrichment.py`, add a separate historical summary lane:

```python
def _build_historical_event_summary(item) -> str:
    earnings_notice_count = _as_int(getattr(item, "earnings_notice_count_20d", 0))
    risk_notice_count = _as_int(getattr(item, "risk_notice_count_20d", 0))
    report_count = _as_int(getattr(item, "research_report_count_20d", 0))
    rating_action_count = _as_int(getattr(item, "rating_action_count_20d", 0))

    if earnings_notice_count > 0 and report_count > 0:
        return f"近20日有{earnings_notice_count}条业绩类公告 + {report_count}篇机构研报"
    if risk_notice_count > 0 and report_count == 0:
        return f"近20日有{risk_notice_count}条风险类公告，暂无新增机构研报"
    if report_count > 0 and rating_action_count > 0:
        return f"近20日有{report_count}篇机构研报，其中{rating_action_count}次评级动作"
    return ""
```

Merge it into the output row as a new field:

```python
"historical_event_summary": _build_historical_event_summary(item),
```

- [ ] **Step 4: Run the focused test to verify pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_topn_news_enrichment.py -q
```

Expected:

- PASS for the historical summary tests and existing compact-summary tests.

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/topn_news_enrichment.py tests/test_topn_news_enrichment.py
git commit -m "feat: add historical notice and report summaries to enrichment"
```

## Task 5: Switch Historical Backfill to Replacement Sources and Smoke Test

**Files:**
- Modify: `src/stock_research/news_source_backfill.py`
- Test: `tests/test_public_news_fallback_adapter.py`

- [ ] **Step 1: Write failing summary/report test for replacement-source coverage**

Add a test that verifies summary metrics are populated when historical replacement providers emit rows.

```python
def test_historical_backfill_summary_reports_nonzero_replacement_source_rows(tmp_path, monkeypatch):
    candidates = pd.DataFrame(
        [{"trade_date": "2025-01-24", "asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"}]
    )
    top10_path = tmp_path / "top10.csv"
    candidates.to_csv(top10_path, index=False)

    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_historical_candidate_events",
        lambda **kwargs: pd.DataFrame(
            [{"source_name": "eastmoney_individual_notice", "event_family": "disclosure_notice", "published_at": "2025-01-24 00:00:00", "asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技", "title": "业绩预增公告", "content": "", "source_event_id": "e1", "source_channel": "eastmoney_notice", "url": "", "language": "zh", "metadata": {}}]
        ),
    )

    result = run_historical_top10_news_backfill(
        top10_path=top10_path,
        start_date="2025-01-24",
        end_date="2025-01-24",
        providers=["eastmoney_individual_notice"],
        output_dir=tmp_path,
    )

    summary = pd.read_csv(result["paths"]["summary"])
    assert int(summary.iloc[0]["source_event_rows"]) == 1
```

- [ ] **Step 2: Run the focused test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_public_news_fallback_adapter.py -q
```

Expected:

- FAIL if the summary path or replacement-source metrics are not wired through correctly.

- [ ] **Step 3: Update the historical runner defaults and smoke command**

Set historical default providers in `src/stock_research/news_source_backfill.py` and `src/stock_research/cli.py` to:

```python
DEFAULT_HISTORICAL_REPLACEMENT_PROVIDERS = [
    "eastmoney_individual_notice",
    "eastmoney_research_report",
]
```

Keep `cninfo_disclosure_announcement` opt-in for phase 1:

```bash
stock-research historical-top10-news-backfill \
  --top10-path outputs/research/mid_trend_shadow_top10.csv \
  --start-date 2025-01-02 \
  --end-date 2025-01-31 \
  --providers eastmoney_individual_notice eastmoney_research_report \
  --sample-trade-dates 10 \
  --output-dir outputs/research/top10_historical_news_backfill_smoke_replacement_202501
```

- [ ] **Step 4: Run focused tests and the real smoke command**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  /Users/xiwei/stock_research/tests/test_news_source_backfill.py \
  /Users/xiwei/stock_research/tests/test_public_news_fallback_adapter.py \
  /Users/xiwei/stock_research/tests/test_news_features.py \
  /Users/xiwei/stock_research/tests/test_topn_news_enrichment.py -q
```

Expected:

- PASS for the replacement-source focused suite.

Then run:

```bash
cd /Users/xiwei/stock_research && PYTHONPATH=/Users/xiwei/stock_research/src .venv/bin/python -m stock_research.cli historical-top10-news-backfill \
  --top10-path outputs/research/mid_trend_shadow_top10.csv \
  --start-date 2025-01-02 \
  --end-date 2025-01-31 \
  --providers eastmoney_individual_notice eastmoney_research_report \
  --sample-trade-dates 10 \
  --output-dir outputs/research/top10_historical_news_backfill_smoke_replacement_202501
```

Expected:

- non-zero `source_event_rows`
- non-zero `feature_rows`
- non-zero `enrichment_rows`
- summary/report files written

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/news_source_backfill.py src/stock_research/cli.py tests/test_public_news_fallback_adapter.py
git commit -m "feat: switch historical backfill to replacement notice and report sources"
```

## Task 6: Verify, Compare, and Document Coverage Delta

**Files:**
- Modify if needed: `src/stock_research/news_source_backfill.py`
- Output only: `outputs/research/top10_historical_news_backfill_smoke_replacement_202501/*`

- [ ] **Step 1: Compare old and new smoke summaries**

Read:

```bash
cat /Users/xiwei/stock_research/outputs/research/top10_historical_news_backfill_smoke_202501/historical_top10_news_backfill_summary.csv
cat /Users/xiwei/stock_research/outputs/research/top10_historical_news_backfill_smoke_replacement_202501/historical_top10_news_backfill_summary.csv
```

Expected:

- old `source_event_rows = 0`
- new `source_event_rows > 0`

- [ ] **Step 2: Run the broad verification suite**

Run:

```bash
cd /Users/xiwei/stock_research && /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_news_source_backfill.py \
  tests/test_public_news_fallback_adapter.py \
  tests/test_news_features.py \
  tests/test_topn_news_enrichment.py \
  tests/test_mid_trend_position_dossier.py -q
```

Expected:

- PASS across the news stack and dossier integration.

- [ ] **Step 3: Record verification notes in the final handoff**

Capture:

- which providers were used
- smoke window
- old vs new `source_event_rows`
- old vs new `coverage_rate`
- whether `historical_event_summary` is non-empty in sample rows

- [ ] **Step 4: Commit any final fixes if required**

```bash
cd /Users/xiwei/stock_research
git add -A
git commit -m "test: verify historical replacement source coverage delta"
```

If no final fixes were required, skip this commit.

## Self-Review

Spec coverage check:

- historical replacement source set: covered by Tasks 1-2
- `event_family`: covered by Tasks 1-3
- family-aware features: covered by Task 3
- historical summaries for enrichment: covered by Task 4
- switch historical backfill from `stock_news_em` to replacement providers: covered by Task 5
- smoke and coverage comparison: covered by Task 6

Placeholder scan:

- No `TBD`, `TODO`, or implicit “handle later” language left in tasks

Type consistency:

- plan consistently uses:
  - `providers: list[str]`
  - `event_family`
  - `historical_event_summary`
  - `run_historical_top10_news_backfill(...)`

