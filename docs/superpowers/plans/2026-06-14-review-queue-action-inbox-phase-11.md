# Review Queue And Action Inbox Phase 11 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only EOD Review Queue workspace that groups Phase 10 Evidence Digest candidates into a daily action inbox.

**Architecture:** Add a backend `review_queue` read model that composes `load_platform_summary` top candidates with `build_evidence_digest`, then expose it as `GET /api/review-queue`. Add matching frontend DTO/client support and a new `ReviewQueueWorkspace` wired into `AppShell` and Home quick actions, reusing existing Stock/News/Research/Market handoff callbacks.

**Tech Stack:** Python FastAPI, pytest, React, TypeScript, Vitest, Testing Library, Playwright, existing dashboard API client and workspace components.

---

## File Structure

Phase 11 files expected to change:

- Create `src/stock_research/dashboard/review_queue.py`: bounded read model, queue grouping, fallback item behavior, deterministic sorting.
- Modify `src/stock_research/dashboard/app.py`: import `build_review_queue` and expose `GET /api/review-queue`.
- Create `tests/test_dashboard_review_queue.py`: backend unit and endpoint tests.
- Modify `dashboard/src/api/types.ts`: add `ReviewQueueResponse`, `ReviewQueueGroup`, `ReviewQueueItem`.
- Modify `dashboard/src/api/client.ts`: add `fetchReviewQueue`.
- Modify `dashboard/tests/client.test.ts`: cover query serialization and response shape.
- Create `dashboard/src/components/ReviewQueueWorkspace.tsx`: queue UI, grouping, preview, actions, loading/error/empty states.
- Create `dashboard/tests/review-queue-workspace.test.tsx`: component behavior and action callbacks.
- Modify `dashboard/src/components/AppShell.tsx`: add `reviewQueue` workspace mode, nav item, and queue handoff callbacks.
- Modify `dashboard/src/components/HomeCockpit.tsx`: add quick action for Review Queue.
- Modify `dashboard/tests/app-shell.test.tsx`: mock `fetchReviewQueue`, navigation, and cross-workspace action behavior.
- Modify `dashboard/tests/home-cockpit.test.tsx`: quick action expectation.
- Modify `dashboard/tests/platform-full-flow.spec.ts`: mock `/api/review-queue` and cover opening Review Queue.

Known dirty-worktree boundary:

- Existing unrelated dirty changes may remain in `dashboard/src/api/types.ts`, `dashboard/tests/client.test.ts`, and `dashboard/tests/app-shell.test.tsx`.
- Stage only Phase 11 hunks. Use `git diff -- <file>` and `git add -p` where a file has unrelated edits.
- Do not stage `.superpowers/brainstorm/**` visual companion files.

---

### Task 1: Backend Review Queue Read Model And Endpoint

**Files:**
- Create: `src/stock_research/dashboard/review_queue.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_review_queue.py`

- [ ] **Step 1: Write failing backend tests**

Create `tests/test_dashboard_review_queue.py`:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import review_queue


def _score(asset_id, rank, score_total=80.0):
    return {
        "trade_date": "2026-06-08",
        "asset_id": asset_id,
        "rank": rank,
        "score_total": score_total,
        "score_version": "manual_v1",
        "score_components": {},
    }


def _digest(asset_id, *, bucket="strong", score=80, facts=None, risks=None, warnings=None):
    return {
        "asset_id": asset_id,
        "canonical_asset_id": asset_id,
        "trade_date": "2026-06-08",
        "title": f"{bucket} evidence",
        "score": score,
        "bucket": bucket,
        "facts": facts
        if facts is not None
        else [
            {"kind": "strategy", "label": "TopN candidate"},
            {"kind": "news", "label": "Recent news"},
        ],
        "risk_flags": risks or [],
        "source_refs": {"strategy_asset_id": asset_id},
        "next_actions": [
            {"key": "review_stock", "label": "Review Stock", "workspace": "stock", "asset_id": asset_id, "query": asset_id},
            {"key": "open_news", "label": "Open News", "workspace": "news", "asset_id": asset_id, "query": asset_id},
        ],
        "warnings": warnings or [],
    }


def test_build_review_queue_groups_all_buckets_and_sorts(monkeypatch):
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {
            "latest_market_date": "2026-06-08",
            "topn_preview": [
                _score("000003.SZ", 3, 70),
                _score("000001.SZ", 1, 90),
                _score("000002.SZ", 2, 60),
            ],
        },
    )
    digests = {
        "000001.SZ": _digest("000001.SZ", bucket="mixed", score=62),
        "000002.SZ": _digest("000002.SZ", bucket="strong", score=81),
        "000003.SZ": _digest("000003.SZ", bucket="thin", score=30, facts=[]),
    }
    monkeypatch.setattr(review_queue, "build_evidence_digest", lambda asset_id, **kwargs: digests[asset_id])

    payload = review_queue.build_review_queue(trade_date="2026-06-08", score_version="manual_v1", limit=20)

    assert payload["trade_date"] == "2026-06-08"
    assert [group["bucket"] for group in payload["groups"]] == ["strong", "mixed", "risk_heavy", "thin"]
    assert [group["count"] for group in payload["groups"]] == [1, 1, 0, 1]
    strong_item = payload["groups"][0]["items"][0]
    assert strong_item["queue_id"] == "2026-06-08:manual_v1:000002.SZ"
    assert strong_item["rank"] == 2
    assert strong_item["source_kinds"] == ["strategy", "news"]
    assert strong_item["next_action_count"] == 2


def test_build_review_queue_degrades_digest_failure_to_thin_item(monkeypatch):
    monkeypatch.setattr(
        review_queue,
        "load_platform_summary",
        lambda **kwargs: {"latest_market_date": "2026-06-08", "topn_preview": [_score("000001.SZ", 1, 90)]},
    )

    def fail_digest(asset_id, **kwargs):
        raise RuntimeError("digest unavailable")

    monkeypatch.setattr(review_queue, "build_evidence_digest", fail_digest)

    payload = review_queue.build_review_queue(trade_date="2026-06-08", score_version="manual_v1", limit=20)

    thin = next(group for group in payload["groups"] if group["bucket"] == "thin")
    assert thin["count"] == 1
    item = thin["items"][0]
    assert item["asset_id"] == "000001.SZ"
    assert item["warning_count"] == 1
    assert "digest unavailable" in item["digest"]["warnings"][0]
    assert any("digest unavailable" in warning for warning in payload["warnings"])


def test_build_review_queue_bounds_limit_and_uses_latest_market_date(monkeypatch):
    captured = {}

    def fake_summary(**kwargs):
        captured.update(kwargs)
        return {"latest_market_date": "2026-06-08", "topn_preview": []}

    monkeypatch.setattr(review_queue, "load_platform_summary", fake_summary)

    payload = review_queue.build_review_queue(trade_date=None, score_version="manual_v1", limit=999, lookback_days=999)

    assert captured["top_n"] == 50
    assert payload["trade_date"] == "2026-06-08"
    assert payload["warnings"] == []


def test_review_queue_endpoint_forwards_query(monkeypatch):
    captured = {}

    def fake_queue(*, trade_date=None, score_version="manual_v1", limit=20, lookback_days=90):
        captured.update(
            {
                "trade_date": trade_date,
                "score_version": score_version,
                "limit": limit,
                "lookback_days": lookback_days,
            }
        )
        return {"trade_date": trade_date, "score_version": score_version, "generated_at": "", "groups": [], "warnings": []}

    monkeypatch.setattr(dashboard_app, "build_review_queue", fake_queue)
    client = TestClient(dashboard_app.app)

    response = client.get(
        "/api/review-queue",
        params={"trade_date": "2026-06-08", "score_version": "manual_v2", "limit": 12, "lookback_days": 45},
    )

    assert response.status_code == 200
    assert captured == {
        "trade_date": "2026-06-08",
        "score_version": "manual_v2",
        "limit": 12,
        "lookback_days": 45,
    }
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_review_queue.py -q
```

Expected: FAIL because `stock_research.dashboard.review_queue` does not exist or `build_review_queue` is missing.

- [ ] **Step 3: Implement backend read model**

Create `src/stock_research/dashboard/review_queue.py` with these public helpers and contracts:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from stock_research.dashboard.evidence_digest import build_evidence_digest
from stock_research.dashboard.platform import load_platform_summary

BUCKET_ORDER = ["strong", "mixed", "risk_heavy", "thin"]
BUCKET_LABELS = {
    "strong": "High Conviction",
    "mixed": "Mixed Evidence",
    "risk_heavy": "Risk Flags",
    "thin": "Thin / Missing Sources",
}
MAX_LIMIT = 50


def build_review_queue(
    *,
    trade_date: str | None = None,
    score_version: str = "manual_v1",
    limit: int = 20,
    lookback_days: int = 90,
) -> dict[str, Any]:
    bounded_limit = _bounded_int(limit, default=20, minimum=1, maximum=MAX_LIMIT)
    bounded_lookback = _bounded_int(lookback_days, default=90, minimum=1, maximum=365)
    warnings: list[str] = []
    try:
        summary = load_platform_summary(score_version=score_version, top_n=bounded_limit)
    except Exception as exc:
        return _empty_response(
            trade_date=trade_date or "",
            score_version=score_version,
            warnings=[f"platform summary unavailable: {exc}"],
        )

    selected_trade_date = trade_date or str(summary.get("latest_market_date") or summary.get("latest_score_date") or "")
    score_rows = list(summary.get("topn_preview") or [])
    items: list[dict[str, Any]] = []
    for index, row in enumerate(score_rows):
        asset_id = str(row.get("asset_id") or "")
        if not asset_id:
            continue
        try:
            digest = build_evidence_digest(
                asset_id,
                trade_date=selected_trade_date,
                lookback_days=bounded_lookback,
                score_version=score_version,
            )
        except Exception as exc:
            warning = f"{asset_id} digest unavailable: {exc}"
            warnings.append(warning)
            digest = _fallback_digest(asset_id, selected_trade_date, warning)
        items.append(_queue_item(row, digest, selected_trade_date, score_version, index))

    groups = _groups(items)
    return {
        "trade_date": selected_trade_date,
        "score_version": score_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "groups": groups,
        "warnings": warnings,
    }


def _empty_response(*, trade_date: str, score_version: str, warnings: list[str]) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "score_version": score_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "groups": _groups([]),
        "warnings": warnings,
    }


def _queue_item(
    score_row: dict[str, Any],
    digest: dict[str, Any],
    trade_date: str,
    score_version: str,
    fallback_index: int,
) -> dict[str, Any]:
    canonical_asset_id = str(digest.get("canonical_asset_id") or score_row.get("asset_id") or "")
    bucket = _bucket(digest.get("bucket"))
    facts = list(digest.get("facts") or [])
    risk_flags = list(digest.get("risk_flags") or [])
    warnings = list(digest.get("warnings") or [])
    next_actions = list(digest.get("next_actions") or [])
    rank = _optional_int(score_row.get("rank"))
    score = _optional_float(score_row.get("score_total"))
    return {
        "queue_id": f"{trade_date}:{score_version}:{canonical_asset_id}",
        "asset_id": str(score_row.get("asset_id") or canonical_asset_id),
        "canonical_asset_id": canonical_asset_id,
        "display_name": _display_name(digest, canonical_asset_id),
        "rank": rank if rank is not None else fallback_index + 1,
        "score": score if score is not None else _optional_float(digest.get("score")),
        "digest_title": str(digest.get("title") or BUCKET_LABELS[bucket]),
        "bucket": bucket,
        "source_kinds": _source_kinds(facts),
        "risk_count": len(risk_flags),
        "warning_count": len(warnings),
        "next_action_count": len(next_actions),
        "digest": digest,
    }


def _groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped = {bucket: [] for bucket in BUCKET_ORDER}
    for item in items:
        grouped[_bucket(item.get("bucket"))].append(item)
    return [
        {
            "bucket": bucket,
            "label": BUCKET_LABELS[bucket],
            "count": len(sorted_items),
            "items": sorted_items,
        }
        for bucket in BUCKET_ORDER
        for sorted_items in [sorted(grouped[bucket], key=_sort_key)]
    ]


def _fallback_digest(asset_id: str, trade_date: str, warning: str) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "canonical_asset_id": asset_id,
        "trade_date": trade_date,
        "title": "Thin evidence",
        "score": 0,
        "bucket": "thin",
        "facts": [{"kind": "strategy", "label": "Candidate from score preview"}],
        "risk_flags": [{"key": "digest_unavailable", "label": "Digest unavailable", "severity": "warning"}],
        "source_refs": {"strategy_asset_id": asset_id},
        "next_actions": [
            {"key": "review_stock", "label": "Review Stock", "workspace": "stock", "asset_id": asset_id, "query": asset_id}
        ],
        "warnings": [warning],
    }
```

Add these private helpers in the same file:

```python
def _bucket(value: Any) -> str:
    text = str(value or "thin")
    return text if text in BUCKET_ORDER else "thin"


def _source_kinds(facts: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for fact in facts:
        kind = str(fact.get("kind") or "")
        if kind and kind not in seen:
            seen.append(kind)
    return seen


def _sort_key(item: dict[str, Any]) -> tuple[int, float, str]:
    rank = _optional_int(item.get("rank"))
    digest = item.get("digest") or {}
    digest_score = _optional_float(digest.get("score"))
    return (rank if rank is not None else 999999, -(digest_score or 0.0), str(item.get("asset_id") or ""))


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _display_name(digest: dict[str, Any], fallback: str) -> str:
    asset = digest.get("asset")
    if isinstance(asset, dict):
        name = asset.get("name") or asset.get("symbol")
        if name:
            return str(name)
    source_refs = digest.get("source_refs")
    if isinstance(source_refs, dict):
        name = source_refs.get("stock_name") or source_refs.get("name")
        if name:
            return str(name)
    return fallback
```

- [ ] **Step 4: Add FastAPI route**

Modify `src/stock_research/dashboard/app.py`:

```python
from stock_research.dashboard.review_queue import build_review_queue
```

Inside `create_app()` near the platform/evidence routes:

```python
    @app.get("/api/review-queue")
    def review_queue_route(
        trade_date: str | None = None,
        score_version: str = "manual_v1",
        limit: int = 20,
        lookback_days: int = 90,
    ):
        return build_review_queue(
            trade_date=trade_date,
            score_version=score_version,
            limit=limit,
            lookback_days=lookback_days,
        )
```

- [ ] **Step 5: Run backend tests to verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_review_queue.py tests/test_dashboard_evidence_digest.py tests/test_dashboard_app.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit backend task**

Stage only backend files:

```bash
git add src/stock_research/dashboard/review_queue.py src/stock_research/dashboard/app.py tests/test_dashboard_review_queue.py
git commit -m "feat: add review queue endpoint"
```

---

### Task 2: Frontend API Types And Client

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write failing client tests**

Append tests in `dashboard/tests/client.test.ts` near the Evidence Digest client tests:

```typescript
it('fetchReviewQueue serializes optional filters', async () => {
  fetchMock.mockResolvedValueOnce(jsonResponse({
    trade_date: '2026-06-08',
    score_version: 'manual_v1',
    generated_at: '2026-06-08T20:00:00+08:00',
    groups: [],
    warnings: []
  }));

  const payload = await fetchReviewQueue({
    tradeDate: '2026-06-08',
    scoreVersion: 'manual_v2',
    limit: 12,
    lookbackDays: 45
  });

  expect(fetchMock).toHaveBeenCalledWith('/api/review-queue?trade_date=2026-06-08&score_version=manual_v2&limit=12&lookback_days=45');
  expect(payload.trade_date).toBe('2026-06-08');
});

it('accepts backend-like review queue payloads', async () => {
  fetchMock.mockResolvedValueOnce(jsonResponse({
    trade_date: '2026-06-08',
    score_version: 'manual_v1',
    generated_at: '2026-06-08T20:00:00+08:00',
    groups: [{
      bucket: 'strong',
      label: 'High Conviction',
      count: 1,
      items: [{
        queue_id: '2026-06-08:manual_v1:000001.SZ',
        asset_id: '000001.SZ',
        canonical_asset_id: '000001.SZ',
        display_name: '平安银行',
        rank: 1,
        score: 88.5,
        digest_title: 'Strong evidence',
        bucket: 'strong',
        source_kinds: ['strategy', 'news'],
        risk_count: 0,
        warning_count: 0,
        next_action_count: 2,
        digest: {
          asset_id: '000001.SZ',
          canonical_asset_id: '000001.SZ',
          trade_date: '2026-06-08',
          title: 'Strong evidence',
          score: 82,
          bucket: 'strong',
          facts: [{ kind: 'news', label: 'Recent news' }],
          risk_flags: [],
          source_refs: {},
          next_actions: [{ key: 'review_stock', label: 'Review Stock', workspace: 'stock', asset_id: '000001.SZ' }],
          warnings: []
        }
      }]
    }],
    warnings: []
  }));

  const payload = await fetchReviewQueue();

  expect(payload.groups[0].items[0].digest.facts[0].kind).toBe('news');
});
```

Add imports expected by the test:

```typescript
import { fetchReviewQueue } from '../src/api/client';
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts
```

Expected: FAIL because `fetchReviewQueue` and review queue types are missing.

- [ ] **Step 3: Add TypeScript DTOs**

Add to `dashboard/src/api/types.ts` after Evidence Digest types:

```typescript
export type ReviewQueueItem = {
  queue_id: string;
  asset_id: string;
  canonical_asset_id: string;
  display_name: string;
  rank: number;
  score: number | null;
  digest_title: string;
  bucket: EvidenceDigestBucket;
  source_kinds: string[];
  risk_count: number;
  warning_count: number;
  next_action_count: number;
  digest: EvidenceDigestResponse;
};

export type ReviewQueueGroup = {
  bucket: EvidenceDigestBucket;
  label: string;
  count: number;
  items: ReviewQueueItem[];
};

export type ReviewQueueResponse = {
  trade_date: string;
  score_version: string;
  generated_at: string;
  groups: ReviewQueueGroup[];
  warnings: string[];
};
```

- [ ] **Step 4: Add API client function**

Modify imports in `dashboard/src/api/client.ts`:

```typescript
  ReviewQueueResponse,
```

Add params type near `EvidenceDigestParams`:

```typescript
type ReviewQueueParams = {
  tradeDate?: string;
  scoreVersion?: string;
  limit?: number;
  lookbackDays?: number;
};
```

Add function after `fetchEvidenceDigest`:

```typescript
export async function fetchReviewQueue(params: ReviewQueueParams = {}): Promise<ReviewQueueResponse> {
  const searchParams = new URLSearchParams();
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  if (params.scoreVersion) searchParams.set('score_version', params.scoreVersion);
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
  if (params.lookbackDays !== undefined) searchParams.set('lookback_days', String(params.lookbackDays));
  const query = searchParams.toString();
  return getJson(query ? `/api/review-queue?${query}` : '/api/review-queue');
}
```

- [ ] **Step 5: Run client tests to verify GREEN**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit client task**

If `types.ts` or `client.test.ts` contain unrelated dirty hunks, use patch staging:

```bash
git add -p dashboard/src/api/types.ts dashboard/tests/client.test.ts
git add dashboard/src/api/client.ts
git diff --cached --stat
git commit -m "feat: add review queue client"
```

---

### Task 3: Review Queue Workspace Component

**Files:**
- Create: `dashboard/src/components/ReviewQueueWorkspace.tsx`
- Test: `dashboard/tests/review-queue-workspace.test.tsx`

- [ ] **Step 1: Write failing component tests**

Create `dashboard/tests/review-queue-workspace.test.tsx`:

```typescript
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ReviewQueueWorkspace } from '../src/components/ReviewQueueWorkspace';
import type { ReviewQueueResponse } from '../src/api/types';

vi.mock('../src/api/client', () => ({
  fetchReviewQueue: vi.fn()
}));

import { fetchReviewQueue } from '../src/api/client';

function makeQueue(overrides: Partial<ReviewQueueResponse> = {}): ReviewQueueResponse {
  return {
    trade_date: '2026-06-08',
    score_version: 'manual_v1',
    generated_at: '2026-06-08T20:00:00+08:00',
    warnings: [],
    groups: [
      {
        bucket: 'strong',
        label: 'High Conviction',
        count: 1,
        items: [{
          queue_id: 'q1',
          asset_id: '000001.SZ',
          canonical_asset_id: '000001.SZ',
          display_name: '平安银行',
          rank: 1,
          score: 88.5,
          digest_title: 'Strong evidence',
          bucket: 'strong',
          source_kinds: ['strategy', 'news', 'research'],
          risk_count: 0,
          warning_count: 0,
          next_action_count: 4,
          digest: {
            asset_id: '000001.SZ',
            canonical_asset_id: '000001.SZ',
            trade_date: '2026-06-08',
            title: 'Strong evidence',
            score: 82,
            bucket: 'strong',
            facts: [{ kind: 'news', label: 'Recent accepted news' }],
            risk_flags: [],
            source_refs: { news_id: 'news-1', report_id: 'r1', monitor_tab: 'limit_up' },
            next_actions: [
              { key: 'review_stock', label: 'Review Stock', workspace: 'stock', asset_id: '000001.SZ', query: '平安银行' },
              { key: 'open_news', label: 'Open News', workspace: 'news', asset_id: '000001.SZ', news_id: 'news-1', query: '平安银行' },
              { key: 'open_research', label: 'Open Research', workspace: 'researchReports', asset_id: '000001.SZ', report_id: 'r1', event_key: 'r1:000001.SZ', query: '平安银行' },
              { key: 'open_market', label: 'Open Market', workspace: 'market', asset_id: '000001.SZ', monitor_tab: 'limit_up', query: '平安银行' }
            ],
            warnings: []
          }
        }]
      },
      { bucket: 'mixed', label: 'Mixed Evidence', count: 0, items: [] },
      { bucket: 'risk_heavy', label: 'Risk Flags', count: 0, items: [] },
      { bucket: 'thin', label: 'Thin / Missing Sources', count: 0, items: [] }
    ],
    ...overrides
  };
}

describe('ReviewQueueWorkspace', () => {
  afterEach(() => cleanup());

  beforeEach(() => {
    vi.mocked(fetchReviewQueue).mockResolvedValue(makeQueue());
  });

  it('loads grouped queue items and renders the selected evidence preview', async () => {
    render(<ReviewQueueWorkspace />);

    expect(await screen.findByRole('heading', { name: 'Review Queue' })).toBeInTheDocument();
    expect(fetchReviewQueue).toHaveBeenCalledWith({ limit: 20, lookbackDays: 90 });
    expect(screen.getByRole('button', { name: /High Conviction 1/ })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('平安银行')).toBeInTheDocument();
    expect(screen.getByText('Strong evidence')).toBeInTheDocument();
    expect(screen.getByText('Recent accepted news')).toBeInTheDocument();
    expect(screen.getByText('strategy')).toBeInTheDocument();
    expect(screen.getByText('research')).toBeInTheDocument();
  });

  it('switches groups and shows an empty group state', async () => {
    render(<ReviewQueueWorkspace />);

    await screen.findByText('平安银行');
    fireEvent.click(screen.getByRole('button', { name: /Mixed Evidence 0/ }));

    expect(screen.getByText('No mixed evidence items for 2026-06-08.')).toBeInTheDocument();
    expect(screen.queryByText('Recent accepted news')).not.toBeInTheDocument();
  });

  it('dispatches source-backed next actions', async () => {
    const onOpenStock = vi.fn();
    const onOpenNews = vi.fn();
    const onOpenResearchReports = vi.fn();
    const onOpenMarketMonitor = vi.fn();

    render(
      <ReviewQueueWorkspace
        onOpenStock={onOpenStock}
        onOpenNews={onOpenNews}
        onOpenResearchReports={onOpenResearchReports}
        onOpenMarketMonitor={onOpenMarketMonitor}
      />
    );

    const preview = await screen.findByRole('region', { name: 'Selected Evidence' });
    fireEvent.click(within(preview).getByRole('button', { name: 'Review Stock' }));
    fireEvent.click(within(preview).getByRole('button', { name: 'Open News' }));
    fireEvent.click(within(preview).getByRole('button', { name: 'Open Research' }));
    fireEvent.click(within(preview).getByRole('button', { name: 'Open Market' }));

    expect(onOpenStock).toHaveBeenCalledWith('000001.SZ', expect.objectContaining({ sourceWorkspace: 'search', query: '平安银行' }));
    expect(onOpenNews).toHaveBeenCalledWith(expect.objectContaining({ assetId: '000001.SZ', newsId: 'news-1', query: '平安银行' }));
    expect(onOpenResearchReports).toHaveBeenCalledWith(expect.objectContaining({ assetId: '000001.SZ', reportId: 'r1', eventKey: 'r1:000001.SZ' }));
    expect(onOpenMarketMonitor).toHaveBeenCalledWith(expect.objectContaining({ assetId: '000001.SZ', monitorTab: 'limit_up' }));
  });

  it('shows local error with retry', async () => {
    vi.mocked(fetchReviewQueue).mockRejectedValueOnce(new Error('queue offline')).mockResolvedValueOnce(makeQueue());

    render(<ReviewQueueWorkspace />);

    expect(await screen.findByText('queue offline')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry Review Queue' }));
    expect(await screen.findByText('平安银行')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
cd dashboard && npm test -- --run tests/review-queue-workspace.test.tsx
```

Expected: FAIL because `ReviewQueueWorkspace` does not exist.

- [ ] **Step 3: Implement `ReviewQueueWorkspace`**

Create `dashboard/src/components/ReviewQueueWorkspace.tsx` with:

```typescript
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchReviewQueue } from '../api/client';
import type { EvidenceDigestAction, ReviewQueueGroup, ReviewQueueItem, ReviewQueueResponse } from '../api/types';
import type { StockEntryContext } from './StockWorkspace';

type MarketMonitorTab = 'auction' | 'limit_up' | 'broken_limit_up' | 'limit_down';

type ReviewQueueWorkspaceProps = {
  onOpenStock?: (assetId: string, context?: StockEntryContext) => void;
  onOpenNews?: (context: StockEntryContext) => void;
  onOpenResearchReports?: (context: StockEntryContext) => void;
  onOpenMarketMonitor?: (context: StockEntryContext) => void;
};

const BUCKET_ORDER = ['strong', 'mixed', 'risk_heavy', 'thin'];

function errorMessage(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

function formatScore(value: number | null) {
  return typeof value === 'number' ? value.toFixed(1) : '-';
}

function actionContext(action: EvidenceDigestAction): StockEntryContext {
  return {
    sourceWorkspace: action.workspace === 'stock' ? 'search' : (action.workspace as StockEntryContext['sourceWorkspace']),
    assetId: action.asset_id,
    query: action.query ?? action.asset_id,
    newsId: action.news_id,
    reportId: action.report_id,
    eventKey: action.event_key,
    monitorTab: action.monitor_tab as MarketMonitorTab | undefined
  };
}
```

Implement the component with this structure:

```typescript
export function ReviewQueueWorkspace({
  onOpenStock,
  onOpenNews,
  onOpenResearchReports,
  onOpenMarketMonitor
}: ReviewQueueWorkspaceProps) {
  const [queue, setQueue] = useState<ReviewQueueResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedBucket, setSelectedBucket] = useState<string>('strong');
  const [selectedQueueId, setSelectedQueueId] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const loadQueue = useCallback(() => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsLoading(true);
    setError(null);
    fetchReviewQueue({ limit: 20, lookbackDays: 90 })
      .then((payload) => {
        if (requestId !== requestIdRef.current) return;
        setQueue(payload);
        const firstGroup = payload.groups.find((group) => group.items.length > 0) ?? payload.groups[0] ?? null;
        setSelectedBucket(firstGroup?.bucket ?? 'strong');
        setSelectedQueueId(firstGroup?.items[0]?.queue_id ?? null);
      })
      .catch((err: unknown) => {
        if (requestId !== requestIdRef.current) return;
        setError(errorMessage(err));
        setQueue(null);
        setSelectedQueueId(null);
      })
      .finally(() => {
        if (requestId === requestIdRef.current) setIsLoading(false);
      });
  }, []);

  useEffect(() => {
    loadQueue();
    return () => {
      requestIdRef.current += 1;
    };
  }, [loadQueue]);

  const groups = queue?.groups ?? [];
  const selectedGroup = groups.find((group) => group.bucket === selectedBucket) ?? groups[0] ?? null;
  const selectedItem =
    selectedGroup?.items.find((item) => item.queue_id === selectedQueueId) ?? selectedGroup?.items[0] ?? null;

  function selectGroup(group: ReviewQueueGroup) {
    setSelectedBucket(group.bucket);
    setSelectedQueueId(group.items[0]?.queue_id ?? null);
  }

  function openAction(action: EvidenceDigestAction) {
    const context = actionContext(action);
    const assetId = action.asset_id ?? selectedItem?.canonical_asset_id ?? selectedItem?.asset_id;
    if (action.workspace === 'stock' && assetId) onOpenStock?.(assetId, context);
    if (action.workspace === 'news') onOpenNews?.(context);
    if (action.workspace === 'researchReports') onOpenResearchReports?.(context);
    if (action.workspace === 'market') onOpenMarketMonitor?.(context);
  }

  return (
    <section className="workspace-stack" aria-label="Review Queue workspace">
      <header className="workspace-header">
        <h1>Review Queue</h1>
        <p className="muted">EOD evidence-backed candidates grouped by digest bucket.</p>
      </header>
      {isLoading ? <p className="muted">Loading review queue...</p> : null}
      {error ? (
        <section className="workspace-band">
          <p className="error-text">{error}</p>
          <button type="button" onClick={loadQueue}>Retry Review Queue</button>
        </section>
      ) : null}
      {!error && queue ? (
        <section className="stock-evidence-grid">
          <aside className="workspace-band" aria-label="Queue Groups">
            <div className="section-heading">
              <h2>{queue.trade_date || 'No market date'}</h2>
              <span className="status-chip neutral">{queue.score_version}</span>
            </div>
            <div className="compact-toolbar">
              {groups.map((group) => (
                <button
                  key={group.bucket}
                  type="button"
                  aria-pressed={selectedBucket === group.bucket}
                  onClick={() => selectGroup(group)}
                >
                  {group.label} {group.count}
                </button>
              ))}
            </div>
          </aside>
          <section className="workspace-band" aria-label="Queue Items">
            <div className="section-heading"><h2>{selectedGroup?.label ?? 'Queue Items'}</h2></div>
            {selectedGroup && selectedGroup.items.length === 0 ? (
              <p className="muted">No {selectedGroup.label.toLowerCase()} items for {queue.trade_date}.</p>
            ) : null}
            <div className="data-table">
              {(selectedGroup?.items ?? []).map((item) => (
                <button
                  className="data-table-row"
                  style={{ gridTemplateColumns: '48px minmax(0,1fr) 70px 100px 110px' }}
                  key={item.queue_id}
                  type="button"
                  aria-pressed={selectedItem?.queue_id === item.queue_id}
                  onClick={() => setSelectedQueueId(item.queue_id)}
                >
                  <span>{item.rank}</span>
                  <strong>{item.display_name || item.asset_id}</strong>
                  <span>{formatScore(item.score)}</span>
                  <span className="status-chip neutral">{item.bucket}</span>
                  <span>{item.next_action_count} actions</span>
                </button>
              ))}
            </div>
          </section>
          <section className="workspace-band" role="region" aria-label="Selected Evidence">
            <div className="section-heading"><h2>Selected Evidence</h2></div>
            {selectedItem ? (
              <>
                <strong>{selectedItem.digest_title}</strong>
                <div className="tag-stack">
                  {selectedItem.source_kinds.map((kind) => <span className="status-chip neutral" key={kind}>{kind}</span>)}
                </div>
                {selectedItem.digest.facts.map((fact) => <p key={`${fact.kind}:${fact.label}`}>{fact.label}</p>)}
                {selectedItem.digest.risk_flags.map((flag) => <p className="error-text" key={flag.key}>{flag.label}</p>)}
                {selectedItem.digest.warnings.map((warning) => <p className="muted" key={warning}>{warning}</p>)}
                <div className="compact-toolbar">
                  {selectedItem.digest.next_actions.map((action) => (
                    <button key={action.key} type="button" onClick={() => openAction(action)}>{action.label}</button>
                  ))}
                </div>
              </>
            ) : (
              <p className="muted">Select a queue item to inspect evidence.</p>
            )}
          </section>
        </section>
      ) : null}
    </section>
  );
}
```

This implementation should:

- call `fetchReviewQueue({ limit: 20, lookbackDays: 90 })` on mount;
- keep `queue`, `isLoading`, `error`, `selectedBucket`, `selectedQueueId`;
- use `requestIdRef` to prevent state updates after unmount;
- choose the first non-empty group in the backend order;
- render a header `Review Queue`;
- render group buttons with `aria-pressed`;
- render selected evidence in `role="region" aria-label="Selected Evidence"`;
- show local retry button with label `Retry Review Queue`;
- route actions through `openAction`.

```typescript
function openAction(action: EvidenceDigestAction) {
  const context = actionContext(action);
  const assetId = action.asset_id ?? selectedItem?.canonical_asset_id ?? selectedItem?.asset_id;
  if (action.workspace === 'stock' && assetId) onOpenStock?.(assetId, context);
  if (action.workspace === 'news') onOpenNews?.(context);
  if (action.workspace === 'researchReports') onOpenResearchReports?.(context);
  if (action.workspace === 'market') onOpenMarketMonitor?.(context);
}
```

- [ ] **Step 4: Run component tests to verify GREEN**

Run:

```bash
cd dashboard && npm test -- --run tests/review-queue-workspace.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit workspace task**

```bash
git add dashboard/src/components/ReviewQueueWorkspace.tsx dashboard/tests/review-queue-workspace.test.tsx
git commit -m "feat: add review queue workspace"
```

---

### Task 4: AppShell, Home, And E2E Integration

**Files:**
- Modify: `dashboard/src/components/AppShell.tsx`
- Modify: `dashboard/src/components/HomeCockpit.tsx`
- Modify: `dashboard/tests/app-shell.test.tsx`
- Modify: `dashboard/tests/home-cockpit.test.tsx`
- Modify: `dashboard/tests/platform-full-flow.spec.ts`

- [ ] **Step 1: Write failing integration tests**

In `dashboard/tests/app-shell.test.tsx`:

- add `fetchReviewQueue: vi.fn()` to the hoisted API mocks;
- add a default mocked queue payload in `beforeEach`;
- add test:

```typescript
it('opens Review Queue from navigation and follows review stock action', async () => {
  render(<App />);

  fireEvent.click(await screen.findByRole('button', { name: 'Open Review Queue workspace' }));
  expect(await screen.findByRole('heading', { name: 'Review Queue' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Review Stock' }));

  expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'Source Context' })).toBeInTheDocument();
});
```

In `dashboard/tests/home-cockpit.test.tsx`, update quick action expectations to include Review Queue:

```typescript
expect(screen.getByRole('button', { name: 'Review Queue' })).toBeInTheDocument();
```

In `dashboard/tests/platform-full-flow.spec.ts`, add `/api/review-queue` route and an assertion that Review Queue can be opened:

```typescript
if (url.pathname === '/api/review-queue') {
  await route.fulfill({ json: makeReviewQueueFixture() });
  return;
}
```

Then in the test flow:

```typescript
await page.getByRole('button', { name: 'Open Review Queue workspace' }).click();
await expect(page.getByRole('heading', { name: 'Review Queue' })).toBeVisible();
await expect(page.getByText('Strong evidence')).toBeVisible();
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
cd dashboard && npm test -- --run tests/app-shell.test.tsx tests/home-cockpit.test.tsx
```

Expected: FAIL because `Review Queue` is not in nav/Home and `fetchReviewQueue` is not wired.

- [ ] **Step 3: Wire `AppShell`**

Modify `dashboard/src/components/AppShell.tsx`:

```typescript
import { ReviewQueueWorkspace } from './ReviewQueueWorkspace';
```

Add mode:

```typescript
  | 'reviewQueue'
```

Add nav item near Home:

```typescript
{ mode: 'reviewQueue', label: 'Review Queue' },
```

Add render branch before Market Monitor:

```tsx
{workspaceMode === 'reviewQueue' ? (
  <ReviewQueueWorkspace
    onOpenStock={openStockWorkspace}
    onOpenNews={openNewsWorkspaceFromStock}
    onOpenResearchReports={openResearchReportsWorkspaceFromStock}
    onOpenMarketMonitor={openMarketMonitorWorkspaceFromStock}
  />
) : null}
```

- [ ] **Step 4: Wire `HomeCockpit` quick action**

Modify `WorkspaceMode` and `QUICK_ACTIONS` in `dashboard/src/components/HomeCockpit.tsx`:

```typescript
  | 'reviewQueue'
```

```typescript
{ mode: 'reviewQueue', label: 'Review Queue' },
```

- [ ] **Step 5: Update e2e mocks**

In `dashboard/tests/platform-full-flow.spec.ts`, create a fixture:

```typescript
function makeReviewQueueFixture() {
  return {
    trade_date: '2026-06-08',
    score_version: 'manual_v1',
    generated_at: '2026-06-08T20:00:00+08:00',
    groups: [
      {
        bucket: 'strong',
        label: 'High Conviction',
        count: 1,
        items: [{
          queue_id: '2026-06-08:manual_v1:CN:SZ:300951',
          asset_id: 'CN:SZ:300951',
          canonical_asset_id: 'CN:SZ:300951',
          display_name: 'Fixture Stock',
          rank: 1,
          score: 89.9,
          digest_title: 'Strong evidence',
          bucket: 'strong',
          source_kinds: ['strategy', 'news'],
          risk_count: 0,
          warning_count: 0,
          next_action_count: 1,
          digest: {
            asset_id: 'CN:SZ:300951',
            canonical_asset_id: 'CN:SZ:300951',
            trade_date: '2026-06-08',
            title: 'Strong evidence',
            score: 81,
            bucket: 'strong',
            facts: [{ kind: 'news', label: 'Fixture news evidence' }],
            risk_flags: [],
            source_refs: {},
            next_actions: [{ key: 'review_stock', label: 'Review Stock', workspace: 'stock', asset_id: 'CN:SZ:300951', query: 'Fixture Stock' }],
            warnings: []
          }
        }]
      },
      { bucket: 'mixed', label: 'Mixed Evidence', count: 0, items: [] },
      { bucket: 'risk_heavy', label: 'Risk Flags', count: 0, items: [] },
      { bucket: 'thin', label: 'Thin / Missing Sources', count: 0, items: [] }
    ],
    warnings: []
  };
}
```

- [ ] **Step 6: Run integration tests to verify GREEN**

Run:

```bash
cd dashboard && npm test -- --run tests/app-shell.test.tsx tests/home-cockpit.test.tsx tests/review-queue-workspace.test.tsx
cd dashboard && npm run test:e2e
```

Expected: PASS.

- [ ] **Step 7: Commit integration task**

Patch-stage mixed files as needed:

```bash
git add dashboard/src/components/AppShell.tsx dashboard/src/components/HomeCockpit.tsx dashboard/tests/platform-full-flow.spec.ts
git add -p dashboard/tests/app-shell.test.tsx dashboard/tests/home-cockpit.test.tsx
git commit -m "feat: wire review queue workspace"
```

---

### Task 5: Final Verification, Review, And Worktree Boundary

**Files:**
- Inspect all Phase 11 files.
- Do not create product code unless a Critical or Important review finding requires it.

- [ ] **Step 1: Run focused backend verification**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_review_queue.py tests/test_dashboard_evidence_digest.py tests/test_dashboard_app.py -q
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend verification**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts tests/review-queue-workspace.test.tsx tests/app-shell.test.tsx tests/home-cockpit.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run build**

Run:

```bash
cd dashboard && npm run build
```

Expected: PASS.

- [ ] **Step 4: Run mocked e2e**

Run:

```bash
cd dashboard && npm run test:e2e
```

Expected: PASS.

- [ ] **Step 5: Inspect Phase 11 diff and dirty files**

Run:

```bash
git log --oneline --reverse aa2f1e5..HEAD
git status --short
git diff --stat aa2f1e5..HEAD -- \
  src/stock_research/dashboard/review_queue.py \
  src/stock_research/dashboard/app.py \
  tests/test_dashboard_review_queue.py \
  dashboard/src/api/client.ts \
  dashboard/src/api/types.ts \
  dashboard/tests/client.test.ts \
  dashboard/src/components/ReviewQueueWorkspace.tsx \
  dashboard/tests/review-queue-workspace.test.tsx \
  dashboard/src/components/AppShell.tsx \
  dashboard/src/components/HomeCockpit.tsx \
  dashboard/tests/app-shell.test.tsx \
  dashboard/tests/home-cockpit.test.tsx \
  dashboard/tests/platform-full-flow.spec.ts
```

Expected:

- Phase 11 commits only touch listed files.
- Existing unrelated dirty files may remain unstaged.
- `.superpowers/brainstorm/**` remains untracked and unstaged.

- [ ] **Step 6: Request final code review**

Ask an independent reviewer to inspect Phase 11 from base commit `aa2f1e5` to current HEAD. Review requirements:

- `/api/review-queue` is deterministic, EOD, read-only, bounded, and source-backed.
- All four groups always exist.
- Digest failures degrade row-locally and do not fail the full queue.
- Frontend does not refetch per row and has loading/error/empty states.
- Queue actions reuse existing cross-workspace handoff.
- No user task persistence, realtime polling, AI calls, trading actions, or deep-link route changes.

Fix all Critical and Important findings. Minor findings may be noted if they do not block the phase.

- [ ] **Step 7: Final report**

Use the verification-before-completion skill before claiming completion. Report:

- final Phase 11 commit list;
- verification commands and pass counts;
- review result;
- dirty-worktree caveat for unrelated pre-existing changes.
