from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


MAX_LIMIT = 200
DEFAULT_LIMIT = 50
RESEARCH_REPORT_ALLOWED_PDF_ROOTS = (
    Path("/Users/xiwei/stock_research/data/manual"),
    Path("/Users/xiwei/stock_research/reports"),
    Path(getattr(SETTINGS, "output_root", "/Users/xiwei/stock_research/outputs")),
)


def load_research_report_summary(service: str = SETTINGS.research_service) -> dict[str, Any]:
    with connect(service) as conn:
        summary_rows = fetch_all(
            conn,
            """
            SELECT
                COUNT(DISTINCT s.report_id) AS total_reports,
                COUNT(DISTINCT e.ts_code) AS covered_stocks,
                MAX(s.publish_date) AS latest_publish_date,
                (SELECT MAX(trade_date) FROM research.stock_report_feature_daily) AS latest_feature_date,
                COUNT(DISTINCT s.source_name) AS source_count,
                COUNT(DISTINCT s.report_id) FILTER (
                    WHERE s.source_url LIKE 'file://%%'
                       OR s.metadata ? 'local_pdf_path'
                       OR s.metadata ? 'pdf_path'
                       OR s.metadata ? 'yanbaoke'
                ) AS readable_report_count,
                COUNT(DISTINCT s.report_id) FILTER (
                    WHERE NOT (
                        s.source_url LIKE 'file://%%'
                        OR s.metadata ? 'local_pdf_path'
                        OR s.metadata ? 'pdf_path'
                        OR s.metadata ? 'yanbaoke'
                    )
                ) AS web_index_report_count
            FROM research.stock_report_source s
            JOIN research.stock_report_event e USING (report_id)
            """,
        )
        source_counts = fetch_all(
            conn,
            """
            SELECT s.source_name, COUNT(DISTINCT s.report_id) AS rows
            FROM research.stock_report_source s
            JOIN research.stock_report_event e USING (report_id)
            GROUP BY s.source_name
            ORDER BY rows DESC, source_name
            LIMIT 20
            """,
        )
        rating_counts = fetch_all(
            conn,
            """
            SELECT NULLIF(TRIM(e.rating), '') AS rating, COUNT(*) AS rows
            FROM research.stock_report_source s
            JOIN research.stock_report_event e USING (report_id)
            GROUP BY rating
            ORDER BY rows DESC NULLS LAST
            LIMIT 20
            """,
        )
        broker_counts = fetch_all(
            conn,
            """
            SELECT NULLIF(TRIM(s.broker), '') AS broker, COUNT(DISTINCT s.report_id) AS rows
            FROM research.stock_report_source s
            JOIN research.stock_report_event e USING (report_id)
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
        "readable_report_count": int(summary.get("readable_report_count") or 0),
        "pdf_report_count": int(summary.get("readable_report_count") or 0),
        "web_index_report_count": int(summary.get("web_index_report_count") or 0),
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
            ORDER BY s.publish_date DESC NULLS LAST, s.updated_at DESC, s.report_id, e.ts_code
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
            ORDER BY s.publish_date DESC NULLS LAST, s.updated_at DESC, s.report_id, e.ts_code
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


def load_research_report_document(
    report_id: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    clean_report_id = _clean(report_id)
    if not clean_report_id:
        return _empty_report_document("", warnings=["missing report id"])

    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT
                report_id, report_title, source_url, public_access, copyright_note,
                COALESCE(metadata, '{}'::jsonb) AS metadata
            FROM research.stock_report_source
            WHERE report_id = %s
            LIMIT 1
            """,
            [clean_report_id],
        )
    if not rows:
        return _empty_report_document(clean_report_id, warnings=["research report not found"])

    row = rows[0]
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    local_pdf_path = _resolve_report_pdf_path(row)
    source_url = _display_source_url(row, metadata)
    warnings = [] if local_pdf_path else ["local pdf is unavailable or outside allowed report directories"]
    return {
        "report_id": clean_report_id,
        "report_title": str(row.get("report_title") or ""),
        "has_pdf": local_pdf_path is not None,
        "pdf_url": f"/api/research-reports/{clean_report_id}/pdf" if local_pdf_path else "",
        "source_url": source_url,
        "file_name": local_pdf_path.name if local_pdf_path else "",
        "public_access": bool(row.get("public_access")),
        "copyright_note": str(row.get("copyright_note") or ""),
        "warnings": warnings,
    }


def load_research_report_pdf_path(
    report_id: str,
    *,
    service: str = SETTINGS.research_service,
) -> Path | None:
    clean_report_id = _clean(report_id)
    if not clean_report_id:
        return None
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT source_url, COALESCE(metadata, '{}'::jsonb) AS metadata
            FROM research.stock_report_source
            WHERE report_id = %s
            LIMIT 1
            """,
            [clean_report_id],
        )
    if not rows:
        return None
    return _resolve_report_pdf_path(rows[0])


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
    metadata = row.get("metadata")
    report_id = str(row.get("report_id") or "")
    ts_code = str(row.get("ts_code") or "")
    return {
        "event_key": f"{report_id}:{ts_code}",
        "report_id": report_id,
        "asset_id": str(row.get("asset_id") or ""),
        "ts_code": ts_code,
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
        "metadata": metadata if isinstance(metadata, dict) else {},
    }


def _count_row(row: dict[str, Any], key: str) -> dict[str, Any]:
    return {key: str(row.get(key) or ""), "rows": int(row.get("rows") or 0)}


def _bounded_limit(limit: int) -> int:
    requested_limit = DEFAULT_LIMIT if limit is None else int(limit)
    return max(1, min(MAX_LIMIT, requested_limit))


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


def _empty_report_document(report_id: str, *, warnings: list[str]) -> dict[str, Any]:
    return {
        "report_id": report_id,
        "report_title": "",
        "has_pdf": False,
        "pdf_url": "",
        "source_url": "",
        "file_name": "",
        "public_access": False,
        "copyright_note": "",
        "warnings": warnings,
    }


def _resolve_report_pdf_path(row: dict[str, Any]) -> Path | None:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    candidates = _pdf_path_candidates(row, metadata)
    for candidate in candidates:
        resolved = _safe_existing_pdf_path(candidate)
        if resolved:
            return resolved
    return None


def _pdf_path_candidates(row: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    yanbaoke = metadata.get("yanbaoke") if isinstance(metadata.get("yanbaoke"), dict) else {}
    for value in (
        yanbaoke.get("local_pdf_path"),
        metadata.get("local_pdf_path"),
        metadata.get("pdf_path"),
        row.get("source_url"),
    ):
        text = _clean(value)
        if text:
            candidates.append(text)
    return candidates


def _display_source_url(row: dict[str, Any], metadata: dict[str, Any]) -> str:
    yanbaoke = metadata.get("yanbaoke") if isinstance(metadata.get("yanbaoke"), dict) else {}
    detail_url = _clean(yanbaoke.get("detail_url"))
    if detail_url:
        return detail_url
    source_url = _clean(row.get("source_url"))
    if source_url.startswith("file://"):
        return ""
    return source_url


def _safe_existing_pdf_path(value: str) -> Path | None:
    path_text = value
    parsed = urlparse(value)
    if parsed.scheme == "file":
        path_text = unquote(parsed.path)
    elif parsed.scheme:
        return None
    candidate = Path(path_text).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if resolved.suffix.lower() != ".pdf":
        return None
    if not resolved.is_file():
        return None
    allowed_roots = []
    for root in RESEARCH_REPORT_ALLOWED_PDF_ROOTS:
        try:
            allowed_roots.append(Path(root).expanduser().resolve(strict=False))
        except (OSError, RuntimeError):
            continue
    if not any(_is_relative_to(resolved, root) for root in allowed_roots):
        return None
    return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
