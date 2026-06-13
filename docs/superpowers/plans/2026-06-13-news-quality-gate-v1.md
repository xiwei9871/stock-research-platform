# News Quality Gate V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 30-minute backend public-news collector that admits, persists, and displays only the top three high-quality market-relevant news items per refresh window.

**Architecture:** Add a deterministic backend quality gate before news persistence, store quality metadata in the existing `research.news_event_source.metadata` JSONB field, and make `/api/public-news` serve quality-filtered rows directly. The frontend News tab becomes a thin server-side query view that requests only the accepted top three rows and displays quality score, reasons, scheduler status, and an empty high-quality state.

**Tech Stack:** Python/FastAPI, PostgreSQL JSONB metadata, existing Sina public-news adapter, Vitest/React Testing Library, pytest.

---

## File Structure

- Create `src/stock_research/dashboard/news_quality.py`
  - Pure deterministic scoring and filtering for `PublicNewsItem`.
  - Exposes `NewsQualityDecision`, `NewsQualityResult`, `evaluate_public_news_items`, and constants for `NEWS_QUALITY_THRESHOLD`, `NEWS_MAX_ACCEPTED_PER_RUN`, `NEWS_FRESHNESS_HOURS`.
- Create `src/stock_research/dashboard/news_scheduler.py`
  - In-process asyncio scheduler with 30-minute interval, immediate startup run, overlap lock, and status snapshot.
  - Exposes `PublicNewsScheduler`, `create_public_news_scheduler`, `get_public_news_scheduler_status`.
- Modify `src/stock_research/dashboard/news.py`
  - Call quality gate before `NewsEventStore.upsert_public_items`.
  - Persist only accepted top three items.
  - Surface `quality_score`, `quality_reasons`, and scheduler/refresh counters in API payloads.
  - Add server-side `min_quality_score` filtering and quality-first ordering.
- Modify `src/stock_research/dashboard/app.py`
  - Add `min_quality_score` query parameter.
  - Add `/api/public-news/status`.
  - Start/stop scheduler during app lifespan unless disabled by environment.
- Modify `dashboard/src/api/types.ts`
  - Add quality fields and collector status fields.
- Modify `dashboard/src/api/client.ts`
  - Add `minQualityScore` to `fetchPublicNews`.
  - Add `fetchPublicNewsStatus`.
- Modify `dashboard/src/components/NewsWorkspace.tsx`
  - Fetch `limit: 3`, `minQualityScore: 70`, and server-side category/search filters.
  - Use a 30-minute UI polling interval for reading already-admitted rows/status.
  - Keep manual Refresh but route through the same backend quality gate.
- Modify tests:
  - `tests/test_dashboard_news.py`
  - `tests/test_dashboard_app.py`
  - `dashboard/tests/client.test.ts`
  - `dashboard/tests/news-workspace.test.tsx`
  - `dashboard/tests/app-shell.test.tsx`

## Data Contract

Accepted news rows store this metadata shape inside `research.news_event_source.metadata`:

```json
{
  "category": "market",
  "raw_id": "sina-live-20260613-001",
  "raw_payload": { "source": "sina" },
  "quality": {
    "score": 86,
    "reasons": ["fresh", "policy", "sector_specific", "trading_relevant"],
    "run_id": "public-news-20260613T043000Z",
    "accepted_at": "2026-06-13T04:30:00+00:00"
  }
}
```

`GET /api/public-news` returns each item with:

```json
{
  "quality_score": 86,
  "quality_reasons": ["fresh", "policy", "sector_specific", "trading_relevant"],
  "quality_run_id": "public-news-20260613T043000Z"
}
```

`POST /api/public-news/refresh` returns:

```json
{
  "items_received": 100,
  "accepted": 3,
  "stored": 3,
  "rejected": 97,
  "rejection_counts": {
    "duplicate": 18,
    "missing_url": 4,
    "low_signal": 31,
    "below_threshold": 44
  },
  "quality_threshold": 70,
  "max_accepted": 3,
  "warnings": []
}
```

`GET /api/public-news/status` returns:

```json
{
  "enabled": true,
  "running": false,
  "interval_seconds": 1800,
  "last_success_at": "2026-06-13T04:30:05+00:00",
  "last_error": "",
  "next_run_at": "2026-06-13T05:00:05+00:00"
}
```

### Task 1: Backend Quality Gate Unit

**Files:**
- Create: `src/stock_research/dashboard/news_quality.py`
- Modify: `tests/test_dashboard_news.py`

- [ ] **Step 1: Add failing quality-gate tests**

Append these tests near the public-news ingestion tests in `tests/test_dashboard_news.py`:

```python
def test_news_quality_gate_accepts_only_top_three_market_relevant_items():
    from stock_research.dashboard.news_quality import evaluate_public_news_items

    items = [
        make_item(
            news_id=f"policy-{idx}",
            title=f"国家发改委出台半导体产业链支持政策 第{idx}批",
            summary="政策支持、产业链、订单、涨价预期均明确",
            category="market",
            published_at=f"2026-06-13T0{idx}:00:00+00:00",
            url=f"https://finance.sina.com.cn/policy-{idx}.shtml",
        )
        for idx in range(1, 6)
    ]

    result = evaluate_public_news_items(
        items,
        now=datetime(2026, 6, 13, 6, 0, tzinfo=UTC),
    )

    assert len(result.accepted_items) == 3
    assert result.rejection_counts["overflow"] == 2
    assert all(item.raw_payload["quality"]["score"] >= 70 for item in result.accepted_items)
    assert result.accepted_items[0].news_id == "policy-5"
    assert "policy" in result.accepted_items[0].raw_payload["quality"]["reasons"]


def test_news_quality_gate_rejects_low_signal_and_does_not_fill_three_slots():
    from stock_research.dashboard.news_quality import evaluate_public_news_items

    items = [
        make_item(
            news_id="good-1",
            title="央行开展逆回购操作 资金面流动性维持合理充裕",
            summary="市场流动性、利率、资金价格具备交易参考价值",
            category="macro",
            published_at="2026-06-13T05:00:00+00:00",
            url="https://finance.sina.com.cn/good-1.shtml",
        ),
        make_item(
            news_id="bad-1",
            title="更多精彩内容请关注新浪财经",
            summary="",
            category="other",
            published_at="2026-06-13T05:01:00+00:00",
            url="https://finance.sina.com.cn/bad-1.shtml",
        ),
        make_item(
            news_id="bad-2",
            title="今日财经早餐来了",
            summary="",
            category="other",
            published_at="2026-06-13T05:02:00+00:00",
            url="https://finance.sina.com.cn/bad-2.shtml",
        ),
    ]

    result = evaluate_public_news_items(
        items,
        now=datetime(2026, 6, 13, 6, 0, tzinfo=UTC),
    )

    assert [item.news_id for item in result.accepted_items] == ["good-1"]
    assert result.rejection_counts["low_signal"] >= 1
    assert result.rejection_counts["below_threshold"] >= 1
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
pytest tests/test_dashboard_news.py::test_news_quality_gate_accepts_only_top_three_market_relevant_items tests/test_dashboard_news.py::test_news_quality_gate_rejects_low_signal_and_does_not_fill_three_slots -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stock_research.dashboard.news_quality'`.

- [ ] **Step 3: Implement the quality gate**

Create `src/stock_research/dashboard/news_quality.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from stock_research.public_news.models import PublicNewsItem

NEWS_QUALITY_THRESHOLD = 70
NEWS_MAX_ACCEPTED_PER_RUN = 3
NEWS_FRESHNESS_HOURS = 24

LOW_SIGNAL_TOKENS = (
    "财经早餐",
    "更多精彩",
    "点击查看",
    "滚动直播",
    "专题",
    "图文直播",
    "欢迎关注",
)

TRADING_TOKENS = {
    "policy": ("政策", "监管", "发改委", "央行", "证监会", "关税", "制裁", "出口管制"),
    "sector_specific": ("半导体", "新能源", "机器人", "算力", "芯片", "有色", "军工", "医药", "地产", "消费"),
    "company_event": ("公告", "订单", "并购", "重组", "回购", "增持", "减持", "业绩", "中标"),
    "market_liquidity": ("逆回购", "流动性", "利率", "降准", "降息", "融资", "成交额"),
    "risk_event": ("调查", "处罚", "违约", "爆雷", "事故", "下调", "亏损", "退市"),
    "price_signal": ("涨价", "降价", "大涨", "大跌", "供给", "减产", "库存", "期货"),
}

CATEGORY_SCORE = {
    "live": 18,
    "focus": 18,
    "company": 16,
    "market": 16,
    "macro": 14,
    "international": 10,
    "original": 8,
    "opinion": -8,
    "other": -10,
}


@dataclass(frozen=True)
class NewsQualityDecision:
    item: PublicNewsItem
    accepted: bool
    score: int
    reasons: list[str]
    reject_reason: str


@dataclass(frozen=True)
class NewsQualityResult:
    accepted_items: list[PublicNewsItem]
    decisions: list[NewsQualityDecision]
    rejection_counts: dict[str, int]
    threshold: int
    max_accepted: int


def evaluate_public_news_items(
    items: list[PublicNewsItem],
    *,
    now: datetime | None = None,
    threshold: int = NEWS_QUALITY_THRESHOLD,
    max_accepted: int = NEWS_MAX_ACCEPTED_PER_RUN,
) -> NewsQualityResult:
    current_time = now or datetime.now(UTC)
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    scored: list[NewsQualityDecision] = []
    rejection_counts: dict[str, int] = {}

    for item in items:
        decision = score_public_news_item(
            item,
            now=current_time,
            seen_urls=seen_urls,
            seen_titles=seen_titles,
            threshold=threshold,
        )
        if decision.reject_reason:
            rejection_counts[decision.reject_reason] = rejection_counts.get(decision.reject_reason, 0) + 1
        if decision.accepted:
            scored.append(decision)

    ranked = sorted(
        scored,
        key=lambda decision: (
            decision.score,
            _parse_timestamp(decision.item.published_at) or datetime.min.replace(tzinfo=UTC),
            decision.item.news_id,
        ),
        reverse=True,
    )
    accepted_decisions = ranked[:max_accepted]
    overflow = max(0, len(ranked) - len(accepted_decisions))
    if overflow:
        rejection_counts["overflow"] = overflow

    run_id = f"public-news-{current_time.strftime('%Y%m%dT%H%M%SZ')}"
    accepted_items = [_with_quality_metadata(decision, current_time, run_id) for decision in accepted_decisions]
    all_decisions = accepted_decisions + [
        decision for decision in scored if decision.item.news_id not in {accepted.item.news_id for accepted in accepted_decisions}
    ]
    return NewsQualityResult(
        accepted_items=accepted_items,
        decisions=all_decisions,
        rejection_counts=rejection_counts,
        threshold=threshold,
        max_accepted=max_accepted,
    )


def score_public_news_item(
    item: PublicNewsItem,
    *,
    now: datetime,
    seen_urls: set[str],
    seen_titles: set[str],
    threshold: int,
) -> NewsQualityDecision:
    title = " ".join((item.title or "").split())
    summary = " ".join((item.summary or "").split())
    url = " ".join((item.url or "").split())
    if not title:
        return NewsQualityDecision(item, False, 0, [], "missing_title")
    if not url:
        return NewsQualityDecision(item, False, 0, [], "missing_url")
    normalized_title = title.lower()
    normalized_url = url.lower()
    if normalized_url in seen_urls or normalized_title in seen_titles:
        return NewsQualityDecision(item, False, 0, [], "duplicate")
    seen_urls.add(normalized_url)
    seen_titles.add(normalized_title)
    if any(token in title for token in LOW_SIGNAL_TOKENS):
        return NewsQualityDecision(item, False, 0, [], "low_signal")

    published_at = _parse_timestamp(item.published_at) or _parse_timestamp(item.collected_at)
    if published_at and now - published_at > timedelta(hours=NEWS_FRESHNESS_HOURS):
        return NewsQualityDecision(item, False, 0, [], "stale")

    reasons: list[str] = []
    score = 28
    if published_at:
        age_hours = max(0.0, (now - published_at).total_seconds() / 3600)
        if age_hours <= 2:
            score += 18
            reasons.append("fresh")
        elif age_hours <= 8:
            score += 12
            reasons.append("same_day")
        else:
            score += 4
            reasons.append("recent")

    category = (item.category or "other").lower()
    score += CATEGORY_SCORE.get(category, 0)
    if category in {"live", "focus", "company", "market", "macro"}:
        reasons.append(category)

    text = f"{title} {summary}"
    for reason, tokens in TRADING_TOKENS.items():
        if any(token in text for token in tokens):
            score += 10
            reasons.append(reason)

    if any(char.isdigit() for char in text):
        score += 4
        reasons.append("numeric_detail")

    score = max(0, min(100, score))
    if score < threshold:
        return NewsQualityDecision(item, False, score, sorted(set(reasons)), "below_threshold")
    return NewsQualityDecision(item, True, score, sorted(set(reasons)), "")


def _with_quality_metadata(decision: NewsQualityDecision, accepted_at: datetime, run_id: str) -> PublicNewsItem:
    raw_payload: dict[str, Any] = dict(decision.item.raw_payload or {})
    raw_payload["quality"] = {
        "score": decision.score,
        "reasons": decision.reasons,
        "run_id": run_id,
        "accepted_at": accepted_at.isoformat(),
    }
    return PublicNewsItem.from_raw(
        news_id=decision.item.news_id,
        source=decision.item.source,
        source_channel=decision.item.source_channel,
        title=decision.item.title,
        summary=decision.item.summary,
        url=decision.item.url,
        published_at=decision.item.published_at,
        collected_at=decision.item.collected_at,
        category=decision.item.category,
        raw_id=decision.item.raw_id,
        raw_payload=raw_payload,
        status=decision.item.status,
    )


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
```

- [ ] **Step 4: Run quality-gate tests**

Run:

```bash
pytest tests/test_dashboard_news.py::test_news_quality_gate_accepts_only_top_three_market_relevant_items tests/test_dashboard_news.py::test_news_quality_gate_rejects_low_signal_and_does_not_fill_three_slots -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/news_quality.py tests/test_dashboard_news.py
git commit -m "feat: add public news quality gate"
```

### Task 2: Persist Only Accepted Top 3

**Files:**
- Modify: `src/stock_research/dashboard/news.py`
- Modify: `tests/test_dashboard_news.py`

- [ ] **Step 1: Add failing ingestion test**

Append:

```python
def test_public_news_refresh_persists_only_quality_gate_accepted_items(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from stock_research.public_news.store import JsonPublicNewsStore

    received = [
        make_item(news_id="strong-1", title="央行逆回购维护流动性 半导体板块受益", category="macro", url="https://finance.sina.com.cn/strong-1.shtml"),
        make_item(news_id="strong-2", title="国家政策支持机器人产业链订单增长", category="market", url="https://finance.sina.com.cn/strong-2.shtml"),
        make_item(news_id="strong-3", title="有色金属期货大涨 供给减产预期升温", category="market", url="https://finance.sina.com.cn/strong-3.shtml"),
        make_item(news_id="weak-1", title="更多精彩内容请关注新浪财经", summary="", category="other", url="https://finance.sina.com.cn/weak-1.shtml"),
    ]

    class RecordingStore(news.NewsEventStore):
        def __init__(self):
            self.saved: list[PublicNewsItem] = []

        def upsert_public_items(self, items):
            self.saved = list(items)
            return {"received": len(self.saved), "stored": len(self.saved)}

    store = RecordingStore()
    service = news.PublicNewsIngestionService(
        fetcher=lambda: received,
        store=store,
        fallback_store=JsonPublicNewsStore(tmp_path / "public_news.json"),
        mention_mapper=None,
    )

    payload = service.refresh()

    assert payload["items_received"] == 4
    assert payload["accepted"] == 3
    assert payload["stored"] == 3
    assert payload["rejected"] == 1
    assert [item.news_id for item in store.saved] == ["strong-3", "strong-2", "strong-1"]
    assert all("quality" in item.raw_payload for item in store.saved)
```

- [ ] **Step 2: Run test and confirm it fails**

Run:

```bash
pytest tests/test_dashboard_news.py::test_public_news_refresh_persists_only_quality_gate_accepted_items -v
```

Expected: FAIL because refresh currently stores all fetched rows and does not return `accepted`.

- [ ] **Step 3: Wire quality gate into refresh**

Modify imports in `src/stock_research/dashboard/news.py`:

```python
from stock_research.dashboard.news_quality import evaluate_public_news_items
```

Inside `PublicNewsIngestionService.refresh()`, replace the direct upsert of `items` with:

```python
items = list(self.fetcher())
quality_result = evaluate_public_news_items(items)
accepted_items = quality_result.accepted_items
store_result = self.store.upsert_public_items(accepted_items)
mention_result = self.mention_mapper.map_items(accepted_items) if self.mention_mapper else {"mentions": 0}
fallback_result = self.fallback_store.upsert_items(accepted_items) if self.fallback_store else {"stored": 0}
return {
    "items_received": len(items),
    "accepted": len(accepted_items),
    "stored": store_result.get("stored", 0),
    "rejected": max(0, len(items) - len(accepted_items)),
    "rejection_counts": quality_result.rejection_counts,
    "quality_threshold": quality_result.threshold,
    "max_accepted": quality_result.max_accepted,
    "counts_by_category": _category_counts_from_items([_news_row(_item_to_source_row(item)) for item in accepted_items]),
    "mentions": mention_result.get("mentions", 0),
    "fallback_stored": fallback_result.get("stored", 0),
    "warnings": [],
}
```

Keep the existing exception/fallback behavior, but ensure both normal DB writes and JSON fallback receive `accepted_items`, never the full candidate list.

- [ ] **Step 4: Preserve quality metadata in DB rows**

Modify `_item_to_source_row()` so it lifts `raw_payload["quality"]` into top-level metadata:

```python
def _item_to_source_row(item: PublicNewsItem) -> dict[str, Any]:
    raw_payload = item.raw_payload if isinstance(item.raw_payload, dict) else {}
    metadata = {
        "category": item.category or "other",
        "raw_id": item.raw_id,
        "raw_payload": raw_payload,
    }
    if isinstance(raw_payload.get("quality"), dict):
        metadata["quality"] = raw_payload["quality"]
    ...
```

- [ ] **Step 5: Run focused ingestion tests**

Run:

```bash
pytest tests/test_dashboard_news.py::test_public_news_refresh_persists_only_quality_gate_accepted_items tests/test_dashboard_news.py::test_public_news_ingestion_refresh_stores_items tests/test_dashboard_news.py::test_public_news_ingestion_falls_back_to_json_cache_when_db_fails -v
```

Expected: PASS. If legacy tests assert `stored == items_received`, update them to assert accepted-count behavior and that warnings remain preserved.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/dashboard/news.py tests/test_dashboard_news.py
git commit -m "feat: admit only quality public news"
```

### Task 3: Server-Side Quality Filters and API Payload

**Files:**
- Modify: `src/stock_research/dashboard/news.py`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_news.py`
- Modify: `tests/test_dashboard_app.py`

- [ ] **Step 1: Add failing list/filter test**

Add to `tests/test_dashboard_news.py`:

```python
def test_news_event_store_filters_and_orders_by_quality(monkeypatch: pytest.MonkeyPatch):
    db = FakeDb()
    db.news_rows = [
        {
            "source_event_id": "low",
            "source_name": "sina_finance",
            "source_channel": "sina_live",
            "title": "普通观点",
            "content": "",
            "published_at": "2026-06-13T05:00:00+00:00",
            "collected_at": "2026-06-13T05:00:10+00:00",
            "url": "https://finance.sina.com.cn/low.shtml",
            "source_status": "available",
            "metadata": {"category": "other", "quality": {"score": 45, "reasons": ["other"]}},
        },
        {
            "source_event_id": "high",
            "source_name": "sina_finance",
            "source_channel": "sina_live",
            "title": "政策推动半导体产业链订单增长",
            "content": "",
            "published_at": "2026-06-13T04:00:00+00:00",
            "collected_at": "2026-06-13T04:00:10+00:00",
            "url": "https://finance.sina.com.cn/high.shtml",
            "source_status": "available",
            "metadata": {"category": "market", "quality": {"score": 88, "reasons": ["policy", "sector_specific"]}},
        },
    ]
    install_fake_db(monkeypatch, db)

    payload = news.NewsEventStore().list_news(source="sina_finance", min_quality_score=70, limit=3)

    assert [item["news_id"] for item in payload["items"]] == ["high"]
    assert payload["items"][0]["quality_score"] == 88
    assert payload["items"][0]["quality_reasons"] == ["policy", "sector_specific"]
```

If the local `FakeDb` helper has different names, adjust the fixture setup while keeping these assertions.

- [ ] **Step 2: Run test and confirm it fails**

Run:

```bash
pytest tests/test_dashboard_news.py::test_news_event_store_filters_and_orders_by_quality -v
```

Expected: FAIL because `min_quality_score` and quality fields are not supported.

- [ ] **Step 3: Add `min_quality_score` filter**

Update `_build_news_filters()`:

```python
min_quality_score = filters.get("min_quality_score")
if min_quality_score is not None:
    try:
        min_score = int(min_quality_score)
    except (TypeError, ValueError):
        min_score = 0
    if min_score > 0:
        clauses.append("COALESCE((s.metadata->'quality'->>'score')::numeric, 0) >= %s")
        params.append(min_score)
```

Update `NewsEventStore.list_news(...)` signature and call to `_build_news_filters(...)` with `min_quality_score`.

Update the SQL order:

```sql
ORDER BY
    COALESCE((s.metadata->'quality'->>'score')::numeric, 0) DESC,
    s.published_at DESC,
    s.collected_at DESC,
    s.source_event_id
```

- [ ] **Step 4: Surface quality fields**

Update `_news_row()`:

```python
quality = metadata.get("quality") if isinstance(metadata.get("quality"), dict) else {}
quality_reasons = quality.get("reasons") if isinstance(quality.get("reasons"), list) else []
quality_score = quality.get("score")
return {
    ...
    "quality_score": int(quality_score) if isinstance(quality_score, (int, float, str)) and str(quality_score).isdigit() else None,
    "quality_reasons": [str(reason) for reason in quality_reasons],
    "quality_run_id": str(quality.get("run_id") or ""),
    ...
}
```

- [ ] **Step 5: Expose API parameter**

Modify `src/stock_research/dashboard/app.py` public-news endpoint:

```python
@app.get("/api/public-news")
def public_news(
    source: str | None = None,
    category: str | None = None,
    q: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    asset_id: str | None = None,
    ts_code: str | None = None,
    min_quality_score: int | None = None,
    limit: int = 100,
    offset: int = 0,
):
    return load_public_news_for_dashboard(
        source=source,
        category=category,
        q=q,
        start_time=start_time,
        end_time=end_time,
        asset_id=asset_id,
        ts_code=ts_code,
        min_quality_score=min_quality_score,
        limit=limit,
        offset=offset,
    )
```

Propagate the parameter through `load_public_news_for_dashboard()`.

- [ ] **Step 6: Run backend API tests**

Run:

```bash
pytest tests/test_dashboard_news.py::test_news_event_store_filters_and_orders_by_quality tests/test_dashboard_app.py::test_public_news_endpoint_uses_filters -v
```

Expected: PASS after updating existing endpoint assertions to include `min_quality_score` only when provided.

- [ ] **Step 7: Commit**

```bash
git add src/stock_research/dashboard/news.py src/stock_research/dashboard/app.py tests/test_dashboard_news.py tests/test_dashboard_app.py
git commit -m "feat: filter public news by quality"
```

### Task 4: Backend Scheduler and Status Endpoint

**Files:**
- Create: `src/stock_research/dashboard/news_scheduler.py`
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_news.py`
- Modify: `tests/test_dashboard_app.py`

- [ ] **Step 1: Add failing scheduler tests**

Add to `tests/test_dashboard_news.py`:

```python
@pytest.mark.asyncio
async def test_public_news_scheduler_runs_once_and_records_status():
    from stock_research.dashboard.news_scheduler import PublicNewsScheduler

    calls: list[int] = []

    def refresh():
        calls.append(1)
        return {"accepted": 2, "stored": 2, "warnings": []}

    scheduler = PublicNewsScheduler(refresh=refresh, interval_seconds=1800, enabled=True)
    await scheduler.run_once()

    status = scheduler.status()
    assert calls == [1]
    assert status["enabled"] is True
    assert status["running"] is False
    assert status["interval_seconds"] == 1800
    assert status["last_success_at"]
    assert status["last_error"] == ""
    assert status["next_run_at"]


@pytest.mark.asyncio
async def test_public_news_scheduler_lock_prevents_overlap():
    from stock_research.dashboard.news_scheduler import PublicNewsScheduler

    calls = 0

    async def slow_refresh():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"accepted": 1}

    scheduler = PublicNewsScheduler(refresh=slow_refresh, interval_seconds=1800, enabled=True)
    await asyncio.gather(scheduler.run_once(), scheduler.run_once())

    assert calls == 1
```

Ensure `asyncio` is imported at the top of the test file.

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
pytest tests/test_dashboard_news.py::test_public_news_scheduler_runs_once_and_records_status tests/test_dashboard_news.py::test_public_news_scheduler_lock_prevents_overlap -v
```

Expected: FAIL because `news_scheduler.py` does not exist.

- [ ] **Step 3: Implement scheduler**

Create `src/stock_research/dashboard/news_scheduler.py`:

```python
from __future__ import annotations

import asyncio
import inspect
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Awaitable, Callable

NEWS_SCHEDULER_INTERVAL_SECONDS = 30 * 60

RefreshCallable = Callable[[], dict[str, Any] | Awaitable[dict[str, Any]]]


class PublicNewsScheduler:
    def __init__(
        self,
        *,
        refresh: RefreshCallable,
        interval_seconds: int = NEWS_SCHEDULER_INTERVAL_SECONDS,
        enabled: bool = True,
    ) -> None:
        self.refresh = refresh
        self.interval_seconds = interval_seconds
        self.enabled = enabled
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._last_success_at = ""
        self._last_error = ""
        self._next_run_at = ""
        self._running = False

    async def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(self.interval_seconds)

    async def run_once(self) -> dict[str, Any] | None:
        if not self.enabled or self._lock.locked():
            return None
        async with self._lock:
            self._running = True
            try:
                result = self.refresh()
                if inspect.isawaitable(result):
                    result = await result
                now = datetime.now(UTC)
                self._last_success_at = now.isoformat()
                self._last_error = ""
                self._next_run_at = (now + timedelta(seconds=self.interval_seconds)).isoformat()
                return result
            except Exception as exc:  # noqa: BLE001 - surfaced in status for local dashboard diagnostics
                now = datetime.now(UTC)
                self._last_error = str(exc)
                self._next_run_at = (now + timedelta(seconds=self.interval_seconds)).isoformat()
                return None
            finally:
                self._running = False

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "running": self._running,
            "interval_seconds": self.interval_seconds,
            "last_success_at": self._last_success_at,
            "last_error": self._last_error,
            "next_run_at": self._next_run_at,
        }


def scheduler_enabled_from_env() -> bool:
    return os.environ.get("DASHBOARD_PUBLIC_NEWS_SCHEDULER", "1") not in {"0", "false", "False"}
```

- [ ] **Step 4: Wire scheduler into FastAPI lifespan**

Modify `src/stock_research/dashboard/app.py`:

```python
from contextlib import asynccontextmanager
from stock_research.dashboard.news_scheduler import PublicNewsScheduler, scheduler_enabled_from_env


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = PublicNewsScheduler(
        refresh=refresh_public_news_for_dashboard,
        enabled=scheduler_enabled_from_env(),
    )
    app.state.public_news_scheduler = scheduler
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="Stock Research Dashboard API", lifespan=lifespan)
```

Add status endpoint:

```python
@app.get("/api/public-news/status")
def public_news_status():
    scheduler = getattr(app.state, "public_news_scheduler", None)
    if scheduler is None:
        return {"enabled": False, "running": False, "interval_seconds": 1800, "last_success_at": "", "last_error": "", "next_run_at": ""}
    return scheduler.status()
```

- [ ] **Step 5: Add endpoint test**

Add to `tests/test_dashboard_app.py`:

```python
def test_public_news_status_endpoint(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DASHBOARD_PUBLIC_NEWS_SCHEDULER", "0")
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/public-news/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["interval_seconds"] == 1800
```

- [ ] **Step 6: Run scheduler/API tests**

Run:

```bash
pytest tests/test_dashboard_news.py::test_public_news_scheduler_runs_once_and_records_status tests/test_dashboard_news.py::test_public_news_scheduler_lock_prevents_overlap tests/test_dashboard_app.py::test_public_news_status_endpoint -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/stock_research/dashboard/news_scheduler.py src/stock_research/dashboard/app.py tests/test_dashboard_news.py tests/test_dashboard_app.py
git commit -m "feat: schedule public news quality refresh"
```

### Task 5: Frontend Client Types and Server-Side Querying

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Add failing client tests**

Update `dashboard/tests/client.test.ts` public-news test to include `minQualityScore: 70` and expected URL:

```typescript
await fetchPublicNews({
  source: 'sina_finance',
  category: 'live',
  q: '快讯',
  startTime: '2026-06-12T00:00:00',
  endTime: '2026-06-12T23:59:59',
  assetId: 'CN:SH:600519',
  minQualityScore: 70,
  limit: 3,
  offset: 2
});

expect(fetchMock).toHaveBeenCalledWith(
  '/api/public-news?source=sina_finance&category=live&q=%E5%BF%AB%E8%AE%AF&start_time=2026-06-12T00%3A00%3A00&end_time=2026-06-12T23%3A59%3A59&asset_id=CN%3ASH%3A600519&min_quality_score=70&limit=3&offset=2'
);
```

Add:

```typescript
it('fetches public news scheduler status', async () => {
  fetchMock.mockResolvedValueOnce({
    ok: true,
    json: async () => ({ enabled: true, running: false, interval_seconds: 1800 })
  });

  const result = await fetchPublicNewsStatus();

  expect(fetchMock).toHaveBeenCalledWith('/api/public-news/status');
  expect(result.interval_seconds).toBe(1800);
});
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts
```

Expected: FAIL because `minQualityScore` and `fetchPublicNewsStatus` are missing.

- [ ] **Step 3: Update TypeScript types**

Add to `dashboard/src/api/types.ts`:

```typescript
export type PublicNewsCollectorStatus = {
  enabled: boolean;
  running: boolean;
  interval_seconds: number;
  last_success_at?: string;
  last_error?: string;
  next_run_at?: string;
};
```

Extend `PublicNewsItem`:

```typescript
quality_score?: number | null;
quality_reasons?: string[];
quality_run_id?: string;
```

Extend `PublicNewsSummary`:

```typescript
collector_status?: PublicNewsCollectorStatus;
```

Extend `PublicNewsRefreshResponse`:

```typescript
accepted?: number;
rejected?: number;
rejection_counts?: Record<string, number>;
quality_threshold?: number;
max_accepted?: number;
```

- [ ] **Step 4: Update API client**

Modify `PublicNewsParams` in `dashboard/src/api/client.ts`:

```typescript
type PublicNewsParams = {
  source?: string;
  category?: string;
  q?: string;
  startTime?: string;
  endTime?: string;
  assetId?: string;
  tsCode?: string;
  minQualityScore?: number;
  limit?: number;
  offset?: number;
};
```

Add:

```typescript
if (params.minQualityScore !== undefined) searchParams.set('min_quality_score', String(params.minQualityScore));
```

Add:

```typescript
export async function fetchPublicNewsStatus(): Promise<PublicNewsCollectorStatus> {
  return getJson('/api/public-news/status');
}
```

Ensure `PublicNewsCollectorStatus` is imported from `./types`.

- [ ] **Step 5: Run client tests**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/tests/client.test.ts
git commit -m "feat: add public news quality client contract"
```

### Task 6: News Workspace Top 3 UI

**Files:**
- Modify: `dashboard/src/components/NewsWorkspace.tsx`
- Modify: `dashboard/tests/news-workspace.test.tsx`
- Modify: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Add failing UI tests**

In `dashboard/tests/news-workspace.test.tsx`, add:

```typescript
it('loads only accepted quality top three from the server', async () => {
  render(<NewsWorkspace />);

  await waitFor(() => {
    expect(apiMocks.fetchPublicNews).toHaveBeenCalledWith({
      source: 'sina_finance',
      limit: 3,
      minQualityScore: 70
    });
  });
});

it('renders quality score and reasons', async () => {
  apiMocks.fetchPublicNews.mockResolvedValueOnce({
    items: [
      makeNewsItem({
        news_id: 'quality-1',
        title: '政策推动半导体产业链订单增长',
        quality_score: 88,
        quality_reasons: ['policy', 'sector_specific']
      })
    ],
    warnings: [],
    summary: {
      total_news: 1,
      latest_collected_at: '2026-06-13T04:30:00+00:00',
      collector_status: {
        enabled: true,
        running: false,
        interval_seconds: 1800,
        next_run_at: '2026-06-13T05:00:00+00:00'
      }
    }
  });

  render(<NewsWorkspace />);

  expect(await screen.findByText('政策推动半导体产业链订单增长')).toBeInTheDocument();
  expect(screen.getByText('88')).toBeInTheDocument();
  expect(screen.getByText('policy')).toBeInTheDocument();
  expect(screen.getByText('sector_specific')).toBeInTheDocument();
});

it('shows high-quality empty state without filler rows', async () => {
  apiMocks.fetchPublicNews.mockResolvedValueOnce({
    items: [],
    warnings: [],
    summary: {
      total_news: 0,
      collector_status: { enabled: true, running: false, interval_seconds: 1800 }
    }
  });

  render(<NewsWorkspace />);

  expect(await screen.findByText('本轮无高质量新闻')).toBeInTheDocument();
});
```

Update the app-shell timer test to advance fake timers by `30 * 60 * 1000` instead of `60 * 1000`.

- [ ] **Step 2: Run UI tests and confirm they fail**

Run:

```bash
cd dashboard && npm test -- --run tests/news-workspace.test.tsx tests/app-shell.test.tsx
```

Expected: FAIL because NewsWorkspace still fetches 200 rows, filters locally, and uses a 60-second interval.

- [ ] **Step 3: Update NewsWorkspace constants and query builder**

Modify imports:

```typescript
import { fetchPublicNews, fetchPublicNewsStatus, refreshPublicNews } from '../api/client';
import type { PublicNewsCollectorStatus, PublicNewsItem, PublicNewsSummary } from '../api/types';
```

Replace constants:

```typescript
const NEWS_REFRESH_INTERVAL_MS = 30 * 60 * 1000;
const NEWS_QUALITY_THRESHOLD = 70;
const NEWS_LIMIT = 3;
```

Add state:

```typescript
const [collectorStatus, setCollectorStatus] = useState<PublicNewsCollectorStatus | null>(null);
```

Add helper:

```typescript
const buildNewsParams = useCallback(
  () => ({
    source: 'sina_finance',
    category: category === 'all' ? undefined : category,
    q: query.trim() || undefined,
    limit: NEWS_LIMIT,
    minQualityScore: NEWS_QUALITY_THRESHOLD
  }),
  [category, query]
);
```

- [ ] **Step 4: Replace local filtering with server-side loading**

Replace `loadInitialNews` with `loadNews`:

```typescript
const loadNews = useCallback(async () => {
  const requestId = nextRequestId();
  setIsLoading(true);
  try {
    const [payload, status] = await Promise.all([
      fetchPublicNews(buildNewsParams()),
      fetchPublicNewsStatus().catch(() => null)
    ]);
    if (isLatestRequest(requestId)) {
      setItems(payload.items);
      setSummary(payload.summary ?? null);
      setCollectorStatus(status ?? payload.summary?.collector_status ?? null);
      setWarnings(payload.warnings ?? []);
      setLastUpdatedAt(payload.summary?.latest_collected_at ?? new Date().toLocaleTimeString());
    }
  } catch (err: unknown) {
    if (isLatestRequest(requestId)) {
      setWarnings([err instanceof Error ? err.message : String(err)]);
    }
  } finally {
    if (isLatestRequest(requestId)) setIsLoading(false);
  }
}, [buildNewsParams, isLatestRequest, nextRequestId]);
```

Replace `refreshNews` payload fetch with:

```typescript
const refreshResult = await refreshPublicNews();
const [payload, status] = await Promise.all([
  fetchPublicNews(buildNewsParams()),
  fetchPublicNewsStatus().catch(() => null)
]);
...
setItems(payload.items);
setSummary(payload.summary ?? null);
setCollectorStatus(status ?? payload.summary?.collector_status ?? null);
setWarnings([...(refreshResult.warnings ?? []), ...(payload.warnings ?? [])]);
```

Remove `visibleItems` and render `items` directly.

- [ ] **Step 5: Reload on server-side filters**

Add a debounce effect after the initial mounted effect:

```typescript
useEffect(() => {
  if (!isMountedRef.current) return;
  const timer = window.setTimeout(() => {
    void loadNews();
  }, 250);
  return () => window.clearTimeout(timer);
}, [category, query, loadNews]);
```

Update the initial effect to call `loadNews()` and set interval to `NEWS_REFRESH_INTERVAL_MS`.

- [ ] **Step 6: Render collector status, quality score, reasons, and empty state**

In the section heading, replace row count with accepted count:

```tsx
<span className="metric-chip">{items.length}/3 accepted</span>
{collectorStatus?.next_run_at ? <span className="muted">Next {collectorStatus.next_run_at}</span> : null}
{collectorStatus && !collectorStatus.enabled ? <span className="warning-chip">collector off</span> : null}
```

Replace empty text:

```tsx
{isLoading ? (
  <p className="muted">Loading news...</p>
) : items.length === 0 ? (
  <p className="muted">本轮无高质量新闻</p>
) : (
```

Inside each article meta row, add:

```tsx
{item.quality_score !== undefined && item.quality_score !== null ? (
  <span className="quality-score">{item.quality_score}</span>
) : null}
```

Below summary, add:

```tsx
{(item.quality_reasons ?? []).length > 0 ? (
  <div className="news-quality-row">
    {(item.quality_reasons ?? []).map((reason) => (
      <span key={reason} className="metric-chip">{reason}</span>
    ))}
  </div>
) : null}
```

- [ ] **Step 7: Run UI tests**

Run:

```bash
cd dashboard && npm test -- --run tests/news-workspace.test.tsx tests/app-shell.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add dashboard/src/components/NewsWorkspace.tsx dashboard/tests/news-workspace.test.tsx dashboard/tests/app-shell.test.tsx
git commit -m "feat: show accepted public news top three"
```

### Task 7: End-to-End Verification and Local Smoke

**Files:**
- Modify only if verification reveals a bug:
  - `src/stock_research/dashboard/news.py`
  - `src/stock_research/dashboard/app.py`
  - `dashboard/src/components/NewsWorkspace.tsx`

- [ ] **Step 1: Run backend news test suite**

Run:

```bash
pytest tests/test_dashboard_news.py tests/test_dashboard_app.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend targeted tests**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts tests/news-workspace.test.tsx tests/app-shell.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run manual backend smoke**

With the backend dev server running, run:

```bash
curl -s -X POST http://127.0.0.1:8765/api/public-news/refresh | python -m json.tool
curl -s 'http://127.0.0.1:8765/api/public-news?source=sina_finance&min_quality_score=70&limit=3' | python -m json.tool
curl -s http://127.0.0.1:8765/api/public-news/status | python -m json.tool
```

Expected:
- `accepted` is between `0` and `3`.
- `stored` is between `0` and `3`.
- returned `items` length is between `0` and `3`.
- every returned item has `quality_score >= 70` and `quality_reasons`.
- status shows `interval_seconds: 1800`.

- [ ] **Step 4: Browser smoke**

Open `http://127.0.0.1:5174/`, navigate to `News`, and verify:
- It shows at most three rows.
- No low-quality filler appears when fewer than three pass.
- Category/search triggers backend fetches and keeps at most three rows.
- Manual Refresh preserves previous accepted rows if the source fails.
- Collector status is visible.

- [ ] **Step 5: Commit final fixes if needed**

If verification required changes:

```bash
git add <changed-files>
git commit -m "fix: stabilize public news quality workflow"
```

If no changes were needed, do not create an empty commit.

## Self-Review Checklist

- Spec coverage:
  - 30-minute cadence: Task 4 and Task 6.
  - Persist at most three accepted items: Task 1 and Task 2.
  - Show same persisted accepted items: Task 3 and Task 6.
  - Reject low-quality candidates before display/downstream: Task 1 and Task 2.
  - Server-side filters: Task 3 and Task 6.
  - Manual and scheduled refresh use same gate: Task 2 and Task 4.
- Placeholder scan:
  - No `TBD`, no generic validation instructions, no unspecified tests.
- Type consistency:
  - Backend metadata uses `quality.score`, `quality.reasons`, `quality.run_id`.
  - API item fields use `quality_score`, `quality_reasons`, `quality_run_id`.
  - Frontend request uses `minQualityScore`, API query param uses `min_quality_score`.
