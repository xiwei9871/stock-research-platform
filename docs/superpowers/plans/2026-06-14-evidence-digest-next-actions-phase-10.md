# Evidence Digest And Next Actions Phase 10 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic EOD evidence digest endpoint and surface digest status/actions in Stock Detail and Home Cockpit.

**Architecture:** Implement one backend read adapter, `stock_research.dashboard.evidence_digest`, that composes existing asset profile, public news, research reports, and market monitor read models into a source-backed digest DTO. Frontend adds matching TypeScript DTO/client functions, then renders digest facts/actions in `StockWorkspace` and digest badges in `HomeCockpit` without adding realtime, AI generation, batch endpoints, URL routing, or new persistent state.

**Tech Stack:** Python FastAPI, pytest, React, TypeScript, Vitest, Testing Library, existing dashboard API client and workspace components.

---

## File Structure

- Create `src/stock_research/dashboard/evidence_digest.py`: deterministic scoring helpers, risk flag rules, source ref selection, and `build_evidence_digest`.
- Modify `src/stock_research/dashboard/app.py`: import `build_evidence_digest` and expose `GET /api/evidence-digest`.
- Create `tests/test_dashboard_evidence_digest.py`: unit tests for strong/thin/risk-heavy/partial-source digest behavior and endpoint forwarding.
- Modify `dashboard/src/api/types.ts`: add Evidence Digest DTOs.
- Modify `dashboard/src/api/client.ts`: add `fetchEvidenceDigest(assetId, options)`.
- Modify `dashboard/src/components/StockWorkspace.tsx`: fetch and render Evidence Digest panel and action buttons.
- Modify `dashboard/tests/stock-workspace.test.tsx`: cover digest render, action callbacks, error state, and stale response guard.
- Modify `dashboard/src/components/HomeCockpit.tsx`: fetch top-five digests and render digest badges in Today Focus.
- Modify `dashboard/tests/home-cockpit.test.tsx`: cover digest badges and row-local digest failure behavior.

Do not add a batch endpoint, realtime polling, AI calls, URL deep links, or a user investigation queue.

---

### Task 1: Backend Evidence Digest Helper And Endpoint

**Files:**
- Create: `src/stock_research/dashboard/evidence_digest.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_evidence_digest.py`

- [ ] **Step 1: Write backend tests for deterministic digest cases**

Create `tests/test_dashboard_evidence_digest.py` with these tests:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app
from stock_research.dashboard import evidence_digest


def _profile(asset_id="000001.SZ", *, rank=3, risk_tags=None):
    return {
        "asset_id": asset_id,
        "canonical_asset_id": asset_id,
        "asset": {"asset_id": asset_id, "symbol": asset_id[:6], "name": "平安银行"},
        "score": {
            "trade_date": "2026-06-12",
            "asset_id": asset_id,
            "rank": rank,
            "score_total": 88.5,
            "score_version": "manual_v1",
            "score_components": {},
        },
        "signals": [
            {
                "asset_id": asset_id,
                "primary_signal": "candidate",
                "risk_tags": risk_tags or [],
                "signal_tags": ["momentum"],
            }
        ],
        "bars": [],
        "decisions": [],
        "outcomes": [],
        "factor_values": [],
        "coverage": {},
    }


def _news(asset_id="000001.SZ", *, items=2):
    return {
        "asset_id": asset_id,
        "summary": {
            "news_count_1d": min(items, 1),
            "news_count_3d": min(items, 2),
            "news_count_7d": items,
            "latest_published_at": "2026-06-12T09:30:00+08:00",
        },
        "items": [
            {
                "news_id": "news-1",
                "title": "平安银行经营更新",
                "quality_score": 82,
                "published_at": "2026-06-12T09:30:00+08:00",
            }
        ][:items],
        "warnings": [],
    }


def _reports(asset_id="000001.SZ", *, count=1):
    return {
        "asset_id": asset_id,
        "summary": {
            "report_count_30d": count,
            "report_count_90d": count,
            "broker_coverage_count_90d": 1 if count else 0,
            "latest_report_date": "2026-06-10" if count else None,
            "latest_rating": "买入" if count else "",
            "latest_target_price": 19.5 if count else None,
        },
        "items": [
            {
                "report_id": "r1",
                "event_key": "r1:000001.SZ",
                "asset_id": asset_id,
                "ts_code": asset_id,
                "stock_name": "平安银行",
                "report_title": "平安银行深度报告",
                "rating": "买入",
                "target_price": 19.5,
                "broker": "华泰证券",
            }
        ][:count],
        "warnings": [],
    }


def _market(asset_id="000001.SZ", *, tab="limit_up"):
    empty = {"auction": [], "limit_up": [], "broken_limit_up": [], "limit_down": [], "auction_status": "available"}
    if tab:
        empty[tab] = [
            {
                "asset_id": asset_id,
                "name": "平安银行",
                "symbol": asset_id[:6],
                "tab": tab,
                "amount": 1000000000,
                "pct_chg": 10.0,
                "board": "main",
            }
        ]
    return {
        "trade_date": "2026-06-12",
        "emotion_stock_lists": empty,
        "strategy_signal_summary": {"topn_preview": []},
        "warnings": [],
    }


def test_build_evidence_digest_strong_source_backed(monkeypatch):
    monkeypatch.setattr(evidence_digest, "build_asset_profile", lambda **kwargs: _profile(kwargs["asset_id"]))
    monkeypatch.setattr(evidence_digest, "load_asset_news", lambda asset_id, **kwargs: _news(asset_id))
    monkeypatch.setattr(evidence_digest, "load_asset_research_reports", lambda asset_id, **kwargs: _reports(asset_id))
    monkeypatch.setattr(evidence_digest, "build_market_monitor_eod", lambda **kwargs: _market(tab="limit_up"))
    monkeypatch.setattr(evidence_digest, "load_platform_summary", lambda **kwargs: {"latest_market_date": "2026-06-12"})

    digest = evidence_digest.build_evidence_digest("000001.SZ", trade_date="2026-06-12")

    assert digest["canonical_asset_id"] == "000001.SZ"
    assert digest["bucket"] == "strong"
    assert digest["score"] >= 75
    assert any(fact["kind"] == "news" for fact in digest["facts"])
    assert any(fact["kind"] == "research" for fact in digest["facts"])
    assert digest["source_refs"]["news_id"] == "news-1"
    assert digest["source_refs"]["report_id"] == "r1"
    assert digest["source_refs"]["monitor_tab"] == "limit_up"
    assert {action["key"] for action in digest["next_actions"]} >= {"open_news", "open_research", "open_market"}


def test_build_evidence_digest_thin_when_sources_missing(monkeypatch):
    monkeypatch.setattr(evidence_digest, "build_asset_profile", lambda **kwargs: _profile(kwargs["asset_id"], rank=80))
    monkeypatch.setattr(evidence_digest, "load_asset_news", lambda asset_id, **kwargs: _news(asset_id, items=0))
    monkeypatch.setattr(evidence_digest, "load_asset_research_reports", lambda asset_id, **kwargs: _reports(asset_id, count=0))
    monkeypatch.setattr(evidence_digest, "build_market_monitor_eod", lambda **kwargs: _market(tab=None))
    monkeypatch.setattr(evidence_digest, "load_platform_summary", lambda **kwargs: {"latest_market_date": "2026-06-12"})

    digest = evidence_digest.build_evidence_digest("000001.SZ", trade_date="2026-06-12")

    assert digest["bucket"] == "thin"
    assert any(flag["key"] == "thin_research" for flag in digest["risk_flags"])
    assert any(flag["key"] == "low_news_coverage" for flag in digest["risk_flags"])


def test_build_evidence_digest_risk_heavy_for_market_pressure(monkeypatch):
    monkeypatch.setattr(evidence_digest, "build_asset_profile", lambda **kwargs: _profile(kwargs["asset_id"], risk_tags=["gap_risk"]))
    monkeypatch.setattr(evidence_digest, "load_asset_news", lambda asset_id, **kwargs: _news(asset_id))
    monkeypatch.setattr(evidence_digest, "load_asset_research_reports", lambda asset_id, **kwargs: _reports(asset_id))
    monkeypatch.setattr(evidence_digest, "build_market_monitor_eod", lambda **kwargs: _market(tab="limit_down"))
    monkeypatch.setattr(evidence_digest, "load_platform_summary", lambda **kwargs: {"latest_market_date": "2026-06-12"})

    digest = evidence_digest.build_evidence_digest("000001.SZ", trade_date="2026-06-12")

    assert digest["bucket"] == "risk_heavy"
    assert any(flag["key"] == "market_limit_down" for flag in digest["risk_flags"])
    assert any(flag["key"] == "strategy_risk_tags" for flag in digest["risk_flags"])


def test_build_evidence_digest_returns_warning_for_partial_source_failure(monkeypatch):
    monkeypatch.setattr(evidence_digest, "build_asset_profile", lambda **kwargs: _profile(kwargs["asset_id"]))
    monkeypatch.setattr(evidence_digest, "load_asset_news", lambda asset_id, **kwargs: (_ for _ in ()).throw(RuntimeError("news offline")))
    monkeypatch.setattr(evidence_digest, "load_asset_research_reports", lambda asset_id, **kwargs: _reports(asset_id))
    monkeypatch.setattr(evidence_digest, "build_market_monitor_eod", lambda **kwargs: _market(tab=None))
    monkeypatch.setattr(evidence_digest, "load_platform_summary", lambda **kwargs: {"latest_market_date": "2026-06-12"})

    digest = evidence_digest.build_evidence_digest("000001.SZ", trade_date="2026-06-12")

    assert any("news offline" in warning for warning in digest["warnings"])
    assert any(fact["kind"] == "research" for fact in digest["facts"])


def test_evidence_digest_endpoint_forwards_query(monkeypatch):
    captured = {}

    def fake_digest(asset_id, *, trade_date=None, lookback_days=90, score_version="manual_v1"):
        captured.update(
            {
                "asset_id": asset_id,
                "trade_date": trade_date,
                "lookback_days": lookback_days,
                "score_version": score_version,
            }
        )
        return {
            "asset_id": asset_id,
            "canonical_asset_id": asset_id,
            "trade_date": trade_date,
            "title": "Thin evidence",
            "score": 20,
            "bucket": "thin",
            "facts": [],
            "risk_flags": [],
            "source_refs": {},
            "next_actions": [],
            "warnings": [],
        }

    monkeypatch.setattr(dashboard_app, "build_evidence_digest", fake_digest, raising=False)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/evidence-digest?asset_id=000001.SZ&trade_date=2026-06-12&lookback_days=30&score_version=manual_v2"
    )

    assert response.status_code == 200
    assert captured == {
        "asset_id": "000001.SZ",
        "trade_date": "2026-06-12",
        "lookback_days": 30,
        "score_version": "manual_v2",
    }
    assert response.json()["bucket"] == "thin"
```

- [ ] **Step 2: Run backend tests to verify they fail**

Run:

```bash
pytest tests/test_dashboard_evidence_digest.py -q
```

Expected: FAIL because `stock_research.dashboard.evidence_digest` and the route do not exist.

- [ ] **Step 3: Implement evidence digest helper**

Create `src/stock_research/dashboard/evidence_digest.py`:

```python
from __future__ import annotations

from typing import Any

from stock_research.dashboard.asset_profile import build_asset_profile
from stock_research.dashboard.market_monitor import build_market_monitor_eod
from stock_research.dashboard.news import load_asset_news
from stock_research.dashboard.platform import load_platform_summary
from stock_research.dashboard.research_reports import load_asset_research_reports


DigestSeverity = str


def build_evidence_digest(
    asset_id: str,
    *,
    trade_date: str | None = None,
    lookback_days: int = 90,
    score_version: str = "manual_v1",
) -> dict[str, Any]:
    selected_trade_date = trade_date or _latest_market_date(score_version)
    warnings: list[str] = []
    profile = build_asset_profile(
        asset_id=asset_id,
        trade_date=selected_trade_date,
        start_date=selected_trade_date,
        end_date=selected_trade_date,
        score_version=score_version,
    )
    canonical_asset_id = str(profile.get("canonical_asset_id") or profile.get("asset_id") or asset_id)

    news = _safe_source(
        "news",
        warnings,
        lambda: load_asset_news(canonical_asset_id, limit=5, lookback_days=7),
        {"summary": {"news_count_7d": 0}, "items": [], "warnings": []},
    )
    reports = _safe_source(
        "research",
        warnings,
        lambda: load_asset_research_reports(canonical_asset_id, limit=5, lookback_days=lookback_days),
        {"summary": {"report_count_30d": 0, "report_count_90d": 0}, "items": [], "warnings": []},
    )
    market = _safe_source(
        "market",
        warnings,
        lambda: build_market_monitor_eod(trade_date=selected_trade_date, score_version=score_version, top_n=5),
        {"emotion_stock_lists": {"auction": [], "limit_up": [], "broken_limit_up": [], "limit_down": []}, "warnings": []},
    )

    score = 0
    facts: list[dict[str, Any]] = []
    risk_flags: list[dict[str, str]] = []
    source_refs: dict[str, str] = {}

    score += _add_news_evidence(news, canonical_asset_id, facts, risk_flags, source_refs)
    score += _add_research_evidence(reports, canonical_asset_id, facts, risk_flags, source_refs)
    score += _add_market_evidence(market, canonical_asset_id, facts, risk_flags, source_refs)
    score += _add_strategy_evidence(profile, facts, risk_flags)
    score = max(0, min(100, score))

    bucket = _bucket(score, risk_flags, facts)
    return {
        "asset_id": asset_id,
        "canonical_asset_id": canonical_asset_id,
        "trade_date": selected_trade_date,
        "title": _title(bucket),
        "score": score,
        "bucket": bucket,
        "facts": facts[:5],
        "risk_flags": risk_flags,
        "source_refs": source_refs,
        "next_actions": _next_actions(canonical_asset_id, source_refs),
        "warnings": [*warnings, *news.get("warnings", []), *reports.get("warnings", []), *market.get("warnings", [])],
    }
```

Then add these helper functions in the same file:

```python
def _latest_market_date(score_version: str) -> str:
    summary = load_platform_summary(score_version=score_version, top_n=1)
    return str(summary.get("latest_market_date") or "")


def _safe_source(name: str, warnings: list[str], loader, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = loader()
    except Exception as exc:
        warnings.append(f"{name} unavailable: {exc}")
        return fallback
    return payload or fallback


def _fact(kind: str, label: str, severity: DigestSeverity = "neutral", source_ref: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"kind": kind, "label": label, "severity": severity}
    if source_ref:
        payload["source_ref"] = source_ref
    return payload


def _risk(key: str, label: str, severity: DigestSeverity = "warning") -> dict[str, str]:
    return {"key": key, "label": label, "severity": severity}


def _add_news_evidence(news: dict[str, Any], asset_id: str, facts: list[dict[str, Any]], risk_flags: list[dict[str, str]], refs: dict[str, str]) -> int:
    summary = news.get("summary") or {}
    items = list(news.get("items") or [])
    count_7d = int(summary.get("news_count_7d") or len(items) or 0)
    if count_7d <= 0:
        risk_flags.append(_risk("low_news_coverage", "Low accepted-news coverage"))
        return 0
    first = items[0] if items else {}
    if first.get("news_id"):
        refs["news_id"] = str(first["news_id"])
    facts.append(_fact("news", f"{count_7d} accepted news items in 7d", "positive", {"workspace": "news", "news_id": refs.get("news_id", ""), "asset_id": asset_id}))
    quality_bonus = 5 if any((item.get("quality_score") or 0) >= 80 for item in items) else 0
    return min(15, count_7d * 5) + quality_bonus


def _add_research_evidence(reports: dict[str, Any], asset_id: str, facts: list[dict[str, Any]], risk_flags: list[dict[str, str]], refs: dict[str, str]) -> int:
    summary = reports.get("summary") or {}
    items = list(reports.get("items") or [])
    count_90d = int(summary.get("report_count_90d") or len(items) or 0)
    if count_90d <= 0:
        risk_flags.append(_risk("thin_research", "No recent research coverage"))
        return 0
    first = items[0] if items else {}
    if first.get("report_id"):
        refs["report_id"] = str(first["report_id"])
    if first.get("event_key"):
        refs["event_key"] = str(first["event_key"])
    rating = str(summary.get("latest_rating") or first.get("rating") or "").strip()
    label = f"Latest report rating: {rating}" if rating else f"{count_90d} research reports in 90d"
    facts.append(_fact("research", label, "positive", {"workspace": "researchReports", "report_id": refs.get("report_id", ""), "event_key": refs.get("event_key", ""), "asset_id": asset_id}))
    target_bonus = 5 if summary.get("latest_target_price") is not None or first.get("target_price") is not None else 0
    return min(15, count_90d * 5) + target_bonus


def _add_market_evidence(market: dict[str, Any], asset_id: str, facts: list[dict[str, Any]], risk_flags: list[dict[str, str]], refs: dict[str, str]) -> int:
    lists = market.get("emotion_stock_lists") or {}
    for tab, label in [("limit_up", "Appears in EOD limit-up list"), ("auction", "Appears in EOD auction list")]:
        if _contains_asset(lists.get(tab, []), asset_id):
            refs["monitor_tab"] = tab
            facts.append(_fact("market", label, "positive", {"workspace": "market", "asset_id": asset_id, "monitor_tab": tab}))
            return 15
    for tab, key, label in [
        ("broken_limit_up", "market_broken_limit_up", "Recent broken limit-up pressure"),
        ("limit_down", "market_limit_down", "Limit-down pressure"),
    ]:
        if _contains_asset(lists.get(tab, []), asset_id):
            refs["monitor_tab"] = tab
            risk_flags.append(_risk(key, label, "severe"))
            facts.append(_fact("market", label, "negative", {"workspace": "market", "asset_id": asset_id, "monitor_tab": tab}))
            return -10
    return 0


def _contains_asset(rows: list[dict[str, Any]], asset_id: str) -> bool:
    return any(str(row.get("asset_id") or "") == asset_id or str(row.get("symbol") or "") == asset_id for row in rows)


def _add_strategy_evidence(profile: dict[str, Any], facts: list[dict[str, Any]], risk_flags: list[dict[str, str]]) -> int:
    score_row = profile.get("score") or {}
    signals = list(profile.get("signals") or [])
    points = 0
    rank = score_row.get("rank")
    if rank is not None:
        facts.append(_fact("strategy", f"TopN score rank {rank}", "positive"))
        points += 15 if int(rank) <= 20 else 8
    if signals:
        primary = str(signals[0].get("primary_signal") or "signal")
        facts.append(_fact("strategy", f"Watchlist signal: {primary}", "positive"))
        points += 5
        risk_tags = [tag for row in signals for tag in row.get("risk_tags", [])]
        if risk_tags:
            risk_flags.append(_risk("strategy_risk_tags", f"Strategy risk tags: {', '.join(risk_tags[:3])}"))
            points -= 5
    return points


def _bucket(score: int, risk_flags: list[dict[str, str]], facts: list[dict[str, Any]]) -> str:
    severe = any(flag.get("severity") == "severe" for flag in risk_flags)
    if severe or len(risk_flags) >= 3:
        return "risk_heavy"
    categories = {fact["kind"] for fact in facts}
    if score >= 75 and not severe:
        return "strong"
    if score >= 45 and len(categories) >= 2:
        return "mixed"
    return "thin"


def _title(bucket: str) -> str:
    return {
        "strong": "Strong evidence",
        "mixed": "Mixed evidence",
        "risk_heavy": "Risk-heavy evidence",
        "thin": "Thin evidence",
    }[bucket]


def _next_actions(asset_id: str, refs: dict[str, str]) -> list[dict[str, Any]]:
    actions = [
        {"key": "open_news", "label": "Open News", "workspace": "news", "asset_id": asset_id, "query": asset_id},
        {"key": "open_research", "label": "Open Research Reports", "workspace": "researchReports", "asset_id": asset_id, "query": asset_id},
        {"key": "open_market", "label": "Open Market Monitor", "workspace": "market", "asset_id": asset_id, "query": asset_id},
    ]
    for action in actions:
        if action["workspace"] == "news" and refs.get("news_id"):
            action["news_id"] = refs["news_id"]
        if action["workspace"] == "researchReports":
            if refs.get("report_id"):
                action["report_id"] = refs["report_id"]
            if refs.get("event_key"):
                action["event_key"] = refs["event_key"]
        if action["workspace"] == "market" and refs.get("monitor_tab"):
            action["monitor_tab"] = refs["monitor_tab"]
    return actions
```

- [ ] **Step 4: Add FastAPI route**

In `src/stock_research/dashboard/app.py`, import:

```python
from stock_research.dashboard.evidence_digest import build_evidence_digest
```

Add the route near the other read-only dashboard routes:

```python
    @app.get("/api/evidence-digest")
    def evidence_digest_route(
        asset_id: str,
        trade_date: str | None = None,
        lookback_days: int = 90,
        score_version: str = "manual_v1",
    ):
        return build_evidence_digest(
            asset_id,
            trade_date=trade_date,
            lookback_days=lookback_days,
            score_version=score_version,
        )
```

- [ ] **Step 5: Run backend tests**

Run:

```bash
pytest tests/test_dashboard_evidence_digest.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/stock_research/dashboard/evidence_digest.py src/stock_research/dashboard/app.py tests/test_dashboard_evidence_digest.py
git commit -m "feat: add evidence digest endpoint"
```

Before committing, run `git diff --cached --stat` and confirm only Task 1 files are staged.

---

### Task 2: Frontend API Types And Client

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Test: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Add failing client test**

In `dashboard/tests/client.test.ts`, add:

```tsx
it('fetches evidence digest with optional date and lookback', async () => {
  fetchMock.mockResponseOnce(JSON.stringify({
    asset_id: '000001.SZ',
    canonical_asset_id: '000001.SZ',
    trade_date: '2026-06-12',
    title: 'Mixed evidence',
    score: 62,
    bucket: 'mixed',
    facts: [],
    risk_flags: [],
    source_refs: {},
    next_actions: [],
    warnings: []
  }));

  const digest = await fetchEvidenceDigest('000001.SZ', {
    tradeDate: '2026-06-12',
    lookbackDays: 30,
    scoreVersion: 'manual_v2'
  });

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/evidence-digest?asset_id=000001.SZ&trade_date=2026-06-12&lookback_days=30&score_version=manual_v2'
  );
  expect(digest.bucket).toBe('mixed');
});
```

Add `fetchEvidenceDigest` to the import list at the top of the test file.

- [ ] **Step 2: Run failing client test**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts
```

Expected: FAIL because the function and DTOs do not exist.

- [ ] **Step 3: Add TypeScript DTOs**

In `dashboard/src/api/types.ts`, add after the research report types:

```ts
export type EvidenceDigestBucket = 'strong' | 'mixed' | 'thin' | 'risk_heavy';
export type EvidenceDigestSeverity = 'positive' | 'neutral' | 'warning' | 'negative' | 'severe' | string;

export type EvidenceDigestSourceRef = {
  workspace?: 'news' | 'researchReports' | 'market' | 'stock' | string;
  asset_id?: string;
  news_id?: string;
  report_id?: string;
  event_key?: string;
  monitor_tab?: string;
};

export type EvidenceDigestFact = {
  kind: 'news' | 'research' | 'market' | 'strategy' | string;
  label: string;
  severity: EvidenceDigestSeverity;
  source_ref?: EvidenceDigestSourceRef;
};

export type EvidenceDigestRiskFlag = {
  key: string;
  label: string;
  severity: EvidenceDigestSeverity;
};

export type EvidenceDigestAction = {
  key: 'open_news' | 'open_research' | 'open_market' | 'review_stock' | string;
  label: string;
  workspace: 'news' | 'researchReports' | 'market' | 'stock' | string;
  asset_id?: string;
  news_id?: string;
  report_id?: string;
  event_key?: string;
  monitor_tab?: string;
  query?: string;
};

export type EvidenceDigestResponse = {
  asset_id: string;
  canonical_asset_id: string;
  trade_date: string;
  title: string;
  score: number;
  bucket: EvidenceDigestBucket;
  facts: EvidenceDigestFact[];
  risk_flags: EvidenceDigestRiskFlag[];
  source_refs: EvidenceDigestSourceRef;
  next_actions: EvidenceDigestAction[];
  warnings: string[];
};
```

- [ ] **Step 4: Add client function**

In `dashboard/src/api/client.ts`, import `EvidenceDigestResponse` and add parameter type:

```ts
type EvidenceDigestParams = {
  tradeDate?: string;
  lookbackDays?: number;
  scoreVersion?: string;
};
```

Add:

```ts
export async function fetchEvidenceDigest(
  assetId: string,
  params: EvidenceDigestParams = {}
): Promise<EvidenceDigestResponse> {
  const searchParams = new URLSearchParams();
  searchParams.set('asset_id', assetId);
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  if (params.lookbackDays !== undefined) searchParams.set('lookback_days', String(params.lookbackDays));
  if (params.scoreVersion) searchParams.set('score_version', params.scoreVersion);
  return getJson(`/api/evidence-digest?${searchParams.toString()}`);
}
```

- [ ] **Step 5: Run client test**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/tests/client.test.ts
git commit -m "feat: add evidence digest client"
```

Before committing, run `git diff --cached --stat` and confirm only Task 2 files are staged.

---

### Task 3: Stock Detail Evidence Digest Panel

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Test: `dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Extend StockWorkspace API mock and add digest fixture**

In `dashboard/tests/stock-workspace.test.tsx`, add `fetchEvidenceDigest: vi.fn()` to `apiMocks`.

Add:

```tsx
function makeEvidenceDigest(overrides = {}) {
  return {
    asset_id: '000001.SZ',
    canonical_asset_id: '000001.SZ',
    trade_date: '2026-06-12',
    title: 'Mixed evidence',
    score: 62,
    bucket: 'mixed',
    facts: [
      { kind: 'news', label: '2 accepted news items in 7d', severity: 'positive' },
      { kind: 'research', label: 'Latest report rating: 买入', severity: 'positive' }
    ],
    risk_flags: [{ key: 'thin_research', label: 'No recent research coverage', severity: 'warning' }],
    source_refs: { news_id: 'news-1', report_id: 'r1', event_key: 'r1:000001.SZ', monitor_tab: 'limit_up' },
    next_actions: [
      { key: 'open_news', label: 'Open News', workspace: 'news', asset_id: '000001.SZ', news_id: 'news-1', query: '000001.SZ' },
      { key: 'open_research', label: 'Open Research Reports', workspace: 'researchReports', asset_id: '000001.SZ', report_id: 'r1', event_key: 'r1:000001.SZ', query: '000001.SZ' },
      { key: 'open_market', label: 'Open Market Monitor', workspace: 'market', asset_id: '000001.SZ', monitor_tab: 'limit_up', query: '000001.SZ' }
    ],
    warnings: [],
    ...overrides
  };
}
```

In `beforeEach`, add:

```tsx
apiMocks.fetchEvidenceDigest.mockResolvedValue(makeEvidenceDigest());
```

- [ ] **Step 2: Add failing render/action test**

Add:

```tsx
it('renders evidence digest and opens source-backed next actions', async () => {
  const handleOpenNews = vi.fn();
  const handleOpenResearchReports = vi.fn();
  const handleOpenMarketMonitor = vi.fn();

  render(
    <StockWorkspace
      initialAssetId="000001.SZ"
      onOpenNews={handleOpenNews}
      onOpenResearchReports={handleOpenResearchReports}
      onOpenMarketMonitor={handleOpenMarketMonitor}
    />
  );

  expect(await screen.findByRole('heading', { name: 'Evidence Digest' })).toBeInTheDocument();
  expect(screen.getByText('Mixed evidence')).toBeInTheDocument();
  expect(screen.getByText('Score 62')).toBeInTheDocument();
  expect(screen.getByText('2 accepted news items in 7d')).toBeInTheDocument();
  expect(screen.getByText('No recent research coverage')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Open digest news evidence' }));
  fireEvent.click(screen.getByRole('button', { name: 'Open digest research evidence' }));
  fireEvent.click(screen.getByRole('button', { name: 'Open digest market evidence' }));

  expect(handleOpenNews).toHaveBeenCalledWith(expect.objectContaining({ newsId: 'news-1', assetId: '000001.SZ' }));
  expect(handleOpenResearchReports).toHaveBeenCalledWith(expect.objectContaining({ reportId: 'r1', eventKey: 'r1:000001.SZ' }));
  expect(handleOpenMarketMonitor).toHaveBeenCalledWith(expect.objectContaining({ monitorTab: 'limit_up' }));
});
```

- [ ] **Step 3: Add failing local error and stale response tests**

Add:

```tsx
it('shows digest errors locally without hiding the stock profile', async () => {
  apiMocks.fetchEvidenceDigest.mockRejectedValueOnce(new Error('digest offline'));

  render(<StockWorkspace initialAssetId="000001.SZ" />);

  expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
  expect(await screen.findByText('digest offline')).toBeInTheDocument();
});
```

Add:

```tsx
it('does not let stale digest responses overwrite a newer stock', async () => {
  const firstDigest = deferred();
  apiMocks.fetchEvidenceDigest
    .mockReturnValueOnce(firstDigest.promise)
    .mockResolvedValueOnce(makeEvidenceDigest({
      asset_id: '600000.SH',
      canonical_asset_id: '600000.SH',
      title: 'Strong evidence',
      score: 82,
      facts: [{ kind: 'market', label: 'Appears in EOD limit-up list', severity: 'positive' }],
      risk_flags: [],
      source_refs: {},
      next_actions: [],
      warnings: []
    }));
  apiMocks.fetchAssetProfile
    .mockResolvedValueOnce(makeProfile())
    .mockResolvedValueOnce(makeProfile({ asset_id: '600000.SH', canonical_asset_id: '600000.SH', asset: { asset_id: '600000.SH', symbol: '600000', name: '浦发银行', exchange: 'SH', board: null, is_active: true } }));

  render(<StockWorkspace initialAssetId="000001.SZ" />);
  fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
  fireEvent.click(screen.getByRole('button', { name: 'Load Stock' }));

  expect(await screen.findByText('Strong evidence')).toBeInTheDocument();
  firstDigest.resolve(makeEvidenceDigest({ title: 'Old mixed evidence' }));
  await waitFor(() => expect(screen.queryByText('Old mixed evidence')).not.toBeInTheDocument());
});
```

- [ ] **Step 4: Run failing StockWorkspace tests**

Run:

```bash
cd dashboard && npm test -- --run tests/stock-workspace.test.tsx
```

Expected: FAIL because digest fetch/render does not exist.

- [ ] **Step 5: Implement StockWorkspace digest state and fetch**

In `dashboard/src/components/StockWorkspace.tsx`, import:

```tsx
import { fetchAssetNews, fetchAssetProfile, fetchAssetResearchReports, fetchEvidenceDigest, searchAssets } from '../api/client';
import type { EvidenceDigestAction, EvidenceDigestResponse } from '../api/types';
```

Add state:

```tsx
const [evidenceDigest, setEvidenceDigest] = useState<EvidenceDigestResponse | null>(null);
const [isEvidenceDigestLoading, setIsEvidenceDigestLoading] = useState(false);
const [evidenceDigestError, setEvidenceDigestError] = useState<string | null>(null);
const evidenceDigestRequestIdRef = useRef(0);
```

Add effect after profile is available:

```tsx
useEffect(() => {
  if (!profile) {
    evidenceDigestRequestIdRef.current += 1;
    setEvidenceDigest(null);
    setIsEvidenceDigestLoading(false);
    setEvidenceDigestError(null);
    return;
  }
  const requestId = evidenceDigestRequestIdRef.current + 1;
  evidenceDigestRequestIdRef.current = requestId;
  setIsEvidenceDigestLoading(true);
  setEvidenceDigestError(null);
  setEvidenceDigest(null);

  fetchEvidenceDigest(profile.canonical_asset_id, { tradeDate, lookbackDays: 90 })
    .then((digest) => {
      if (mountedRef.current && requestId === evidenceDigestRequestIdRef.current) {
        setEvidenceDigest(digest);
      }
    })
    .catch((err: unknown) => {
      if (mountedRef.current && requestId === evidenceDigestRequestIdRef.current) {
        setEvidenceDigestError(err instanceof Error ? err.message : String(err));
      }
    })
    .finally(() => {
      if (mountedRef.current && requestId === evidenceDigestRequestIdRef.current) {
        setIsEvidenceDigestLoading(false);
      }
    });
}, [profile, tradeDate]);
```

Increment `evidenceDigestRequestIdRef.current` in unmount cleanup.

- [ ] **Step 6: Implement digest action mapper and panel**

Add helper inside component:

```tsx
function openDigestAction(action: EvidenceDigestAction) {
  const context: StockEntryContext = {
    assetId: action.asset_id ?? currentEntryContext.assetId,
    query: action.query ?? currentEntryContext.query,
    newsId: action.news_id,
    reportId: action.report_id,
    eventKey: action.event_key,
    monitorTab: action.monitor_tab
  };
  if (action.workspace === 'news') onOpenNews?.({ ...context, sourceWorkspace: 'news' });
  if (action.workspace === 'researchReports') onOpenResearchReports?.({ ...context, sourceWorkspace: 'researchReports' });
  if (action.workspace === 'market') onOpenMarketMonitor?.({ ...context, sourceWorkspace: 'market' });
}
```

Render this panel near the top of `stock-detail-main`:

```tsx
<section className="workspace-band" aria-label="Evidence Digest panel">
  <div className="section-heading">
    <h2>Evidence Digest</h2>
    {isEvidenceDigestLoading ? <span className="muted">Loading digest...</span> : null}
  </div>
  {evidenceDigestError ? <p className="error-text">{evidenceDigestError}</p> : null}
  {evidenceDigest ? (
    <>
      <div className="metric-row">
        <strong>{evidenceDigest.title}</strong>
        <span>Score {evidenceDigest.score}</span>
      </div>
      <div className="digest-fact-list">
        {evidenceDigest.facts.map((fact) => (
          <span key={`${fact.kind}:${fact.label}`}>{fact.label}</span>
        ))}
      </div>
      {evidenceDigest.risk_flags.length ? (
        <div className="news-stock-row" aria-label="Digest risk flags">
          {evidenceDigest.risk_flags.map((flag) => (
            <span key={flag.key} className="status-chip warning">{flag.label}</span>
          ))}
        </div>
      ) : null}
      <div className="compact-toolbar">
        {evidenceDigest.next_actions.map((action) => (
          <button
            key={action.key}
            type="button"
            onClick={() => openDigestAction(action)}
            aria-label={
              action.workspace === 'news'
                ? 'Open digest news evidence'
                : action.workspace === 'researchReports'
                  ? 'Open digest research evidence'
                  : action.workspace === 'market'
                    ? 'Open digest market evidence'
                    : action.label
            }
          >
            {action.label}
          </button>
        ))}
      </div>
    </>
  ) : null}
</section>
```

Use existing classes; add small CSS only if layout is broken.

- [ ] **Step 7: Run StockWorkspace tests**

Run:

```bash
cd dashboard && npm test -- --run tests/stock-workspace.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit Task 3**

```bash
git add dashboard/src/components/StockWorkspace.tsx dashboard/tests/stock-workspace.test.tsx
git commit -m "feat: show stock evidence digest"
```

Before committing, run `git diff --cached --stat` and confirm only Task 3 files are staged.

---

### Task 4: Home Cockpit Digest Badges

**Files:**
- Modify: `dashboard/src/components/HomeCockpit.tsx`
- Test: `dashboard/tests/home-cockpit.test.tsx`

- [ ] **Step 1: Extend HomeCockpit API mock and tests**

In `dashboard/tests/home-cockpit.test.tsx`, add `fetchEvidenceDigest: vi.fn()` to the `vi.mock('../src/api/client', ...)` block.

In `beforeEach`, add:

```tsx
vi.mocked(api.fetchEvidenceDigest).mockResolvedValue({
  asset_id: 'CN:SZ:300951',
  canonical_asset_id: 'CN:SZ:300951',
  trade_date: '2026-06-08',
  title: 'Strong evidence',
  score: 81,
  bucket: 'strong',
  facts: [],
  risk_flags: [],
  source_refs: {},
  next_actions: [],
  warnings: []
});
```

Add:

```tsx
it('shows evidence digest badges for today focus rows', async () => {
  render(<AppShell />);

  expect(await screen.findByText('Research Cockpit')).toBeInTheDocument();
  expect(await screen.findByText('Strong evidence')).toBeInTheDocument();
  expect(api.fetchEvidenceDigest).toHaveBeenCalledWith('CN:SZ:300951', {
    tradeDate: '2026-06-08',
    lookbackDays: 90
  });
});
```

Add:

```tsx
it('keeps today focus visible when digest loading fails', async () => {
  vi.mocked(api.fetchEvidenceDigest).mockRejectedValueOnce(new Error('digest unavailable'));

  render(<AppShell />);

  expect(await screen.findByText('CN:SZ:300951')).toBeInTheDocument();
  expect(await screen.findByText('Digest unavailable')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run failing HomeCockpit tests**

Run:

```bash
cd dashboard && npm test -- --run tests/home-cockpit.test.tsx
```

Expected: FAIL because Home does not fetch/render digests.

- [ ] **Step 3: Implement digest state and fetches in HomeCockpit**

In `dashboard/src/components/HomeCockpit.tsx`, import `fetchEvidenceDigest` and `EvidenceDigestResponse`.

Add state:

```tsx
const [digestByAsset, setDigestByAsset] = useState<Record<string, EvidenceDigestResponse>>({});
const [digestErrors, setDigestErrors] = useState<Record<string, string>>({});
```

After platform summary is loaded successfully, request top-five digests:

```tsx
const focusRows = summaryResult.value.topn_preview.slice(0, 5);
void Promise.allSettled(
  focusRows.map((row) =>
    fetchEvidenceDigest(row.asset_id, {
      tradeDate: summaryResult.value.latest_market_date,
      lookbackDays: 90
    }).then((digest) => ({ assetId: row.asset_id, digest }))
  )
).then((results) => {
  if (ignore) return;
  const nextDigests: Record<string, EvidenceDigestResponse> = {};
  const nextErrors: Record<string, string> = {};
  results.forEach((result, index) => {
    const assetId = focusRows[index].asset_id;
    if (result.status === 'fulfilled') nextDigests[assetId] = result.value.digest;
    else nextErrors[assetId] = 'Digest unavailable';
  });
  setDigestByAsset(nextDigests);
  setDigestErrors(nextErrors);
});
```

Reset `digestByAsset` and `digestErrors` at effect start.

- [ ] **Step 4: Render badge in Today Focus**

In the Today Focus row:

```tsx
const digest = digestByAsset[row.asset_id];
const digestError = digestErrors[row.asset_id];
```

Render a fourth cell or inline badge:

```tsx
<span className="status-chip neutral">
  {digest?.title ?? digestError ?? 'Digest pending'}
</span>
```

If adding a fourth cell, update the row class or use existing flexible classes so text does not overlap.

- [ ] **Step 5: Run HomeCockpit tests**

Run:

```bash
cd dashboard && npm test -- --run tests/home-cockpit.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add dashboard/src/components/HomeCockpit.tsx dashboard/tests/home-cockpit.test.tsx
git commit -m "feat: show home evidence digest badges"
```

Before committing, run `git diff --cached --stat` and confirm only Task 4 files are staged.

---

### Task 5: Integration Verification And Hygiene

**Files:**
- Modify only files touched by Tasks 1-4 if verification exposes issues.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
pytest tests/test_dashboard_evidence_digest.py tests/test_dashboard_app.py -q
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend tests**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts tests/stock-workspace.test.tsx tests/home-cockpit.test.tsx tests/app-shell.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run dashboard build**

Run:

```bash
cd dashboard && npm run build
```

Expected: PASS with `tsc && vite build`.

- [ ] **Step 4: Run e2e smoke tests**

Run:

```bash
cd dashboard && npm run test:e2e
```

Expected: PASS for the existing e2e suite.

- [ ] **Step 5: Inspect git state**

Run:

```bash
git status --short
git diff --cached --stat
```

Expected:

- `git diff --cached --stat` is empty.
- Existing unrelated dirty files may still appear in `git status --short`; do not stage or revert them.
- Phase 10 commits are separated from unrelated dirty worktree changes.

- [ ] **Step 6: Final review**

Use the verification-before-completion skill before claiming completion. Request final code review over Phase 10 commits. Fix any Critical or Important issues, rerun focused tests/build/e2e, and report the final commit list and verification output.

