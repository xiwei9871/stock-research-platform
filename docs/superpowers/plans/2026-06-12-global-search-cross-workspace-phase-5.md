# Global Search And Cross-Workspace Phase 5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an API-backed global search box that lets the dashboard jump from one top-bar query into Stock Workspace, News, Research Reports, and Generated Reports.

**Architecture:** Add a focused backend read model in `src/stock_research/dashboard/search.py` that composes existing dashboard read paths. Expose `/api/search`, add typed frontend client support, then add a small `GlobalSearchBox` component owned by `AppShell` so workspace routing remains centralized. Workspaces receive optional initial-query props instead of introducing a global state library.

**Tech Stack:** FastAPI, Python dashboard read models, pytest, React, TypeScript, Vite, Vitest, Testing Library, Playwright.

---

## Scope

Included:

- Backend grouped global search for assets, news, research reports, and generated reports.
- Stable search result DTOs.
- `/api/search?q=...&limit=...`.
- Frontend `fetchGlobalSearch`.
- Persistent top-bar search dropdown in `AppShell`.
- Navigation from result rows into existing workspaces.
- Initial query props for News, Research Reports, and Generated Reports.
- Focused backend/frontend tests, build, E2E smoke, and localhost API smoke.

Excluded:

- Vector search, embeddings, or external search services.
- Factor and strategy-run search.
- News detail pages and research report deep-link selection.
- Persisted recent searches.
- New external data adapters.

## Existing Dirty Worktree Warning

The worktree has unrelated uncommitted edits in Market Monitor, Backtest, strategy,
and other files. Do not revert them. When a task touches files that are already
dirty, inspect the current file and stage only task-related hunks.

Known likely dirty files that overlap this plan:

- `dashboard/src/api/types.ts`
- `dashboard/tests/client.test.ts`
- `dashboard/tests/app-shell.test.tsx`
- `dashboard/src/styles.css`

## File Structure

Create:

- `src/stock_research/dashboard/search.py`
  - Owns `load_global_search`.
  - Composes existing read paths and converts rows into grouped search DTOs.
- `tests/test_dashboard_search.py`
  - Backend unit tests for grouping, short query behavior, partial failure warnings.
- `dashboard/src/components/GlobalSearchBox.tsx`
  - Top-bar search input, grouped dropdown, keyboard navigation, stale response guard.
- `dashboard/tests/global-search-box.test.tsx`
  - Component-only tests for rendering, keyboard behavior, and stale response protection.

Modify:

- `src/stock_research/dashboard/app.py`
  - Import `load_global_search`; add `/api/search`.
- `tests/test_dashboard_app.py`
  - Add route forwarding test.
- `dashboard/src/api/types.ts`
  - Add `GlobalSearchResult`, `GlobalSearchGroup`, `GlobalSearchResponse`.
- `dashboard/src/api/client.ts`
  - Add `fetchGlobalSearch(q, limit)`.
- `dashboard/tests/client.test.ts`
  - Add URL and response test.
- `dashboard/src/components/AppShell.tsx`
  - Add top context bar with `GlobalSearchBox`.
  - Route global-search selections to workspaces.
  - Own initial query state for News, Research Reports, and Generated Reports.
- `dashboard/src/components/NewsWorkspace.tsx`
  - Accept `initialQuery?: string` and apply it when it changes.
- `dashboard/src/components/ResearchReportsWorkspace.tsx`
  - Accept `initialQuery?: string` and apply it when it changes.
- `dashboard/src/components/ReportsWorkspace.tsx`
  - Accept `initialQuery?: string` and filter generated report links by keyword.
- `dashboard/src/components/GeneratedReportsWorkspace.tsx`
  - Pass `initialQuery` through to `ReportsWorkspace`.
- `dashboard/tests/app-shell.test.tsx`
  - Add end-to-end shell behavior tests with mocked search result groups.
- `dashboard/tests/news-workspace.test.tsx`
  - Add initial query behavior if not covered through shell.
- `dashboard/tests/research-reports-workspace.test.tsx`
  - Add initial query behavior if not covered through shell.
- `dashboard/src/styles.css`
  - Add compact top bar/search dropdown styles.
- `dashboard/tests/app-smoke.spec.ts`
  - Add mocked `/api/search` response and a smoke interaction if existing route mocks require it.

---

## Shared DTO Contract

Backend result item shape:

```python
{
    "id": "asset:CN:SH:600519",
    "type": "asset",
    "title": "贵州茅台",
    "subtitle": "600519.SH / SH",
    "timestamp": "",
    "target": {"workspace": "stock", "asset_id": "CN:SH:600519"},
    "score": 100,
    "metadata": {"symbol": "600519", "exchange": "SH"},
}
```

Frontend type names:

```ts
export type GlobalSearchResultType = 'asset' | 'news' | 'research_report' | 'generated_report';

export type GlobalSearchTarget = {
  workspace: 'stock' | 'news' | 'researchReports' | 'generatedReports';
  asset_id?: string;
  news_id?: string;
  report_id?: string;
  path?: string;
  q?: string;
};

export type GlobalSearchResult = {
  id: string;
  type: GlobalSearchResultType;
  title: string;
  subtitle: string;
  timestamp: string;
  target: GlobalSearchTarget;
  score: number;
  metadata: Record<string, unknown>;
};

export type GlobalSearchGroup = {
  key: 'assets' | 'news' | 'research_reports' | 'generated_reports';
  label: string;
  items: GlobalSearchResult[];
};

export type GlobalSearchResponse = {
  query: string;
  groups: GlobalSearchGroup[];
  warnings: string[];
};
```

---

## Task 1: Backend Global Search Read Model

**Files:**

- Create: `src/stock_research/dashboard/search.py`
- Test: `tests/test_dashboard_search.py`

- [ ] **Step 1: Write failing backend tests**

Create `tests/test_dashboard_search.py`:

```python
from __future__ import annotations

from stock_research.dashboard import search


def test_load_global_search_returns_grouped_results(monkeypatch):
    monkeypatch.setattr(
        search,
        "search_assets",
        lambda q, limit: [
            {
                "asset_id": "CN:SH:600519",
                "symbol": "600519",
                "name": "贵州茅台",
                "exchange": "SH",
                "board": "白酒",
                "is_active": True,
            }
        ],
    )
    monkeypatch.setattr(
        search,
        "load_public_news_for_dashboard",
        lambda q, limit, **kwargs: {
            "items": [
                {
                    "id": "news-1",
                    "news_id": "news-1",
                    "source": "sina_finance",
                    "source_channel": "公司",
                    "category": "company",
                    "title": "贵州茅台经营快讯",
                    "summary": "收入保持增长",
                    "url": "https://example.com/news",
                    "published_at": "2026-06-12T09:30:00+00:00",
                    "collected_at": "2026-06-12T09:31:00+00:00",
                    "raw_id": "raw-news-1",
                    "raw_payload": {},
                    "status": "available",
                    "stocks": [{"asset_id": "CN:SH:600519", "ts_code": "600519.SH", "stock_name": "贵州茅台"}],
                }
            ],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        search,
        "list_research_reports",
        lambda q, limit, **kwargs: {
            "items": [
                {
                    "report_id": "r1",
                    "event_key": "r1:CN:SH:600519",
                    "asset_id": "CN:SH:600519",
                    "ts_code": "600519.SH",
                    "stock_name": "贵州茅台",
                    "report_title": "贵州茅台深度报告",
                    "publish_date": "2026-06-03",
                    "broker": "华泰证券",
                    "rating": "买入",
                    "source_url": "https://example.com/r1",
                }
            ],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        search,
        "load_report_links",
        lambda trade_date=None: [
            {
                "report_type": "daily_topn",
                "title": "daily_topn_2026-06-12_manual_v1.md",
                "path": "reports/daily_topn_2026-06-12_manual_v1.md",
                "format": "md",
                "trade_date": "2026-06-12",
            }
        ],
    )

    payload = search.load_global_search("600519", limit=3)

    groups = {group["key"]: group for group in payload["groups"]}
    assert payload["query"] == "600519"
    assert groups["assets"]["items"][0]["target"] == {"workspace": "stock", "asset_id": "CN:SH:600519"}
    assert groups["news"]["items"][0]["target"]["workspace"] == "news"
    assert groups["news"]["items"][0]["metadata"]["stocks"][0]["asset_id"] == "CN:SH:600519"
    assert groups["research_reports"]["items"][0]["target"]["workspace"] == "researchReports"
    assert groups["generated_reports"]["items"][0]["target"]["workspace"] == "generatedReports"


def test_load_global_search_short_query_returns_empty_groups(monkeypatch):
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("short queries should not hit read models")

    monkeypatch.setattr(search, "search_assets", fail_if_called)
    monkeypatch.setattr(search, "load_public_news_for_dashboard", fail_if_called)
    monkeypatch.setattr(search, "list_research_reports", fail_if_called)
    monkeypatch.setattr(search, "load_report_links", fail_if_called)

    payload = search.load_global_search("6", limit=3)

    assert payload["query"] == "6"
    assert all(group["items"] == [] for group in payload["groups"])
    assert payload["warnings"] == []


def test_load_global_search_keeps_other_groups_when_one_fails(monkeypatch):
    monkeypatch.setattr(search, "search_assets", lambda q, limit: [])
    monkeypatch.setattr(search, "load_public_news_for_dashboard", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("news offline")))
    monkeypatch.setattr(search, "list_research_reports", lambda q, limit, **kwargs: {"items": [], "warnings": []})
    monkeypatch.setattr(search, "load_report_links", lambda trade_date=None: [])

    payload = search.load_global_search("茅台", limit=3)

    assert any("news search failed: news offline" == warning for warning in payload["warnings"])
    assert [group["key"] for group in payload["groups"]] == ["assets", "news", "research_reports", "generated_reports"]
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/strategy-validation-visualization
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_search.py -q
```

Expected: FAIL because `stock_research.dashboard.search` does not exist.

- [ ] **Step 3: Implement minimal search read model**

Create `src/stock_research/dashboard/search.py`:

```python
from __future__ import annotations

from typing import Any, Callable

from stock_research.dashboard.news import load_public_news_for_dashboard
from stock_research.dashboard.reports import load_report_links
from stock_research.dashboard.research_reports import list_research_reports
from stock_research.dashboard.scores import search_assets

GROUPS = [
    ("assets", "Stocks"),
    ("news", "News"),
    ("research_reports", "Research Reports"),
    ("generated_reports", "Generated Reports"),
]


def _empty_groups() -> list[dict[str, Any]]:
    return [{"key": key, "label": label, "items": []} for key, label in GROUPS]


def _bounded_limit(limit: int) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = 5
    return max(1, min(value, 10))


def _asset_result(row: dict[str, Any], query: str) -> dict[str, Any]:
    asset_id = str(row.get("asset_id") or "")
    symbol = str(row.get("symbol") or "")
    exchange = str(row.get("exchange") or "")
    name = str(row.get("name") or asset_id)
    normalized_query = query.strip().upper()
    score = 60
    if normalized_query and normalized_query in {asset_id.upper(), f"{symbol}.{exchange}".upper()}:
        score = 100
    elif normalized_query and normalized_query == symbol.upper():
        score = 95
    elif normalized_query and symbol.upper().startswith(normalized_query):
        score = 85
    elif query.strip() and query.strip() in name:
        score = 75
    return {
        "id": f"asset:{asset_id}",
        "type": "asset",
        "title": name,
        "subtitle": " / ".join(part for part in [f"{symbol}.{exchange}" if symbol and exchange else symbol, exchange] if part),
        "timestamp": "",
        "target": {"workspace": "stock", "asset_id": asset_id},
        "score": score,
        "metadata": {"symbol": symbol, "exchange": exchange, "board": row.get("board")},
    }


def _news_result(row: dict[str, Any], query: str) -> dict[str, Any]:
    news_id = str(row.get("news_id") or row.get("id") or row.get("raw_id") or row.get("url") or row.get("title"))
    stocks = list(row.get("stocks") or [])
    asset_id = str(stocks[0].get("asset_id") or "") if stocks else ""
    target: dict[str, Any] = {"workspace": "news", "news_id": news_id, "q": query}
    if asset_id:
        target["asset_id"] = asset_id
    return {
        "id": f"news:{news_id}",
        "type": "news",
        "title": str(row.get("title") or ""),
        "subtitle": " / ".join(part for part in [row.get("source"), row.get("category")] if part),
        "timestamp": str(row.get("published_at") or ""),
        "target": target,
        "score": 70,
        "metadata": {"stocks": stocks, "url": row.get("url"), "source": row.get("source")},
    }


def _research_report_result(row: dict[str, Any], query: str) -> dict[str, Any]:
    report_id = str(row.get("event_key") or row.get("report_id") or row.get("source_url") or row.get("report_title"))
    asset_id = str(row.get("asset_id") or "")
    target: dict[str, Any] = {"workspace": "researchReports", "report_id": report_id, "q": query}
    if asset_id:
        target["asset_id"] = asset_id
    return {
        "id": f"research_report:{report_id}",
        "type": "research_report",
        "title": str(row.get("report_title") or ""),
        "subtitle": " / ".join(str(part) for part in [row.get("stock_name"), row.get("broker"), row.get("rating")] if part),
        "timestamp": str(row.get("publish_date") or row.get("report_date") or ""),
        "target": target,
        "score": 65,
        "metadata": {"asset_id": asset_id, "broker": row.get("broker"), "source_url": row.get("source_url")},
    }


def _generated_report_matches(row: dict[str, Any], query: str) -> bool:
    needle = query.strip().lower()
    haystack = " ".join(str(row.get(key) or "") for key in ("title", "report_type", "path", "trade_date")).lower()
    return needle in haystack


def _generated_report_result(row: dict[str, Any], query: str) -> dict[str, Any]:
    path = str(row.get("path") or "")
    title = str(row.get("title") or path)
    return {
        "id": f"generated_report:{path or title}",
        "type": "generated_report",
        "title": title,
        "subtitle": " / ".join(str(part) for part in [row.get("report_type"), row.get("format")] if part),
        "timestamp": str(row.get("trade_date") or ""),
        "target": {"workspace": "generatedReports", "path": path, "q": query},
        "score": 50,
        "metadata": {"path": path, "report_type": row.get("report_type"), "format": row.get("format")},
    }


def _run_group(warnings: list[str], label: str, fn: Callable[[], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    try:
        return fn()
    except Exception as exc:
        warnings.append(f"{label} search failed: {exc}")
        return []


def load_global_search(q: str, *, limit: int = 5) -> dict[str, Any]:
    query = (q or "").strip()
    bounded_limit = _bounded_limit(limit)
    groups = _empty_groups()
    warnings: list[str] = []
    if len(query) < 2:
        return {"query": query, "groups": groups, "warnings": warnings}

    groups[0]["items"] = _run_group(
        warnings,
        "assets",
        lambda: [_asset_result(row, query) for row in search_assets(query, bounded_limit)][:bounded_limit],
    )
    groups[1]["items"] = _run_group(
        warnings,
        "news",
        lambda: [
            _news_result(row, query)
            for row in load_public_news_for_dashboard(q=query, limit=bounded_limit).get("items", [])
        ][:bounded_limit],
    )
    groups[2]["items"] = _run_group(
        warnings,
        "research reports",
        lambda: [
            _research_report_result(row, query)
            for row in list_research_reports(q=query, limit=bounded_limit).get("items", [])
        ][:bounded_limit],
    )
    groups[3]["items"] = _run_group(
        warnings,
        "generated reports",
        lambda: [
            _generated_report_result(row, query)
            for row in load_report_links()
            if _generated_report_matches(row, query)
        ][:bounded_limit],
    )
    return {"query": query, "groups": groups, "warnings": warnings}
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_search.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/search.py tests/test_dashboard_search.py
git commit -m "feat: add dashboard global search read model"
```

---

## Task 2: Search API Route

**Files:**

- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_app.py`

- [ ] **Step 1: Write failing route test**

Add to `tests/test_dashboard_app.py`:

```python
def test_global_search_route_forwards_query(monkeypatch):
    from fastapi.testclient import TestClient
    from stock_research.dashboard import app as dashboard_app

    captured = {}

    def fake_load_global_search(q: str, *, limit: int = 5):
        captured["q"] = q
        captured["limit"] = limit
        return {
            "query": q,
            "groups": [{"key": "assets", "label": "Stocks", "items": []}],
            "warnings": [],
        }

    monkeypatch.setattr(dashboard_app, "load_global_search", fake_load_global_search)
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/search?q=600519&limit=3")

    assert response.status_code == 200
    assert response.json()["query"] == "600519"
    assert captured == {"q": "600519", "limit": 3}
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_app.py::test_global_search_route_forwards_query -q
```

Expected: FAIL with 404 or missing `load_global_search`.

- [ ] **Step 3: Add route**

Modify `src/stock_research/dashboard/app.py`.

Add import:

```python
from stock_research.dashboard.search import load_global_search
```

Add route after `/api/platform/summary`:

```python
    @app.get("/api/search")
    def global_search(q: str, limit: int = 5):
        return load_global_search(q, limit=limit)
```

- [ ] **Step 4: Run route test and focused backend tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_search.py \
  tests/test_dashboard_app.py::test_global_search_route_forwards_query -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/app.py tests/test_dashboard_app.py
git commit -m "feat: expose dashboard global search API"
```

---

## Task 3: Frontend Types And Client

**Files:**

- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write failing client test**

Add imports in `dashboard/tests/client.test.ts`:

```ts
import { fetchGlobalSearch } from '../src/api/client';
```

Add test:

```ts
it('fetches global search results', async () => {
  fetchMock.mockResolvedValueOnce({
    ok: true,
    json: async () => ({
      query: '600519',
      groups: [
        {
          key: 'assets',
          label: 'Stocks',
          items: [
            {
              id: 'asset:CN:SH:600519',
              type: 'asset',
              title: '贵州茅台',
              subtitle: '600519.SH / SH',
              timestamp: '',
              target: { workspace: 'stock', asset_id: 'CN:SH:600519' },
              score: 100,
              metadata: { symbol: '600519' }
            }
          ]
        }
      ],
      warnings: []
    })
  } as Response);

  const payload = await fetchGlobalSearch('600519', 3);

  expect(fetchMock).toHaveBeenCalledWith('/api/search?q=600519&limit=3');
  expect(payload.groups[0].items[0].target.asset_id).toBe('CN:SH:600519');
});
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/strategy-validation-visualization/dashboard
npm test -- --run tests/client.test.ts
```

Expected: FAIL because `fetchGlobalSearch` is not exported.

- [ ] **Step 3: Add types**

Add to `dashboard/src/api/types.ts`:

```ts
export type GlobalSearchResultType = 'asset' | 'news' | 'research_report' | 'generated_report';

export type GlobalSearchTarget = {
  workspace: 'stock' | 'news' | 'researchReports' | 'generatedReports';
  asset_id?: string;
  news_id?: string;
  report_id?: string;
  path?: string;
  q?: string;
};

export type GlobalSearchResult = {
  id: string;
  type: GlobalSearchResultType;
  title: string;
  subtitle: string;
  timestamp: string;
  target: GlobalSearchTarget;
  score: number;
  metadata: Record<string, unknown>;
};

export type GlobalSearchGroup = {
  key: 'assets' | 'news' | 'research_reports' | 'generated_reports';
  label: string;
  items: GlobalSearchResult[];
};

export type GlobalSearchResponse = {
  query: string;
  groups: GlobalSearchGroup[];
  warnings: string[];
};
```

- [ ] **Step 4: Add client method**

Update imports in `dashboard/src/api/client.ts` to include `GlobalSearchResponse`.

Add:

```ts
export async function fetchGlobalSearch(q: string, limit = 5): Promise<GlobalSearchResponse> {
  return getJson(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`);
}
```

- [ ] **Step 5: Run client tests**

Run:

```bash
cd dashboard
npm test -- --run tests/client.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/tests/client.test.ts
git commit -m "feat: add dashboard global search client"
```

---

## Task 4: Global Search Box Component

**Files:**

- Create: `dashboard/src/components/GlobalSearchBox.tsx`
- Create: `dashboard/tests/global-search-box.test.tsx`

- [ ] **Step 1: Write failing component tests**

Create `dashboard/tests/global-search-box.test.tsx`:

```tsx
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GlobalSearchBox } from '../src/components/GlobalSearchBox';
import type { GlobalSearchResponse, GlobalSearchResult } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchGlobalSearch: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

const assetResult: GlobalSearchResult = {
  id: 'asset:CN:SH:600519',
  type: 'asset',
  title: '贵州茅台',
  subtitle: '600519.SH / SH',
  timestamp: '',
  target: { workspace: 'stock', asset_id: 'CN:SH:600519' },
  score: 100,
  metadata: { symbol: '600519' }
};

function makePayload(items: GlobalSearchResult[] = [assetResult]): GlobalSearchResponse {
  return {
    query: '600519',
    groups: [{ key: 'assets', label: 'Stocks', items }],
    warnings: []
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  apiMocks.fetchGlobalSearch.mockResolvedValue(makePayload());
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('GlobalSearchBox', () => {
  it('renders grouped search results and opens a selected result', async () => {
    const onOpenResult = vi.fn();
    render(<GlobalSearchBox onOpenResult={onOpenResult} />);

    fireEvent.change(screen.getByLabelText('Global search'), { target: { value: '600519' } });
    await vi.advanceTimersByTimeAsync(250);

    expect(await screen.findByText('Stocks')).toBeInTheDocument();
    fireEvent.click(screen.getByText('贵州茅台'));

    expect(onOpenResult).toHaveBeenCalledWith(assetResult);
  });

  it('does not search for one-character queries', async () => {
    render(<GlobalSearchBox onOpenResult={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Global search'), { target: { value: '6' } });
    await vi.advanceTimersByTimeAsync(250);

    expect(apiMocks.fetchGlobalSearch).not.toHaveBeenCalled();
  });

  it('ignores stale search responses', async () => {
    let resolveFirst: (payload: GlobalSearchResponse) => void = () => undefined;
    const first = new Promise<GlobalSearchResponse>((resolve) => {
      resolveFirst = resolve;
    });
    apiMocks.fetchGlobalSearch
      .mockReturnValueOnce(first)
      .mockResolvedValueOnce({
        query: '茅台',
        groups: [{ key: 'assets', label: 'Stocks', items: [{ ...assetResult, title: '最新茅台结果' }] }],
        warnings: []
      });

    render(<GlobalSearchBox onOpenResult={vi.fn()} />);

    fireEvent.change(screen.getByLabelText('Global search'), { target: { value: '600519' } });
    await vi.advanceTimersByTimeAsync(250);
    fireEvent.change(screen.getByLabelText('Global search'), { target: { value: '茅台' } });
    await vi.advanceTimersByTimeAsync(250);

    expect(await screen.findByText('最新茅台结果')).toBeInTheDocument();
    resolveFirst(makePayload([{ ...assetResult, title: '旧结果' }]));
    await vi.runOnlyPendingTimersAsync();

    await waitFor(() => expect(screen.queryByText('旧结果')).not.toBeInTheDocument());
  });

  it('opens highlighted result with Enter', async () => {
    const onOpenResult = vi.fn();
    render(<GlobalSearchBox onOpenResult={onOpenResult} />);

    const input = screen.getByLabelText('Global search');
    fireEvent.change(input, { target: { value: '600519' } });
    await vi.advanceTimersByTimeAsync(250);
    await screen.findByText('贵州茅台');

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onOpenResult).toHaveBeenCalledWith(assetResult);
  });
});
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd dashboard
npm test -- --run tests/global-search-box.test.tsx
```

Expected: FAIL because `GlobalSearchBox` does not exist.

- [ ] **Step 3: Implement component**

Create `dashboard/src/components/GlobalSearchBox.tsx`:

```tsx
import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchGlobalSearch } from '../api/client';
import type { GlobalSearchGroup, GlobalSearchResponse, GlobalSearchResult } from '../api/types';

type GlobalSearchBoxProps = {
  onOpenResult: (result: GlobalSearchResult) => void;
};

const MIN_QUERY_LENGTH = 2;
const SEARCH_DEBOUNCE_MS = 250;

function flattenGroups(groups: GlobalSearchGroup[]) {
  return groups.flatMap((group) => group.items.map((item) => ({ group, item })));
}

export function GlobalSearchBox({ onOpenResult }: GlobalSearchBoxProps) {
  const [query, setQuery] = useState('');
  const [payload, setPayload] = useState<GlobalSearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const requestIdRef = useRef(0);
  const trimmedQuery = query.trim();
  const rows = useMemo(() => flattenGroups(payload?.groups ?? []), [payload]);

  useEffect(() => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;

    if (trimmedQuery.length < MIN_QUERY_LENGTH) {
      setPayload(null);
      setError(null);
      setIsLoading(false);
      setHighlightedIndex(-1);
      return;
    }

    setIsLoading(true);
    setError(null);
    const timer = window.setTimeout(() => {
      fetchGlobalSearch(trimmedQuery, 5)
        .then((nextPayload) => {
          if (requestId === requestIdRef.current) {
            setPayload(nextPayload);
            setIsOpen(true);
            setHighlightedIndex(-1);
          }
        })
        .catch((err: unknown) => {
          if (requestId === requestIdRef.current) {
            setError(err instanceof Error ? err.message : String(err));
            setPayload(null);
            setIsOpen(true);
          }
        })
        .finally(() => {
          if (requestId === requestIdRef.current) {
            setIsLoading(false);
          }
        });
    }, SEARCH_DEBOUNCE_MS);

    return () => window.clearTimeout(timer);
  }, [trimmedQuery]);

  function openResult(result: GlobalSearchResult) {
    onOpenResult(result);
    setIsOpen(false);
    setQuery('');
    setPayload(null);
    setHighlightedIndex(-1);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      setIsOpen(false);
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setIsOpen(true);
      setHighlightedIndex((current) => Math.min(current + 1, rows.length - 1));
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlightedIndex((current) => Math.max(current - 1, 0));
      return;
    }
    if (event.key === 'Enter' && highlightedIndex >= 0 && rows[highlightedIndex]) {
      event.preventDefault();
      openResult(rows[highlightedIndex].item);
    }
  }

  const hasResults = rows.length > 0;
  const showEmpty = Boolean(payload && trimmedQuery.length >= MIN_QUERY_LENGTH && !hasResults && !isLoading && !error);

  return (
    <div className="global-search">
      <input
        aria-label="Global search"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setIsOpen(true);
        }}
        onFocus={() => setIsOpen(true)}
        onKeyDown={handleKeyDown}
        placeholder="Search stocks, news, reports"
      />
      {isOpen && trimmedQuery.length >= MIN_QUERY_LENGTH ? (
        <div className="global-search-menu" role="listbox" aria-label="Global search results">
          {isLoading ? <div className="global-search-status">Searching...</div> : null}
          {payload?.groups.map((group) =>
            group.items.length ? (
              <section key={group.key} className="global-search-group">
                <h3>{group.label}</h3>
                {group.items.map((item) => {
                  const rowIndex = rows.findIndex((row) => row.item.id === item.id);
                  return (
                    <button
                      type="button"
                      role="option"
                      aria-selected={rowIndex === highlightedIndex}
                      key={item.id}
                      className={rowIndex === highlightedIndex ? 'active' : ''}
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => openResult(item)}
                    >
                      <strong>{item.title}</strong>
                      <span>{item.subtitle}</span>
                    </button>
                  );
                })}
              </section>
            ) : null
          )}
          {showEmpty ? <div className="global-search-status">No results found.</div> : null}
          {error ? <div className="global-search-error">{error}</div> : null}
          {payload?.warnings?.map((warning) => (
            <div className="global-search-warning" key={warning}>{warning}</div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Run component tests**

Run:

```bash
cd dashboard
npm test -- --run tests/global-search-box.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/GlobalSearchBox.tsx dashboard/tests/global-search-box.test.tsx
git commit -m "feat: add global search box"
```

---

## Task 5: Workspace Initial Query Props

**Files:**

- Modify: `dashboard/src/components/NewsWorkspace.tsx`
- Modify: `dashboard/src/components/ResearchReportsWorkspace.tsx`
- Modify: `dashboard/src/components/ReportsWorkspace.tsx`
- Modify: `dashboard/src/components/GeneratedReportsWorkspace.tsx`
- Modify tests as needed:
  - `dashboard/tests/news-workspace.test.tsx`
  - `dashboard/tests/research-reports-workspace.test.tsx`
  - `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write failing tests for initial query behavior**

Add to `dashboard/tests/news-workspace.test.tsx`:

```tsx
it('applies an initial news query from navigation context', async () => {
  render(<NewsWorkspace initialQuery="茅台" />);

  expect(await screen.findByDisplayValue('茅台')).toBeInTheDocument();
});
```

Add to `dashboard/tests/research-reports-workspace.test.tsx`:

```tsx
it('applies an initial research report query from navigation context', async () => {
  render(<ResearchReportsWorkspace initialQuery="茅台" />);

  expect(await screen.findByDisplayValue('茅台')).toBeInTheDocument();
  await waitFor(() => {
    expect(apiMocks.fetchResearchReports).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: '茅台' })
    );
  });
});
```

If `GeneratedReportsWorkspace` has no focused test file, cover generated-report query through `app-shell.test.tsx` in Task 6.

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
cd dashboard
npm test -- --run tests/news-workspace.test.tsx tests/research-reports-workspace.test.tsx
```

Expected: FAIL because the workspaces do not accept `initialQuery`.

- [ ] **Step 3: Add `initialQuery` to NewsWorkspace**

Modify props:

```ts
type NewsWorkspaceProps = {
  onOpenAsset?: (assetId: string) => void;
  initialQuery?: string;
};
```

Modify function signature:

```ts
export function NewsWorkspace({ onOpenAsset, initialQuery = '' }: NewsWorkspaceProps) {
```

Add effect after query state:

```ts
  useEffect(() => {
    setQuery(initialQuery);
  }, [initialQuery]);
```

- [ ] **Step 4: Add `initialQuery` to ResearchReportsWorkspace**

Modify signature:

```ts
type ResearchReportsWorkspaceProps = {
  initialQuery?: string;
};

export function ResearchReportsWorkspace({ initialQuery = '' }: ResearchReportsWorkspaceProps) {
```

Initialize query state:

```ts
  const [q, setQ] = useState(initialQuery);
```

Add effect:

```ts
  useEffect(() => {
    setQ(initialQuery);
    void loadReports({
      q: initialQuery,
      broker,
      rating,
      sourceName,
      startDate,
      endDate,
      hasTargetPrice
    });
  }, [initialQuery]);
```

If exhaustive-deps complains during build, adjust by introducing a small helper
that reads current state through a callback, but keep behavior: changing
`initialQuery` updates the input and reloads reports.

- [ ] **Step 5: Add `initialQuery` to GeneratedReportsWorkspace and ReportsWorkspace**

Modify `GeneratedReportsWorkspace`:

```tsx
type GeneratedReportsWorkspaceProps = {
  initialQuery?: string;
};

export function GeneratedReportsWorkspace({ initialQuery = '' }: GeneratedReportsWorkspaceProps) {
  return (
    <ReportsWorkspace
      title="Generated Reports"
      description="Local generated artifacts from TopN, risk, factor, backtest, and validation jobs."
      ariaLabel="Generated Reports workspace"
      initialQuery={initialQuery}
    />
  );
}
```

Modify `ReportsWorkspace` props:

```ts
type ReportsWorkspaceProps = {
  title?: string;
  description?: string;
  ariaLabel?: string;
  initialQuery?: string;
};
```

Add query state and filter rows:

```tsx
const [query, setQuery] = useState(initialQuery);

useEffect(() => {
  setQuery(initialQuery);
}, [initialQuery]);

const visibleReports = reports.filter((report) => {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [report.title, report.report_type, report.path, report.trade_date]
    .join(' ')
    .toLowerCase()
    .includes(needle);
});
```

Render compact input near existing controls:

```tsx
<input
  aria-label="generated reports search"
  value={query}
  onChange={(event) => setQuery(event.target.value)}
  placeholder="Search generated reports"
/>
```

Map `visibleReports` instead of `reports`.

- [ ] **Step 6: Run focused tests**

Run:

```bash
cd dashboard
npm test -- --run tests/news-workspace.test.tsx tests/research-reports-workspace.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add \
  dashboard/src/components/NewsWorkspace.tsx \
  dashboard/src/components/ResearchReportsWorkspace.tsx \
  dashboard/src/components/ReportsWorkspace.tsx \
  dashboard/src/components/GeneratedReportsWorkspace.tsx \
  dashboard/tests/news-workspace.test.tsx \
  dashboard/tests/research-reports-workspace.test.tsx
git commit -m "feat: support search query handoff in workspaces"
```

---

## Task 6: AppShell Integration And Styles

**Files:**

- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/src/styles.css`
- Modify: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write failing shell tests**

Add to `dashboard/tests/app-shell.test.tsx`:

```tsx
it('opens stock workspace from global search result', async () => {
  apiMocks.fetchGlobalSearch.mockResolvedValueOnce({
    query: '600519',
    groups: [
      {
        key: 'assets',
        label: 'Stocks',
        items: [
          {
            id: 'asset:CN:SH:600519',
            type: 'asset',
            title: '贵州茅台',
            subtitle: '600519.SH / SH',
            timestamp: '',
            target: { workspace: 'stock', asset_id: 'CN:SH:600519' },
            score: 100,
            metadata: {}
          }
        ]
      }
    ],
    warnings: []
  });

  render(<App />);

  fireEvent.change(screen.getByLabelText('Global search'), { target: { value: '600519' } });
  expect(await screen.findByText('贵州茅台')).toBeInTheDocument();
  fireEvent.click(screen.getByText('贵州茅台'));

  expect(await screen.findByRole('heading', { name: /Stock Workspace|贵州茅台|平安银行/ })).toBeInTheDocument();
  expect(apiMocks.fetchAssetProfile).toHaveBeenLastCalledWith(
    'CN:SH:600519',
    expect.any(String),
    expect.any(String),
    expect.any(String),
    expect.any(String),
    expect.any(String)
  );
});

it('opens news workspace with query from global search result', async () => {
  apiMocks.fetchGlobalSearch.mockResolvedValueOnce({
    query: '茅台',
    groups: [
      {
        key: 'news',
        label: 'News',
        items: [
          {
            id: 'news:n1',
            type: 'news',
            title: '贵州茅台新闻',
            subtitle: 'sina_finance / company',
            timestamp: '2026-06-12',
            target: { workspace: 'news', news_id: 'n1', q: '茅台' },
            score: 70,
            metadata: {}
          }
        ]
      }
    ],
    warnings: []
  });

  render(<App />);

  fireEvent.change(screen.getByLabelText('Global search'), { target: { value: '茅台' } });
  expect(await screen.findByText('贵州茅台新闻')).toBeInTheDocument();
  fireEvent.click(screen.getByText('贵州茅台新闻'));

  expect(await screen.findByRole('heading', { name: 'News' })).toBeInTheDocument();
  expect(screen.getByDisplayValue('茅台')).toBeInTheDocument();
});
```

Add `fetchGlobalSearch` to the hoisted `apiMocks` object and mock module export.

- [ ] **Step 2: Run shell tests and verify failure**

Run:

```bash
cd dashboard
npm test -- --run tests/app-shell.test.tsx
```

Expected: FAIL because AppShell does not render global search.

- [ ] **Step 3: Integrate `GlobalSearchBox` in AppShell**

Modify `dashboard/src/components/AppShell.tsx`:

```tsx
import { GlobalSearchBox } from './GlobalSearchBox';
import type { GlobalSearchResult } from '../api/types';
```

Add state:

```tsx
  const [newsInitialQuery, setNewsInitialQuery] = useState('');
  const [researchReportsInitialQuery, setResearchReportsInitialQuery] = useState('');
  const [generatedReportsInitialQuery, setGeneratedReportsInitialQuery] = useState('');
```

Add handler:

```tsx
  function openGlobalSearchResult(result: GlobalSearchResult) {
    const target = result.target;
    if (target.workspace === 'stock' && target.asset_id) {
      openStockWorkspace(target.asset_id);
      return;
    }
    if (target.workspace === 'news') {
      setNewsInitialQuery(target.q ?? result.title);
      setWorkspaceMode('news');
      return;
    }
    if (target.workspace === 'researchReports') {
      setResearchReportsInitialQuery(target.q ?? result.title);
      setWorkspaceMode('researchReports');
      return;
    }
    if (target.workspace === 'generatedReports') {
      setGeneratedReportsInitialQuery(target.q ?? result.title);
      setWorkspaceMode('generatedReports');
    }
  }
```

Wrap workspace with top bar:

```tsx
      <section className="platform-main">
        <header className="platform-topbar">
          <GlobalSearchBox onOpenResult={openGlobalSearchResult} />
        </header>
        <section className="platform-workspace">
          ...
        </section>
      </section>
```

Update workspace props:

```tsx
{workspaceMode === 'researchReports' ? <ResearchReportsWorkspace initialQuery={researchReportsInitialQuery} /> : null}
{workspaceMode === 'generatedReports' ? <GeneratedReportsWorkspace initialQuery={generatedReportsInitialQuery} /> : null}
{workspaceMode === 'news' ? <NewsWorkspace onOpenAsset={openStockWorkspace} initialQuery={newsInitialQuery} /> : null}
```

- [ ] **Step 4: Add styles**

Append compact styles to `dashboard/src/styles.css`:

```css
.platform-main {
  min-width: 0;
  display: flex;
  flex: 1;
  flex-direction: column;
}

.platform-topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  min-height: 48px;
  padding: 8px 20px;
  border-bottom: 1px solid var(--border-color, #d8dee8);
  background: rgba(248, 250, 252, 0.96);
}

.global-search {
  position: relative;
  width: min(560px, 100%);
}

.global-search input {
  width: 100%;
}

.global-search-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  z-index: 50;
  max-height: 420px;
  overflow: auto;
  border: 1px solid var(--border-color, #d8dee8);
  background: #fff;
  box-shadow: 0 14px 30px rgba(15, 23, 42, 0.12);
}

.global-search-group h3,
.global-search-status,
.global-search-error,
.global-search-warning {
  margin: 0;
  padding: 8px 12px;
  font-size: 12px;
}

.global-search-group h3 {
  color: #64748b;
  text-transform: uppercase;
}

.global-search-group button {
  display: grid;
  width: 100%;
  grid-template-columns: minmax(0, 1fr);
  gap: 2px;
  padding: 8px 12px;
  border: 0;
  border-top: 1px solid #eef2f7;
  background: transparent;
  text-align: left;
}

.global-search-group button:hover,
.global-search-group button.active {
  background: #eff6ff;
}

.global-search-group button span {
  color: #64748b;
  font-size: 12px;
}

.global-search-error {
  color: #b91c1c;
}

.global-search-warning {
  color: #92400e;
}
```

If existing CSS variables differ, adapt to local variables while preserving the
same layout and no text overlap.

- [ ] **Step 5: Run shell and component tests**

Run:

```bash
cd dashboard
npm test -- --run tests/global-search-box.test.tsx tests/app-shell.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/components/AppShell.tsx dashboard/src/styles.css dashboard/tests/app-shell.test.tsx
git commit -m "feat: wire global search into dashboard shell"
```

---

## Task 7: E2E Smoke And Final Verification

**Files:**

- Modify: `dashboard/tests/app-smoke.spec.ts` if existing mocked API routing needs `/api/search`.
- No production changes unless required by failing verified smoke.

- [ ] **Step 1: Add Playwright smoke coverage if needed**

If `app-smoke.spec.ts` uses route mocking that rejects unregistered endpoints,
add:

```ts
await page.route('**/api/search?**', async (route) => {
  await route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      query: '600519',
      groups: [
        {
          key: 'assets',
          label: 'Stocks',
          items: [
            {
              id: 'asset:CN:SH:600519',
              type: 'asset',
              title: '贵州茅台',
              subtitle: '600519.SH / SH',
              timestamp: '',
              target: { workspace: 'stock', asset_id: 'CN:SH:600519' },
              score: 100,
              metadata: {}
            }
          ]
        }
      ],
      warnings: []
    })
  });
});
```

Add smoke interaction only if stable with the existing test setup:

```ts
await page.getByLabel('Global search').fill('600519');
await page.getByText('贵州茅台').click();
await expect(page.getByRole('heading', { name: /Stock Workspace|贵州茅台/ })).toBeVisible();
```

- [ ] **Step 2: Run final backend regression**

Run:

```bash
cd /Users/xiwei/stock_research/.worktrees/strategy-validation-visualization
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_search.py \
  tests/test_dashboard_news.py \
  tests/test_dashboard_research_reports.py \
  tests/test_dashboard_app.py -v
```

Expected: PASS.

- [ ] **Step 3: Run final frontend regression**

Run:

```bash
cd dashboard
npm test -- --run \
  tests/client.test.ts \
  tests/global-search-box.test.tsx \
  tests/news-workspace.test.tsx \
  tests/research-reports-workspace.test.tsx \
  tests/stock-workspace.test.tsx \
  tests/app-shell.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Run build**

Run:

```bash
cd dashboard
npm run build
```

Expected: PASS.

- [ ] **Step 5: Run Playwright smoke**

Run:

```bash
cd dashboard
npm run test:e2e -- tests/app-smoke.spec.ts
```

Expected: PASS.

- [ ] **Step 6: Run localhost API smoke**

Ensure backend is running from this worktree on `127.0.0.1:8765` and Vite on a
local port. Then run:

```bash
curl -sS 'http://127.0.0.1:5176/api/search?q=600519&limit=3' \
  | jq '{query, groups:[.groups[] | {key, count:(.items|length)}], warnings}'
```

Expected: JSON with groups for `assets`, `news`, `research_reports`, and
`generated_reports`. Counts may be zero depending on local data, but the request
must succeed.

- [ ] **Step 7: Final code review**

Dispatch a final reviewer over the Phase 5 commit range. Ask them to verify:

- `/api/search` groups do not fail whole response when one source fails.
- Frontend search ignores stale responses.
- Search navigation carries asset/query context to existing workspaces.
- Existing Phase 1-4 workspaces remain reachable.
- No unrelated dirty worktree changes were committed.

- [ ] **Step 8: Commit E2E/mock changes if any**

```bash
git add dashboard/tests/app-smoke.spec.ts
git commit -m "test: cover global search smoke"
```

Only commit if Task 7 changed files.

---

## Final Acceptance Checklist

- [ ] Phase 5 spec is implemented without adding external services.
- [ ] Backend `/api/search` returns stable grouped DTOs.
- [ ] Global search input is visible in the persistent shell top bar.
- [ ] Stock result opens Stock Workspace with selected asset.
- [ ] News result opens News with query context.
- [ ] Research report result opens Research Reports with query context.
- [ ] Generated report result opens Generated Reports with query context.
- [ ] Search failure does not blank current workspace.
- [ ] Stale frontend search responses are ignored.
- [ ] Backend focused tests pass.
- [ ] Frontend focused tests pass.
- [ ] Build passes.
- [ ] Playwright smoke passes.
- [ ] Localhost API smoke passes.
