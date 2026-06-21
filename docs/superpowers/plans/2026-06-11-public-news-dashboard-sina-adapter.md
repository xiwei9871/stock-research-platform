# Public News Dashboard Sina Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a localhost dashboard news window backed by a public-news backend and Sina Finance adapter.

**Architecture:** Keep public news separate from research news features. Add a small backend package for normalized public news items, a JSON cache store, refresh/read service, FastAPI routes, and a React panel that reads local API data. Tests use fixtures and monkeypatched adapters; no live network is required for CI.

**Tech Stack:** Python 3.14, FastAPI, pandas optional via AKShare fallback, JSON file cache, React, TypeScript, Vitest, pytest.

---

### Task 1: Backend Public News Models And Store

**Files:**
- Create: `src/stock_research/public_news/__init__.py`
- Create: `src/stock_research/public_news/models.py`
- Create: `src/stock_research/public_news/store.py`
- Test: `tests/test_public_news_backend.py`

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path

from stock_research.public_news.models import PublicNewsItem
from stock_research.public_news.store import JsonPublicNewsStore


def test_public_news_item_builds_stable_id_from_url() -> None:
    item = PublicNewsItem.from_raw(
        source="sina_finance",
        source_channel="7x24",
        category="live",
        title="市场消息",
        summary="",
        url="https://finance.sina.com.cn/test/1.shtml",
        published_at="2026-06-11 08:44:57",
        raw_id="raw-1",
        raw_payload={"x": 1},
    )

    assert item.news_id
    assert item.source == "sina_finance"
    assert item.category == "live"
    assert item.status == "available"


def test_json_public_news_store_upserts_and_filters(tmp_path: Path) -> None:
    store = JsonPublicNewsStore(tmp_path / "public_news.json")
    live = PublicNewsItem.from_raw(
        source="sina_finance",
        source_channel="7x24",
        category="live",
        title="全球快讯",
        summary="",
        url="https://finance.sina.com.cn/live/1",
        published_at="2026-06-11 09:00:00",
    )
    macro = PublicNewsItem.from_raw(
        source="sina_finance",
        source_channel="宏观",
        category="macro",
        title="宏观政策更新",
        summary="政策摘要",
        url="https://finance.sina.com.cn/macro/1",
        published_at="2026-06-11 08:00:00",
    )

    result = store.upsert_items([live, macro, live])

    assert result["stored"] == 2
    assert [item.title for item in store.query(category="macro")] == ["宏观政策更新"]
    assert [item.title for item in store.query(q="快讯")] == ["全球快讯"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/test_public_news_backend.py -q`

Expected: FAIL because `stock_research.public_news` does not exist.

- [ ] **Step 3: Implement models and store**

Create `PublicNewsItem`, stable ID hashing, `to_dict`, `from_dict`, and `JsonPublicNewsStore` with `upsert_items()` and `query()`.

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/pytest tests/test_public_news_backend.py -q`

Expected: PASS.

### Task 2: Sina Adapter And Service

**Files:**
- Create: `src/stock_research/public_news/sina_adapter.py`
- Create: `src/stock_research/public_news/service.py`
- Modify: `tests/test_public_news_backend.py`

- [ ] **Step 1: Write failing tests**

Add tests for `normalize_sina_live_rows()`, `refresh_public_news()`, category counts, and warning-preserving failure behavior.

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/test_public_news_backend.py -q`

Expected: FAIL because adapter/service functions do not exist.

- [ ] **Step 3: Implement adapter and service**

Implement fixture-friendly normalization. The live adapter may call AKShare if available, but tests must monkeypatch `fetch_sina_live_rows()`.

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/pytest tests/test_public_news_backend.py -q`

Expected: PASS.

### Task 3: Dashboard API Routes

**Files:**
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_app.py`

- [ ] **Step 1: Write failing route tests**

Add tests for `GET /api/public-news` and `POST /api/public-news/refresh`, monkeypatching dashboard app imports.

- [ ] **Step 2: Run tests to verify failure**

Run: `.venv/bin/pytest tests/test_dashboard_app.py -q`

Expected: FAIL because routes are missing.

- [ ] **Step 3: Implement routes**

Import `load_public_news_for_dashboard` and `refresh_public_news_for_dashboard`; wire GET/POST routes.

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/pytest tests/test_dashboard_app.py tests/test_public_news_backend.py -q`

Expected: PASS.

### Task 4: Dashboard Client And News Panel

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Create: `dashboard/src/components/PublicNewsPanel.tsx`
- Modify: `dashboard/tests/client.test.ts`
- Modify: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write failing frontend tests**

Add client tests for `fetchPublicNews` and `refreshPublicNews`. Add a component/app-shell test that renders a news row, filters category, searches, and calls refresh.

- [ ] **Step 2: Run tests to verify failure**

Run from `dashboard/`: `pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx`

Expected: FAIL because client functions and panel do not exist.

- [ ] **Step 3: Implement frontend**

Add public news types, client calls, panel component, and mount it in `App.tsx`.

- [ ] **Step 4: Run tests to verify pass**

Run from `dashboard/`: `pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx`

Expected: PASS.

### Task 5: Final Verification And Localhost

**Files:**
- No new files required unless verification reveals issues.

- [ ] **Step 1: Backend focused verification**

Run: `.venv/bin/pytest tests/test_public_news_backend.py tests/test_dashboard_app.py -q`

Expected: PASS.

- [ ] **Step 2: Frontend focused verification**

Run from `dashboard/`: `pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx`

Expected: PASS.

- [ ] **Step 3: Dashboard build**

Run from `dashboard/`: `pnpm build`

Expected: PASS.

- [ ] **Step 4: Start localhost services**

Start backend API and Vite dev server on available localhost ports and report URLs.
