# Research Reports Dashboard Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only Research Reports dashboard workspace backed by the existing `research.stock_report_source` and `research.stock_report_event` tables, with Stock Workspace integration.

**Architecture:** Add a focused backend read model in `src/stock_research/dashboard/research_reports.py`, expose three FastAPI routes from `dashboard/app.py`, then add frontend API types/client functions and two UI surfaces: the full Research Reports workspace and a compact Stock Workspace panel. External adapters stay offline/background; the dashboard only reads stored database rows.

**Tech Stack:** FastAPI, psycopg row dictionaries, PostgreSQL, React, TypeScript, Vitest, Testing Library, Playwright smoke tests.

---

## File Structure

- Create `src/stock_research/dashboard/research_reports.py`
  - Owns SQL, filters, pagination, summary counts, and asset-specific report metrics.
  - Exposes `load_research_report_summary`, `list_research_reports`, and `load_asset_research_reports`.
- Modify `src/stock_research/dashboard/app.py`
  - Imports the three backend functions and registers read-only API routes.
- Modify `dashboard/src/api/types.ts`
  - Adds `ResearchReportItem`, `ResearchReportSummary`, `ResearchReportResponse`, and `AssetResearchReportResponse`.
- Modify `dashboard/src/api/client.ts`
  - Adds `fetchResearchReportSummary`, `fetchResearchReports`, and `fetchAssetResearchReports`.
- Modify `dashboard/src/components/ResearchReportsWorkspace.tsx`
  - Replaces the placeholder with summary strip, filters, table, empty state, and detail panel.
- Modify `dashboard/src/components/StockWorkspace.tsx`
  - Loads asset research reports when profile changes and replaces the Phase 3 placeholder panel.
- Modify `dashboard/src/styles.css`
  - Adds compact table/detail/filter styles only where existing classes are insufficient.
- Add `tests/test_dashboard_research_reports.py`
  - Backend unit and route tests with monkeypatched database fetches.
- Modify `tests/test_dashboard_app.py`
  - Adds route-forwarding tests if not included in the new backend test file.
- Modify `dashboard/tests/client.test.ts`
  - Adds client URL tests.
- Add `dashboard/tests/research-reports-workspace.test.tsx`
  - Tests the full workspace.
- Modify `dashboard/tests/stock-workspace.test.tsx`
  - Adds asset report panel and stale-response tests.
- Modify `dashboard/tests/app-smoke.spec.ts`
  - Extends mocks for the new API endpoints if the app shell route touches them.

## Task 1: Backend Research Report Read Model

**Files:**
- Create: `src/stock_research/dashboard/research_reports.py`
- Test: `tests/test_dashboard_research_reports.py`

- [ ] **Step 1: Write failing backend tests for summary, list filters, and asset reports**

Create `tests/test_dashboard_research_reports.py`:

```python
from datetime import date

from stock_research.dashboard import research_reports


def test_research_report_summary_returns_counts(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        if "COUNT(*) AS total_reports" in sql:
            return [
                {
                    "total_reports": 3,
                    "covered_stocks": 2,
                    "latest_publish_date": date(2026, 6, 3),
                    "latest_feature_date": date(2026, 6, 2),
                    "source_count": 2,
                }
            ]
        if "GROUP BY source_name" in sql:
            return [{"source_name": "cfi_ybyl", "rows": 2}]
        if "GROUP BY rating" in sql:
            return [{"rating": "买入", "rows": 2}]
        if "GROUP BY broker" in sql:
            return [{"broker": "华泰证券", "rows": 2}]
        raise AssertionError(sql)

    monkeypatch.setattr(research_reports, "connect", lambda service: DummyConnection())
    monkeypatch.setattr(research_reports, "fetch_all", fake_fetch_all)

    result = research_reports.load_research_report_summary(service="test")

    assert result["total_reports"] == 3
    assert result["covered_stocks"] == 2
    assert result["latest_publish_date"] == "2026-06-03"
    assert result["latest_feature_date"] == "2026-06-02"
    assert result["source_counts"] == [{"source_name": "cfi_ybyl", "rows": 2}]
    assert result["rating_counts"] == [{"rating": "买入", "rows": 2}]
    assert result["broker_counts"] == [{"broker": "华泰证券", "rows": 2}]


def test_list_research_reports_passes_filters_and_pagination(monkeypatch):
    captured = []

    def fake_fetch_all(conn, sql, params=None):
        captured.append((sql, params))
        if "COUNT(*) AS total" in sql:
            return [{"total": 1}]
        return [
            {
                "report_id": "r1",
                "asset_id": "CN:SH:600519",
                "ts_code": "600519.SH",
                "stock_name": "贵州茅台",
                "industry_name": "白酒",
                "report_title": "贵州茅台深度报告",
                "publish_date": date(2026, 6, 3),
                "report_date": date(2026, 6, 3),
                "broker": "华泰证券",
                "analyst": "张三",
                "rating": "买入",
                "rating_change": "维持",
                "target_price": 1900,
                "target_upside": 0.15,
                "source_type": "public_web_search_result",
                "source_name": "cfi_ybyl",
                "source_confidence": 0.8,
                "public_access": True,
                "copyright_note": "metadata only",
                "source_url": "https://example.com/r1",
                "raw_summary": "summary",
                "company_view": "company",
                "industry_view": "industry",
                "risk_summary": "risk",
                "metadata": {"provider": "test"},
            }
        ]

    monkeypatch.setattr(research_reports, "connect", lambda service: DummyConnection())
    monkeypatch.setattr(research_reports, "fetch_all", fake_fetch_all)

    result = research_reports.list_research_reports(
        q="茅台",
        broker="华泰",
        rating="买入",
        source_name="cfi_ybyl",
        start_date="2026-06-01",
        end_date="2026-06-05",
        has_target_price=True,
        limit=25,
        offset=5,
        service="test",
    )

    assert result["total"] == 1
    assert result["limit"] == 25
    assert result["offset"] == 5
    assert result["items"][0]["stock_name"] == "贵州茅台"
    assert result["items"][0]["publish_date"] == "2026-06-03"
    list_sql, list_params = captured[1]
    assert "target_price IS NOT NULL" in list_sql
    assert "s.broker ILIKE %s" in list_sql
    assert list_params[-2:] == [25, 5]


def test_load_asset_research_reports_returns_summary(monkeypatch):
    def fake_fetch_all(conn, sql, params=None):
        if "COUNT(*) FILTER" in sql:
            return [
                {
                    "report_count_30d": 2,
                    "report_count_90d": 4,
                    "broker_coverage_count_90d": 3,
                    "latest_report_date": date(2026, 6, 3),
                    "latest_rating": "买入",
                    "latest_target_price": 1900,
                }
            ]
        return [
            {
                "report_id": "r1",
                "asset_id": "CN:SH:600519",
                "ts_code": "600519.SH",
                "stock_name": "贵州茅台",
                "industry_name": "白酒",
                "report_title": "贵州茅台深度报告",
                "publish_date": date(2026, 6, 3),
                "report_date": date(2026, 6, 3),
                "broker": "华泰证券",
                "analyst": "",
                "rating": "买入",
                "rating_change": "",
                "target_price": 1900,
                "target_upside": None,
                "source_type": "public_web_search_result",
                "source_name": "cfi_ybyl",
                "source_confidence": 0.8,
                "public_access": True,
                "copyright_note": "metadata only",
                "source_url": "https://example.com/r1",
                "raw_summary": "",
                "company_view": "",
                "industry_view": "",
                "risk_summary": "",
                "metadata": {},
            }
        ]

    monkeypatch.setattr(research_reports, "connect", lambda service: DummyConnection())
    monkeypatch.setattr(research_reports, "fetch_all", fake_fetch_all)

    result = research_reports.load_asset_research_reports("600519.SH", limit=5, lookback_days=90, service="test")

    assert result["asset_id"] == "600519.SH"
    assert result["summary"]["report_count_90d"] == 4
    assert result["summary"]["latest_rating"] == "买入"
    assert result["items"][0]["report_title"] == "贵州茅台深度报告"


class DummyConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_research_reports.py -v
```

Expected: fail with `ImportError` or missing `stock_research.dashboard.research_reports`.

- [ ] **Step 3: Implement backend read model**

Create `src/stock_research/dashboard/research_reports.py`:

```python
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


MAX_LIMIT = 200
DEFAULT_LIMIT = 50


def load_research_report_summary(service: str = SETTINGS.research_service) -> dict[str, Any]:
    with connect(service) as conn:
        summary_rows = fetch_all(
            conn,
            """
            SELECT
                COUNT(*) AS total_reports,
                COUNT(DISTINCT e.ts_code) AS covered_stocks,
                MAX(s.publish_date) AS latest_publish_date,
                (SELECT MAX(trade_date) FROM research.stock_report_feature_daily) AS latest_feature_date,
                COUNT(DISTINCT s.source_name) AS source_count
            FROM research.stock_report_source s
            JOIN research.stock_report_event e USING (report_id)
            """,
        )
        source_counts = fetch_all(
            conn,
            """
            SELECT s.source_name, COUNT(*) AS rows
            FROM research.stock_report_source s
            GROUP BY source_name
            ORDER BY rows DESC, source_name
            LIMIT 20
            """,
        )
        rating_counts = fetch_all(
            conn,
            """
            SELECT NULLIF(TRIM(e.rating), '') AS rating, COUNT(*) AS rows
            FROM research.stock_report_event e
            GROUP BY rating
            ORDER BY rows DESC NULLS LAST
            LIMIT 20
            """,
        )
        broker_counts = fetch_all(
            conn,
            """
            SELECT NULLIF(TRIM(s.broker), '') AS broker, COUNT(*) AS rows
            FROM research.stock_report_source s
            GROUP BY broker
            ORDER BY rows DESC NULLS LAST
            LIMIT 20
            """,
        )
    summary = summary_rows[0] if summary_rows else {}
    return {
        "total_reports": int(summary.get("total_reports") or 0),
        "covered_stocks": int(summary.get("covered_stocks") or 0),
        "latest_publish_date": _date_to_string(summary.get("latest_publish_date")),
        "latest_feature_date": _date_to_string(summary.get("latest_feature_date")),
        "source_count": int(summary.get("source_count") or 0),
        "source_counts": [_count_row(row, "source_name") for row in source_counts],
        "rating_counts": [_count_row(row, "rating") for row in rating_counts],
        "broker_counts": [_count_row(row, "broker") for row in broker_counts],
    }


def list_research_reports(
    *,
    q: str | None = None,
    asset_id: str | None = None,
    ts_code: str | None = None,
    broker: str | None = None,
    rating: str | None = None,
    source_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    has_target_price: bool | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    clauses, params = _build_filters(
        q=q,
        asset_id=asset_id,
        ts_code=ts_code,
        broker=broker,
        rating=rating,
        source_name=source_name,
        start_date=start_date,
        end_date=end_date,
        has_target_price=has_target_price,
    )
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    bounded_limit = _bounded_limit(limit)
    bounded_offset = max(0, int(offset or 0))
    with connect(service) as conn:
        total_rows = fetch_all(
            conn,
            f"""
            SELECT COUNT(*) AS total
            FROM research.stock_report_source s
            JOIN research.stock_report_event e USING (report_id)
            {where_sql}
            """,
            params,
        )
        rows = fetch_all(
            conn,
            f"""
            SELECT
                s.report_id, e.asset_id, e.ts_code, e.stock_name, e.industry_name,
                s.report_title, s.publish_date, e.report_date, s.broker, s.analyst,
                e.rating, e.rating_change, e.target_price, e.target_upside,
                s.source_type, s.source_name, s.source_confidence, s.public_access,
                s.copyright_note, s.source_url, s.raw_summary,
                e.company_view, e.industry_view, e.risk_summary,
                COALESCE(e.metadata, '{{}}'::jsonb) || COALESCE(s.metadata, '{{}}'::jsonb) AS metadata
            FROM research.stock_report_source s
            JOIN research.stock_report_event e USING (report_id)
            {where_sql}
            ORDER BY s.publish_date DESC NULLS LAST, s.updated_at DESC, s.report_id
            LIMIT %s OFFSET %s
            """,
            [*params, bounded_limit, bounded_offset],
        )
    total = int(total_rows[0]["total"]) if total_rows else 0
    return {
        "items": [_report_row(row) for row in rows],
        "total": total,
        "limit": bounded_limit,
        "offset": bounded_offset,
        "warnings": [] if rows else ["no matching research reports"],
    }


def load_asset_research_reports(
    asset_id: str,
    *,
    limit: int = 10,
    lookback_days: int = 90,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    bounded_limit = _bounded_limit(limit)
    bounded_lookback = max(1, int(lookback_days or 90))
    with connect(service) as conn:
        summary_rows = fetch_all(
            conn,
            """
            SELECT
                COUNT(*) FILTER (WHERE s.publish_date >= CURRENT_DATE - INTERVAL '30 days') AS report_count_30d,
                COUNT(*) FILTER (WHERE s.publish_date >= CURRENT_DATE - (%s::int * INTERVAL '1 day')) AS report_count_90d,
                COUNT(DISTINCT NULLIF(TRIM(s.broker), '')) FILTER (
                    WHERE s.publish_date >= CURRENT_DATE - (%s::int * INTERVAL '1 day')
                ) AS broker_coverage_count_90d,
                MAX(s.publish_date) AS latest_report_date,
                (ARRAY_AGG(NULLIF(TRIM(e.rating), '') ORDER BY s.publish_date DESC NULLS LAST, s.updated_at DESC))[1] AS latest_rating,
                (ARRAY_AGG(e.target_price ORDER BY s.publish_date DESC NULLS LAST, s.updated_at DESC)
                    FILTER (WHERE e.target_price IS NOT NULL))[1] AS latest_target_price
            FROM research.stock_report_source s
            JOIN research.stock_report_event e USING (report_id)
            WHERE e.asset_id = %s OR e.ts_code = %s
            """,
            [bounded_lookback, bounded_lookback, asset_id, asset_id],
        )
        rows = fetch_all(
            conn,
            """
            SELECT
                s.report_id, e.asset_id, e.ts_code, e.stock_name, e.industry_name,
                s.report_title, s.publish_date, e.report_date, s.broker, s.analyst,
                e.rating, e.rating_change, e.target_price, e.target_upside,
                s.source_type, s.source_name, s.source_confidence, s.public_access,
                s.copyright_note, s.source_url, s.raw_summary,
                e.company_view, e.industry_view, e.risk_summary,
                COALESCE(e.metadata, '{}'::jsonb) || COALESCE(s.metadata, '{}'::jsonb) AS metadata
            FROM research.stock_report_source s
            JOIN research.stock_report_event e USING (report_id)
            WHERE e.asset_id = %s OR e.ts_code = %s
            ORDER BY s.publish_date DESC NULLS LAST, s.updated_at DESC, s.report_id
            LIMIT %s
            """,
            [asset_id, asset_id, bounded_limit],
        )
    summary = summary_rows[0] if summary_rows else {}
    return {
        "asset_id": asset_id,
        "summary": {
            "report_count_30d": int(summary.get("report_count_30d") or 0),
            "report_count_90d": int(summary.get("report_count_90d") or 0),
            "broker_coverage_count_90d": int(summary.get("broker_coverage_count_90d") or 0),
            "latest_report_date": _date_to_string(summary.get("latest_report_date")),
            "latest_rating": str(summary.get("latest_rating") or ""),
            "latest_target_price": _number_or_none(summary.get("latest_target_price")),
        },
        "items": [_report_row(row) for row in rows],
        "warnings": [] if rows else ["no research reports for asset"],
    }


def _build_filters(**filters: Any) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    q = _clean(filters.get("q"))
    if q:
        term = f"%{q}%"
        clauses.append(
            "(e.ts_code ILIKE %s OR e.stock_name ILIKE %s OR s.report_title ILIKE %s OR s.broker ILIKE %s)"
        )
        params.extend([term, term, term, term])
    for column, value in [
        ("e.asset_id", filters.get("asset_id")),
        ("e.ts_code", filters.get("ts_code")),
        ("s.source_name", filters.get("source_name")),
    ]:
        text = _clean(value)
        if text:
            clauses.append(f"{column} = %s")
            params.append(text)
    broker = _clean(filters.get("broker"))
    if broker:
        clauses.append("s.broker ILIKE %s")
        params.append(f"%{broker}%")
    rating = _clean(filters.get("rating"))
    if rating:
        clauses.append("e.rating = %s")
        params.append(rating)
    start_date = _clean(filters.get("start_date"))
    if start_date:
        clauses.append("s.publish_date >= %s")
        params.append(start_date)
    end_date = _clean(filters.get("end_date"))
    if end_date:
        clauses.append("s.publish_date <= %s")
        params.append(end_date)
    if filters.get("has_target_price") is True:
        clauses.append("e.target_price IS NOT NULL")
    elif filters.get("has_target_price") is False:
        clauses.append("e.target_price IS NULL")
    return clauses, params


def _report_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_id": str(row.get("report_id") or ""),
        "asset_id": str(row.get("asset_id") or ""),
        "ts_code": str(row.get("ts_code") or ""),
        "stock_name": str(row.get("stock_name") or ""),
        "industry_name": str(row.get("industry_name") or ""),
        "report_title": str(row.get("report_title") or ""),
        "publish_date": _date_to_string(row.get("publish_date")),
        "report_date": _date_to_string(row.get("report_date")),
        "broker": str(row.get("broker") or ""),
        "analyst": str(row.get("analyst") or ""),
        "rating": str(row.get("rating") or ""),
        "rating_change": str(row.get("rating_change") or ""),
        "target_price": _number_or_none(row.get("target_price")),
        "target_upside": _number_or_none(row.get("target_upside")),
        "source_type": str(row.get("source_type") or ""),
        "source_name": str(row.get("source_name") or ""),
        "source_confidence": _number_or_none(row.get("source_confidence")),
        "public_access": bool(row.get("public_access")),
        "copyright_note": str(row.get("copyright_note") or ""),
        "source_url": str(row.get("source_url") or ""),
        "raw_summary": str(row.get("raw_summary") or ""),
        "company_view": str(row.get("company_view") or ""),
        "industry_view": str(row.get("industry_view") or ""),
        "risk_summary": str(row.get("risk_summary") or ""),
        "metadata": dict(row.get("metadata") or {}),
    }


def _count_row(row: dict[str, Any], key: str) -> dict[str, Any]:
    return {key: str(row.get(key) or ""), "rows": int(row.get("rows") or 0)}


def _bounded_limit(limit: int) -> int:
    return max(1, min(MAX_LIMIT, int(limit or DEFAULT_LIMIT)))


def _clean(value: object) -> str:
    return str(value or "").strip()


def _date_to_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _number_or_none(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None
```

- [ ] **Step 4: Run backend read model tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_research_reports.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit backend read model**

```bash
git add src/stock_research/dashboard/research_reports.py tests/test_dashboard_research_reports.py
git commit -m "feat: add research report read model"
```

## Task 2: FastAPI Routes

**Files:**
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `tests/test_dashboard_research_reports.py`

- [ ] **Step 1: Add failing route tests**

Append to `tests/test_dashboard_research_reports.py`:

```python
from fastapi.testclient import TestClient
from stock_research.dashboard import app as dashboard_app


def test_research_report_summary_route(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "load_research_report_summary",
        lambda: {
            "total_reports": 3,
            "covered_stocks": 2,
            "latest_publish_date": "2026-06-03",
            "latest_feature_date": "2026-06-02",
            "source_count": 2,
            "source_counts": [],
            "rating_counts": [],
            "broker_counts": [],
        },
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research-reports/summary")

    assert response.status_code == 200
    assert response.json()["total_reports"] == 3


def test_research_reports_route_forwards_filters(monkeypatch):
    captured = {}

    def fake_list_research_reports(**kwargs):
        captured.update(kwargs)
        return {"items": [], "total": 0, "limit": kwargs["limit"], "offset": kwargs["offset"], "warnings": []}

    monkeypatch.setattr(dashboard_app, "list_research_reports", fake_list_research_reports)
    client = TestClient(dashboard_app.create_app())

    response = client.get(
        "/api/research-reports?q=%E8%8C%85%E5%8F%B0&broker=%E5%8D%8E%E6%B3%B0"
        "&rating=%E4%B9%B0%E5%85%A5&source_name=cfi_ybyl&start_date=2026-06-01"
        "&end_date=2026-06-05&has_target_price=true&limit=25&offset=5"
    )

    assert response.status_code == 200
    assert captured == {
        "q": "茅台",
        "asset_id": None,
        "ts_code": None,
        "broker": "华泰",
        "rating": "买入",
        "source_name": "cfi_ybyl",
        "start_date": "2026-06-01",
        "end_date": "2026-06-05",
        "has_target_price": True,
        "limit": 25,
        "offset": 5,
    }


def test_asset_research_reports_route(monkeypatch):
    captured = {}

    def fake_load_asset_research_reports(asset_id, limit, lookback_days):
        captured["args"] = [asset_id, limit, lookback_days]
        return {"asset_id": asset_id, "summary": {"report_count_90d": 4}, "items": [], "warnings": []}

    monkeypatch.setattr(dashboard_app, "load_asset_research_reports", fake_load_asset_research_reports)
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/assets/600519.SH/research-reports?limit=5&lookback_days=90")

    assert response.status_code == 200
    assert captured["args"] == ["600519.SH", 5, 90]
    assert response.json()["summary"]["report_count_90d"] == 4
```

- [ ] **Step 2: Run route tests to verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_research_reports.py -k "route or forwards" -v
```

Expected: fail because routes/imports are missing.

- [ ] **Step 3: Wire routes in app.py**

Modify `src/stock_research/dashboard/app.py`.

Add import near the other dashboard imports:

```python
from stock_research.dashboard.research_reports import (
    list_research_reports,
    load_asset_research_reports,
    load_research_report_summary,
)
```

Add routes after public news routes:

```python
    @app.get("/api/research-reports/summary")
    def research_report_summary():
        return load_research_report_summary()

    @app.get("/api/research-reports")
    def research_reports(
        q: str | None = None,
        asset_id: str | None = None,
        ts_code: str | None = None,
        broker: str | None = None,
        rating: str | None = None,
        source_name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        has_target_price: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        return list_research_reports(
            q=q,
            asset_id=asset_id,
            ts_code=ts_code,
            broker=broker,
            rating=rating,
            source_name=source_name,
            start_date=start_date,
            end_date=end_date,
            has_target_price=has_target_price,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/assets/{asset_id}/research-reports")
    def asset_research_reports(asset_id: str, limit: int = 10, lookback_days: int = 90):
        return load_asset_research_reports(asset_id, limit=limit, lookback_days=lookback_days)
```

- [ ] **Step 4: Run route and existing app tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_research_reports.py tests/test_dashboard_app.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit API routes**

```bash
git add src/stock_research/dashboard/app.py tests/test_dashboard_research_reports.py
git commit -m "feat: expose research report dashboard APIs"
```

## Task 3: Frontend API Client and Types

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write failing client tests**

Append to `dashboard/tests/client.test.ts`:

```ts
import {
  fetchAssetResearchReports,
  fetchResearchReportSummary,
  fetchResearchReports
} from '../src/api/client';

it('fetches research report summary', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ total_reports: 57418, covered_stocks: 3367, source_counts: [] })
  });
  vi.stubGlobal('fetch', fetchMock);

  const result = await fetchResearchReportSummary();

  expect(fetchMock).toHaveBeenCalledWith('/api/research-reports/summary');
  expect(result.total_reports).toBe(57418);
});

it('fetches research reports with filters', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ items: [{ report_id: 'r1', stock_name: '贵州茅台' }], total: 1, limit: 25, offset: 5, warnings: [] })
  });
  vi.stubGlobal('fetch', fetchMock);

  const result = await fetchResearchReports({
    q: '茅台',
    broker: '华泰',
    rating: '买入',
    source_name: 'cfi_ybyl',
    start_date: '2026-06-01',
    end_date: '2026-06-05',
    has_target_price: true,
    limit: 25,
    offset: 5
  });

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/research-reports?q=%E8%8C%85%E5%8F%B0&broker=%E5%8D%8E%E6%B3%B0&rating=%E4%B9%B0%E5%85%A5' +
      '&source_name=cfi_ybyl&start_date=2026-06-01&end_date=2026-06-05&has_target_price=true&limit=25&offset=5'
  );
  expect(result.items[0].stock_name).toBe('贵州茅台');
});

it('fetches asset research reports', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ asset_id: '600519.SH', summary: { report_count_90d: 4 }, items: [], warnings: [] })
  });
  vi.stubGlobal('fetch', fetchMock);

  const result = await fetchAssetResearchReports('600519.SH', { limit: 5, lookbackDays: 90 });

  expect(fetchMock).toHaveBeenCalledWith('/api/assets/600519.SH/research-reports?limit=5&lookback_days=90');
  expect(result.summary.report_count_90d).toBe(4);
});
```

- [ ] **Step 2: Run client tests to verify they fail**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts
```

Expected: fail because new functions/types do not exist.

- [ ] **Step 3: Add frontend types**

Append to `dashboard/src/api/types.ts`:

```ts
export type ResearchReportCount = {
  rows: number;
  source_name?: string;
  rating?: string;
  broker?: string;
};

export type ResearchReportSummary = {
  total_reports: number;
  covered_stocks: number;
  latest_publish_date: string | null;
  latest_feature_date: string | null;
  source_count: number;
  source_counts: ResearchReportCount[];
  rating_counts: ResearchReportCount[];
  broker_counts: ResearchReportCount[];
};

export type ResearchReportItem = {
  report_id: string;
  asset_id: string;
  ts_code: string;
  stock_name: string;
  industry_name: string;
  report_title: string;
  publish_date: string | null;
  report_date: string | null;
  broker: string;
  analyst: string;
  rating: string;
  rating_change: string;
  target_price: number | null;
  target_upside: number | null;
  source_type: string;
  source_name: string;
  source_confidence: number | null;
  public_access: boolean;
  copyright_note: string;
  source_url: string;
  raw_summary: string;
  company_view: string;
  industry_view: string;
  risk_summary: string;
  metadata: Record<string, unknown>;
};

export type ResearchReportResponse = {
  items: ResearchReportItem[];
  total: number;
  limit: number;
  offset: number;
  warnings: string[];
};

export type AssetResearchReportSummary = {
  report_count_30d: number;
  report_count_90d: number;
  broker_coverage_count_90d: number;
  latest_report_date: string | null;
  latest_rating: string;
  latest_target_price: number | null;
};

export type AssetResearchReportResponse = {
  asset_id: string;
  summary: AssetResearchReportSummary;
  items: ResearchReportItem[];
  warnings: string[];
};
```

- [ ] **Step 4: Add frontend client functions**

Modify the import list in `dashboard/src/api/client.ts` to include:

```ts
  AssetResearchReportResponse,
  ResearchReportResponse,
  ResearchReportSummary,
```

Add parameter types near `PublicNewsParams`:

```ts
type ResearchReportParams = {
  q?: string;
  asset_id?: string;
  ts_code?: string;
  broker?: string;
  rating?: string;
  source_name?: string;
  start_date?: string;
  end_date?: string;
  has_target_price?: boolean;
  limit?: number;
  offset?: number;
};
```

Add functions after public news functions:

```ts
export async function fetchResearchReportSummary(): Promise<ResearchReportSummary> {
  return getJson('/api/research-reports/summary');
}

export async function fetchResearchReports(params: ResearchReportParams = {}): Promise<ResearchReportResponse> {
  const searchParams = new URLSearchParams();
  if (params.q) searchParams.set('q', params.q);
  if (params.asset_id) searchParams.set('asset_id', params.asset_id);
  if (params.ts_code) searchParams.set('ts_code', params.ts_code);
  if (params.broker) searchParams.set('broker', params.broker);
  if (params.rating) searchParams.set('rating', params.rating);
  if (params.source_name) searchParams.set('source_name', params.source_name);
  if (params.start_date) searchParams.set('start_date', params.start_date);
  if (params.end_date) searchParams.set('end_date', params.end_date);
  if (params.has_target_price !== undefined) searchParams.set('has_target_price', String(params.has_target_price));
  searchParams.set('limit', String(params.limit ?? 50));
  searchParams.set('offset', String(params.offset ?? 0));
  return getJson(`/api/research-reports?${searchParams.toString()}`);
}

export async function fetchAssetResearchReports(
  assetId: string,
  options: { limit?: number; lookbackDays?: number } = {}
): Promise<AssetResearchReportResponse> {
  const searchParams = new URLSearchParams();
  searchParams.set('limit', String(options.limit ?? 10));
  searchParams.set('lookback_days', String(options.lookbackDays ?? 90));
  return getJson(`/api/assets/${encodeURIComponent(assetId)}/research-reports?${searchParams.toString()}`);
}
```

- [ ] **Step 5: Run client tests**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts
```

Expected: all client tests pass.

- [ ] **Step 6: Commit frontend API client**

```bash
git add dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/tests/client.test.ts
git commit -m "feat: add research report client APIs"
```

## Task 4: Research Reports Workspace UI

**Files:**
- Modify: `dashboard/src/components/ResearchReportsWorkspace.tsx`
- Modify: `dashboard/src/styles.css`
- Add: `dashboard/tests/research-reports-workspace.test.tsx`

- [ ] **Step 1: Write failing workspace tests**

Create `dashboard/tests/research-reports-workspace.test.tsx`:

```tsx
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ResearchReportsWorkspace } from '../src/components/ResearchReportsWorkspace';
import type { ResearchReportItem } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchResearchReportSummary: vi.fn(),
  fetchResearchReports: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function makeReport(overrides: Partial<ResearchReportItem> = {}): ResearchReportItem {
  return {
    report_id: 'r1',
    asset_id: 'CN:SH:600519',
    ts_code: '600519.SH',
    stock_name: '贵州茅台',
    industry_name: '白酒',
    report_title: '贵州茅台深度报告',
    publish_date: '2026-06-03',
    report_date: '2026-06-03',
    broker: '华泰证券',
    analyst: '张三',
    rating: '买入',
    rating_change: '维持',
    target_price: 1900,
    target_upside: 0.15,
    source_type: 'public_web_search_result',
    source_name: 'cfi_ybyl',
    source_confidence: 0.8,
    public_access: true,
    copyright_note: 'metadata only',
    source_url: 'https://example.com/r1',
    raw_summary: 'summary',
    company_view: 'company view',
    industry_view: 'industry view',
    risk_summary: 'risk',
    metadata: {},
    ...overrides
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.fetchResearchReportSummary.mockResolvedValue({
    total_reports: 57418,
    covered_stocks: 3367,
    latest_publish_date: '2026-06-03',
    latest_feature_date: '2026-06-02',
    source_count: 6,
    source_counts: [{ source_name: 'cfi_ybyl', rows: 29228 }],
    rating_counts: [{ rating: '买入', rows: 10065 }],
    broker_counts: [{ broker: '华泰证券', rows: 1041 }]
  });
  apiMocks.fetchResearchReports.mockResolvedValue({
    items: [makeReport()],
    total: 1,
    limit: 50,
    offset: 0,
    warnings: []
  });
});

afterEach(() => {
  cleanup();
});

describe('ResearchReportsWorkspace', () => {
  it('loads summary and report rows', async () => {
    render(<ResearchReportsWorkspace />);

    expect(await screen.findByText('57,418')).toBeInTheDocument();
    expect(await screen.findByText('贵州茅台深度报告')).toBeInTheDocument();
    expect(screen.getByText('华泰证券')).toBeInTheDocument();
    expect(screen.getByText('买入')).toBeInTheDocument();
  });

  it('submits filters to the API', async () => {
    render(<ResearchReportsWorkspace />);

    await screen.findByText('贵州茅台深度报告');
    fireEvent.change(screen.getByLabelText('research report query'), { target: { value: '茅台' } });
    fireEvent.change(screen.getByLabelText('research report broker'), { target: { value: '华泰' } });
    fireEvent.change(screen.getByLabelText('research report rating'), { target: { value: '买入' } });
    fireEvent.click(screen.getByLabelText('research report has target price'));
    fireEvent.click(screen.getByRole('button', { name: 'Search Reports' }));

    await waitFor(() => {
      expect(apiMocks.fetchResearchReports).toHaveBeenLastCalledWith(
        expect.objectContaining({ q: '茅台', broker: '华泰', rating: '买入', has_target_price: true })
      );
    });
  });

  it('opens report details from a selected row', async () => {
    render(<ResearchReportsWorkspace />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open report 贵州茅台深度报告' }));

    expect(screen.getByRole('heading', { name: '贵州茅台深度报告' })).toBeInTheDocument();
    expect(screen.getByText('company view')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Source' })).toHaveAttribute('href', 'https://example.com/r1');
  });

  it('shows an empty state', async () => {
    apiMocks.fetchResearchReports.mockResolvedValueOnce({ items: [], total: 0, limit: 50, offset: 0, warnings: [] });

    render(<ResearchReportsWorkspace />);

    expect(await screen.findByText('No matching research reports.')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run workspace tests to verify they fail**

Run:

```bash
cd dashboard && npm test -- --run tests/research-reports-workspace.test.tsx
```

Expected: fail because the component is still a placeholder.

- [ ] **Step 3: Implement ResearchReportsWorkspace**

Replace `dashboard/src/components/ResearchReportsWorkspace.tsx` with:

```tsx
import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { fetchResearchReportSummary, fetchResearchReports } from '../api/client';
import type { ResearchReportItem, ResearchReportResponse, ResearchReportSummary } from '../api/types';

const DEFAULT_START_DATE = '2026-03-01';
const DEFAULT_END_DATE = '2026-06-11';

function formatNumber(value: number | null | undefined) {
  return typeof value === 'number' ? value.toLocaleString() : '-';
}

function formatMaybe(value: unknown) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  if (typeof value === 'string' && value) {
    return value;
  }
  return '-';
}

export function ResearchReportsWorkspace() {
  const [summary, setSummary] = useState<ResearchReportSummary | null>(null);
  const [payload, setPayload] = useState<ResearchReportResponse>({ items: [], total: 0, limit: 50, offset: 0, warnings: [] });
  const [selectedReport, setSelectedReport] = useState<ResearchReportItem | null>(null);
  const [query, setQuery] = useState('');
  const [broker, setBroker] = useState('');
  const [rating, setRating] = useState('');
  const [sourceName, setSourceName] = useState('');
  const [startDate, setStartDate] = useState(DEFAULT_START_DATE);
  const [endDate, setEndDate] = useState(DEFAULT_END_DATE);
  const [hasTargetPrice, setHasTargetPrice] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(false);
  const requestIdRef = useRef(0);

  const loadReports = useCallback(() => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsLoading(true);
    setError(null);
    fetchResearchReports({
      q: query,
      broker,
      rating,
      source_name: sourceName,
      start_date: startDate,
      end_date: endDate,
      has_target_price: hasTargetPrice || undefined,
      limit: 50,
      offset: 0
    })
      .then((nextPayload) => {
        if (mountedRef.current && requestId === requestIdRef.current) {
          setPayload(nextPayload);
          setSelectedReport(nextPayload.items[0] ?? null);
        }
      })
      .catch((err: unknown) => {
        if (mountedRef.current && requestId === requestIdRef.current) {
          setError(err instanceof Error ? err.message : String(err));
          setPayload({ items: [], total: 0, limit: 50, offset: 0, warnings: [] });
          setSelectedReport(null);
        }
      })
      .finally(() => {
        if (mountedRef.current && requestId === requestIdRef.current) {
          setIsLoading(false);
        }
      });
  }, [broker, endDate, hasTargetPrice, query, rating, sourceName, startDate]);

  useEffect(() => {
    mountedRef.current = true;
    fetchResearchReportSummary().then(setSummary).catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
    loadReports();
    return () => {
      mountedRef.current = false;
      requestIdRef.current += 1;
    };
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    loadReports();
  }

  return (
    <section className="workspace-stack" aria-label="Research Reports workspace">
      <header className="workspace-header">
        <h1>Research Reports</h1>
        <p className="muted">External broker and institution report metadata from the local research database.</p>
      </header>

      <section className="stock-summary-strip" aria-label="Research report freshness">
        <div><span>Total Reports</span><strong>{formatNumber(summary?.total_reports)}</strong></div>
        <div><span>Covered Stocks</span><strong>{formatNumber(summary?.covered_stocks)}</strong></div>
        <div><span>Latest Report</span><strong>{summary?.latest_publish_date ?? '-'}</strong></div>
        <div><span>Sources</span><strong>{formatNumber(summary?.source_count)}</strong></div>
      </section>

      <form className="compact-toolbar research-report-toolbar" onSubmit={handleSubmit}>
        <label>Search<input aria-label="research report query" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        <label>Broker<input aria-label="research report broker" value={broker} onChange={(event) => setBroker(event.target.value)} /></label>
        <label>Rating<input aria-label="research report rating" value={rating} onChange={(event) => setRating(event.target.value)} /></label>
        <label>Source<input aria-label="research report source" value={sourceName} onChange={(event) => setSourceName(event.target.value)} /></label>
        <label>Start<input aria-label="research report start date" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
        <label>End<input aria-label="research report end date" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
        <label className="inline-check"><input aria-label="research report has target price" type="checkbox" checked={hasTargetPrice} onChange={(event) => setHasTargetPrice(event.target.checked)} /> Has target</label>
        <button type="submit">Search Reports</button>
        {isLoading ? <span className="muted">Loading reports...</span> : null}
      </form>

      {error ? <p className="error-text">{error}</p> : null}

      <section className="research-report-layout">
        <div className="workspace-band">
          <div className="section-heading">
            <h2>Report Library</h2>
            <span className="muted">{formatNumber(payload.total)} matches</span>
          </div>
          <table className="compact-table research-report-table">
            <thead>
              <tr>
                <th>Date</th><th>Stock</th><th>Title</th><th>Broker</th><th>Rating</th><th>Target</th><th>Source</th><th></th>
              </tr>
            </thead>
            <tbody>
              {payload.items.map((item) => (
                <tr key={item.report_id}>
                  <td>{item.publish_date ?? item.report_date ?? '-'}</td>
                  <td><strong>{item.stock_name}</strong><span>{item.ts_code}</span></td>
                  <td>{item.report_title}</td>
                  <td>{item.broker}</td>
                  <td>{item.rating || '-'}</td>
                  <td>{formatMaybe(item.target_price)}</td>
                  <td>{item.source_name}</td>
                  <td><button type="button" onClick={() => setSelectedReport(item)} aria-label={`Open report ${item.report_title}`}>Details</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!isLoading && payload.items.length === 0 ? <p className="muted">No matching research reports.</p> : null}
        </div>

        <aside className="workspace-band research-report-detail" aria-label="Research report detail">
          {selectedReport ? (
            <>
              <div className="section-heading"><h2>{selectedReport.report_title}</h2><span className="status-chip neutral">{selectedReport.source_name}</span></div>
              <dl className="detail-grid">
                <div><dt>Stock</dt><dd>{selectedReport.stock_name} {selectedReport.ts_code}</dd></div>
                <div><dt>Broker</dt><dd>{selectedReport.broker || '-'}</dd></div>
                <div><dt>Analyst</dt><dd>{selectedReport.analyst || '-'}</dd></div>
                <div><dt>Rating</dt><dd>{selectedReport.rating || '-'}</dd></div>
                <div><dt>Target Price</dt><dd>{formatMaybe(selectedReport.target_price)}</dd></div>
                <div><dt>Confidence</dt><dd>{formatMaybe(selectedReport.source_confidence)}</dd></div>
              </dl>
              <p>{selectedReport.company_view || selectedReport.raw_summary || 'No summary available.'}</p>
              {selectedReport.risk_summary ? <p className="muted">{selectedReport.risk_summary}</p> : null}
              <div className="button-row">
                {selectedReport.source_url ? <a href={selectedReport.source_url} target="_blank" rel="noreferrer">Open Source</a> : null}
                <a href={`#stock-${selectedReport.ts_code}`}>Open Stock Workspace</a>
              </div>
              {selectedReport.copyright_note ? <p className="muted">{selectedReport.copyright_note}</p> : null}
            </>
          ) : (
            <p className="muted">Select a report to inspect metadata.</p>
          )}
        </aside>
      </section>
    </section>
  );
}
```

- [ ] **Step 4: Add minimal CSS**

Append to `dashboard/src/styles.css`:

```css
.research-report-toolbar {
  align-items: end;
}

.inline-check {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  min-height: 2.4rem;
}

.inline-check input {
  width: auto;
}

.research-report-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(320px, 0.8fr);
  gap: 1rem;
  align-items: start;
}

.research-report-table td:nth-child(2) {
  display: grid;
  gap: 0.1rem;
}

.research-report-table td:nth-child(2) span {
  color: var(--muted-text);
  font-size: 0.78rem;
}

.research-report-detail {
  position: sticky;
  top: 1rem;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  margin: 0;
}

.detail-grid div {
  min-width: 0;
}

.detail-grid dt {
  color: var(--muted-text);
  font-size: 0.75rem;
}

.detail-grid dd {
  margin: 0.15rem 0 0;
  font-weight: 600;
}

.button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

@media (max-width: 980px) {
  .research-report-layout {
    grid-template-columns: 1fr;
  }

  .research-report-detail {
    position: static;
  }
}
```

- [ ] **Step 5: Run workspace tests**

Run:

```bash
cd dashboard && npm test -- --run tests/research-reports-workspace.test.tsx
```

Expected: all tests pass.

- [ ] **Step 6: Commit Research Reports UI**

```bash
git add dashboard/src/components/ResearchReportsWorkspace.tsx dashboard/src/styles.css dashboard/tests/research-reports-workspace.test.tsx
git commit -m "feat: build research reports workspace"
```

## Task 5: Stock Workspace Research Reports Panel

**Files:**
- Modify: `dashboard/src/components/StockWorkspace.tsx`
- Modify: `dashboard/tests/stock-workspace.test.tsx`

- [ ] **Step 1: Extend StockWorkspace mocks and tests**

Modify the mock object in `dashboard/tests/stock-workspace.test.tsx`:

```ts
const apiMocks = vi.hoisted(() => ({
  fetchAssetProfile: vi.fn(),
  fetchAssetResearchReports: vi.fn(),
  fetchPublicNews: vi.fn(),
  searchAssets: vi.fn()
}));
```

Add `fetchAssetResearchReports` to the client mock and default `beforeEach`:

```ts
apiMocks.fetchAssetResearchReports.mockResolvedValue({
  asset_id: '000001.SZ',
  summary: {
    report_count_30d: 2,
    report_count_90d: 4,
    broker_coverage_count_90d: 3,
    latest_report_date: '2026-06-03',
    latest_rating: '买入',
    latest_target_price: 19.5
  },
  items: [
    {
      report_id: 'r1',
      asset_id: '000001.SZ',
      ts_code: '000001.SZ',
      stock_name: '平安银行',
      industry_name: '银行',
      report_title: '平安银行深度报告',
      publish_date: '2026-06-03',
      report_date: '2026-06-03',
      broker: '华泰证券',
      analyst: '',
      rating: '买入',
      rating_change: '',
      target_price: 19.5,
      target_upside: null,
      source_type: 'public_web_search_result',
      source_name: 'cfi_ybyl',
      source_confidence: 0.8,
      public_access: true,
      copyright_note: 'metadata only',
      source_url: 'https://example.com/r1',
      raw_summary: '',
      company_view: '',
      industry_view: '',
      risk_summary: '',
      metadata: {}
    }
  ],
  warnings: []
});
```

Add tests:

```tsx
it('loads research reports for the selected stock', async () => {
  render(<StockWorkspace initialAssetId="000001.SZ" />);

  expect(await screen.findByText('平安银行深度报告')).toBeInTheDocument();
  expect(screen.getByText('90d reports 4')).toBeInTheDocument();
  expect(apiMocks.fetchAssetResearchReports).toHaveBeenCalledWith('000001.SZ', { limit: 5, lookbackDays: 90 });
});

it('does not show stale research reports after a later profile load clears the profile', async () => {
  const firstReports = deferred<Awaited<ReturnType<typeof apiMocks.fetchAssetResearchReports>>>();
  apiMocks.fetchAssetResearchReports.mockReturnValueOnce(firstReports.promise);
  apiMocks.fetchAssetProfile.mockResolvedValueOnce(makeProfile()).mockRejectedValueOnce(new Error('not found'));

  render(<StockWorkspace initialAssetId="000001.SZ" />);
  await screen.findByRole('heading', { name: /平安银行/ });

  fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
  fireEvent.click(screen.getByRole('button', { name: 'Load Stock' }));

  await screen.findByText('not found');

  await act(async () => {
    firstReports.resolve({
      asset_id: '000001.SZ',
      summary: {
        report_count_30d: 2,
        report_count_90d: 4,
        broker_coverage_count_90d: 3,
        latest_report_date: '2026-06-03',
        latest_rating: '买入',
        latest_target_price: 19.5
      },
      items: [],
      warnings: []
    });
  });

  expect(screen.queryByText('90d reports 4')).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run StockWorkspace tests to verify they fail**

Run:

```bash
cd dashboard && npm test -- --run tests/stock-workspace.test.tsx
```

Expected: fail because the component does not call `fetchAssetResearchReports`.

- [ ] **Step 3: Implement StockWorkspace report loading**

Modify imports in `dashboard/src/components/StockWorkspace.tsx`:

```ts
import { fetchAssetProfile, fetchAssetResearchReports, fetchPublicNews, searchAssets } from '../api/client';
import type { AssetProfile, AssetResearchReportResponse, AssetSummary, PublicNewsItem } from '../api/types';
```

Add state and request ref near news state:

```ts
  const [researchReports, setResearchReports] = useState<AssetResearchReportResponse | null>(null);
  const [isResearchReportsLoading, setIsResearchReportsLoading] = useState(false);
  const [researchReportsError, setResearchReportsError] = useState<string | null>(null);
  const researchReportsRequestIdRef = useRef(0);
```

Increment the ref in cleanup:

```ts
      researchReportsRequestIdRef.current += 1;
```

Add a `useEffect` after the news effect:

```tsx
  useEffect(() => {
    if (!profile) {
      researchReportsRequestIdRef.current += 1;
      setResearchReports(null);
      setIsResearchReportsLoading(false);
      setResearchReportsError(null);
      return;
    }

    const requestId = researchReportsRequestIdRef.current + 1;
    researchReportsRequestIdRef.current = requestId;

    setIsResearchReportsLoading(true);
    setResearchReportsError(null);

    fetchAssetResearchReports(profile.canonical_asset_id, { limit: 5, lookbackDays: 90 })
      .then((payload) => {
        if (mountedRef.current && requestId === researchReportsRequestIdRef.current) {
          setResearchReports(payload);
        }
      })
      .catch((err: unknown) => {
        if (mountedRef.current && requestId === researchReportsRequestIdRef.current) {
          setResearchReportsError(err instanceof Error ? err.message : String(err));
          setResearchReports(null);
        }
      })
      .finally(() => {
        if (mountedRef.current && requestId === researchReportsRequestIdRef.current) {
          setIsResearchReportsLoading(false);
        }
      });
  }, [profile]);
```

Replace the `Research Reports Phase 3` placeholder article with:

```tsx
            <article className="workspace-band">
              <div className="section-heading">
                <h2>Research Reports</h2>
                {isResearchReportsLoading ? <span className="muted">Loading...</span> : null}
              </div>
              {researchReportsError ? <p className="error-text">{researchReportsError}</p> : null}
              {researchReports ? (
                <section className="stock-summary-strip compact" aria-label="Stock research report summary">
                  <div><span>90d reports</span><strong>90d reports {researchReports.summary.report_count_90d}</strong></div>
                  <div><span>Brokers</span><strong>{researchReports.summary.broker_coverage_count_90d}</strong></div>
                  <div><span>Latest Rating</span><strong>{researchReports.summary.latest_rating || '-'}</strong></div>
                  <div><span>Target</span><strong>{formatValue(researchReports.summary.latest_target_price)}</strong></div>
                </section>
              ) : null}
              <div className="compact-news-list">
                {(researchReports?.items ?? []).map((item) => (
                  <a key={item.report_id} className="evidence-link-row" href={item.source_url || `#${item.report_id}`} target="_blank" rel="noreferrer">
                    <strong>{item.report_title}</strong>
                    <span>{item.publish_date ?? item.report_date ?? '-'}</span>
                  </a>
                ))}
              </div>
              {!isResearchReportsLoading && (researchReports?.items.length ?? 0) === 0 ? (
                <p className="muted">No research reports found.</p>
              ) : null}
            </article>
```

- [ ] **Step 4: Run StockWorkspace tests**

Run:

```bash
cd dashboard && npm test -- --run tests/stock-workspace.test.tsx
```

Expected: all tests pass.

- [ ] **Step 5: Commit Stock Workspace integration**

```bash
git add dashboard/src/components/StockWorkspace.tsx dashboard/tests/stock-workspace.test.tsx
git commit -m "feat: connect stock workspace research reports"
```

## Task 6: Full Verification and Smoke Updates

**Files:**
- Modify: `dashboard/tests/app-smoke.spec.ts` if `/api/research-reports` requests need mocks.
- Modify: `dashboard/tests/app-shell.test.tsx` only if AppShell tests mock API imports and fail after new client functions.

- [ ] **Step 1: Run focused backend tests**

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_research_reports.py tests/test_dashboard_app.py -v
```

Expected: pass.

- [ ] **Step 2: Run focused frontend tests**

```bash
cd dashboard && npm test -- --run tests/client.test.ts tests/research-reports-workspace.test.tsx tests/stock-workspace.test.tsx
```

Expected: pass.

- [ ] **Step 3: Run broader dashboard tests likely affected by API mocks**

```bash
cd dashboard && npm test -- --run tests/app-shell.test.tsx tests/app-smoke.spec.ts
```

Expected: pass. If mocks fail because `fetchResearchReportSummary`, `fetchResearchReports`, or `fetchAssetResearchReports` are missing, add those functions to the relevant hoisted mock objects with resolved empty payloads:

```ts
fetchResearchReportSummary: vi.fn().mockResolvedValue({
  total_reports: 0,
  covered_stocks: 0,
  latest_publish_date: null,
  latest_feature_date: null,
  source_count: 0,
  source_counts: [],
  rating_counts: [],
  broker_counts: []
}),
fetchResearchReports: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0, warnings: [] }),
fetchAssetResearchReports: vi.fn().mockResolvedValue({
  asset_id: '000001.SZ',
  summary: {
    report_count_30d: 0,
    report_count_90d: 0,
    broker_coverage_count_90d: 0,
    latest_report_date: null,
    latest_rating: '',
    latest_target_price: null
  },
  items: [],
  warnings: []
})
```

- [ ] **Step 4: Run typecheck/build**

```bash
cd dashboard && npm run build
```

Expected: build succeeds.

- [ ] **Step 5: Run a live API smoke query against local database**

Run the FastAPI app in one terminal if it is not already running:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/uvicorn stock_research.dashboard.app:create_app --factory --host 127.0.0.1 --port 8000
```

Then run:

```bash
curl -s 'http://127.0.0.1:8000/api/research-reports?ts_code=600519.SH&limit=2' | /Users/xiwei/stock_research/.venv/bin/python -m json.tool
```

Expected: JSON response with `items`, `total`, `limit`, `offset`, and `warnings`. If the local DB has no `600519.SH` reports in the current worktree environment, retry with:

```bash
curl -s 'http://127.0.0.1:8000/api/research-reports?limit=2' | /Users/xiwei/stock_research/.venv/bin/python -m json.tool
```

- [ ] **Step 6: Commit verification fixes**

Only commit if Step 3 required mock updates or smoke-test changes:

```bash
git add dashboard/tests/app-shell.test.tsx dashboard/tests/app-smoke.spec.ts
git commit -m "test: update research report dashboard mocks"
```

If no files changed, skip this commit.

## Final Acceptance Criteria

- `Research Reports` page no longer shows a placeholder.
- Page loads summary and report rows from read-only backend APIs.
- Filters support stock/title/broker query, broker, rating, source, date range, and target-price availability.
- Selecting a row shows report metadata details and source attribution.
- Stock Workspace shows latest research reports for the selected stock and guards stale responses.
- Backend and frontend focused tests pass.
- Dashboard build passes.
- No adapter or scraping execution is added to the dashboard.
