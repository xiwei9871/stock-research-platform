from __future__ import annotations

from collections import defaultdict
import datetime as dt
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.db import connect, fetch_all
from stock_research.tech_bottleneck_readiness import (
    BOTTLENECK_KEYWORDS,
    CAPACITY_KEYWORDS,
    CUSTOMER_CERTIFICATION_KEYWORDS,
    INVALIDATION_KEYWORDS,
    TECHNICAL_BARRIER_KEYWORDS,
)


EVIDENCE_COLUMNS = [
    "run_id",
    "asset_id",
    "stock_name",
    "candidate_trade_date",
    "as_of_date",
    "evidence_date",
    "source_type",
    "source_id",
    "source_title",
    "source_url",
    "evidence_type",
    "matched_keyword",
    "evidence_snippet",
    "source_confidence",
    "is_proxy",
    "as_of_safe",
    "metadata_json",
]

SOURCE_GAP_COLUMNS = [
    "asset_id",
    "stock_name",
    "candidate_trade_date",
    "as_of_date",
    "lookback_days",
    "safe_evidence_count",
    "missing_evidence_types",
]

TEXT_EVIDENCE_GROUPS = {
    "bottleneck_keyword": BOTTLENECK_KEYWORDS,
    "capacity": CAPACITY_KEYWORDS,
    "customer_certification": CUSTOMER_CERTIFICATION_KEYWORDS,
    "technical_barrier": TECHNICAL_BARRIER_KEYWORDS,
    "invalidation": INVALIDATION_KEYWORDS,
}

REQUIRED_EVIDENCE_TYPES = ["product_revenue_exposure", *TEXT_EVIDENCE_GROUPS.keys()]

EVIDENCE_SORT_COLUMNS = [
    "candidate_trade_date",
    "asset_id",
    "evidence_date",
    "evidence_type",
    "source_type",
    "source_id",
    "matched_keyword",
    "evidence_snippet",
]


class EvidenceBackfillResult:
    def __init__(self, *, candidates: pd.DataFrame, evidence: pd.DataFrame, source_gap_report: pd.DataFrame) -> None:
        self.candidates = candidates
        self.evidence = evidence
        self.source_gap_report = source_gap_report


def normalize_evidence_candidates(
    candidates: pd.DataFrame,
    *,
    run_date: str,
    start_date: str | None,
    end_date: str | None,
    lookback_days: int,
) -> pd.DataFrame:
    if "asset_id" not in candidates.columns:
        raise ValueError("evidence candidates must include asset_id")

    normalized = candidates.copy()
    for column in ["stock_name", "trade_date", "candidate_source", "rank"]:
        if column not in normalized.columns:
            normalized[column] = ""

    normalized["asset_id"] = normalized["asset_id"].map(_safe_text)
    normalized = normalized[normalized["asset_id"] != ""].copy()
    normalized["stock_name"] = normalized["stock_name"].map(_safe_text)
    normalized["trade_date"] = normalized["trade_date"].map(_date_text)
    normalized["candidate_source"] = normalized["candidate_source"].map(_safe_text)
    normalized["rank"] = normalized["rank"].map(_safe_text)

    fallback_run_date = _date_text(run_date)
    normalized["as_of_date"] = normalized["trade_date"].map(lambda trade_date: trade_date or fallback_run_date)
    normalized["lookback_days"] = int(lookback_days)

    start_timestamp = _date_timestamp(start_date)
    end_timestamp = _date_timestamp(end_date)
    as_of_timestamps = normalized["as_of_date"].map(_date_timestamp)
    if start_timestamp is not None:
        normalized = normalized[as_of_timestamps.notna() & (as_of_timestamps >= start_timestamp)].copy()
        as_of_timestamps = normalized["as_of_date"].map(_date_timestamp)
    if end_timestamp is not None:
        normalized = normalized[as_of_timestamps.notna() & (as_of_timestamps <= end_timestamp)].copy()

    return normalized[
        ["asset_id", "stock_name", "trade_date", "candidate_source", "rank", "as_of_date", "lookback_days"]
    ]


def normalize_evidence_rows(rows: pd.DataFrame) -> pd.DataFrame:
    normalized = rows.copy()
    for column in EVIDENCE_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = False if column in {"is_proxy", "as_of_safe"} else ""

    text_columns = [
        "run_id",
        "asset_id",
        "stock_name",
        "candidate_trade_date",
        "as_of_date",
        "evidence_date",
        "source_type",
        "source_id",
        "source_title",
        "source_url",
        "evidence_type",
        "matched_keyword",
        "evidence_snippet",
        "source_confidence",
    ]
    for column in text_columns:
        if column in {"candidate_trade_date", "as_of_date", "evidence_date"}:
            normalized[column] = normalized[column].map(_date_text)
        else:
            normalized[column] = normalized[column].map(_safe_text)

    normalized["metadata_json"] = normalized["metadata_json"].map(_metadata_json)
    normalized["is_proxy"] = normalized["is_proxy"].map(_bool_value).astype(object)
    normalized["as_of_safe"] = normalized["as_of_safe"].map(_bool_value).astype(object)

    return normalized[EVIDENCE_COLUMNS]


def build_evidence_backfill(
    *,
    candidates: pd.DataFrame,
    run_id: str,
    run_date: str,
    start_date: str | None,
    end_date: str | None,
    lookback_days: int,
    main_business: pd.DataFrame,
    reports: pd.DataFrame,
    events: pd.DataFrame,
    news: pd.DataFrame,
) -> EvidenceBackfillResult:
    normalized_candidates = normalize_evidence_candidates(
        candidates,
        run_date=run_date,
        start_date=start_date,
        end_date=end_date,
        lookback_days=lookback_days,
    )
    business_by_asset = _rows_by_asset(main_business)
    reports_by_asset = _rows_by_asset(reports)
    events_by_asset = _rows_by_asset(events)
    news_by_asset = _rows_by_asset(news)

    rows: list[dict[str, Any]] = []
    for candidate in normalized_candidates.to_dict("records"):
        asset_id = _safe_text(candidate.get("asset_id"))
        for row in business_by_asset.get(asset_id, []):
            if not _is_product_business_row(row):
                continue
            rows.append(_product_evidence_row(candidate, row, run_id=run_id))
        for record in _text_records(
            reports=reports_by_asset.get(asset_id, []),
            events=events_by_asset.get(asset_id, []),
            news=news_by_asset.get(asset_id, []),
        ):
            for match in classify_text_evidence(
                text=_safe_text(record.get("text")),
                source_type=_safe_text(record.get("source_type")),
                source_id=_safe_text(record.get("source_id")),
                source_title=_safe_text(record.get("source_title")),
                source_date=_safe_text(record.get("source_date")),
            ):
                row = {
                    **match,
                    "run_id": run_id,
                    "asset_id": asset_id,
                    "stock_name": _safe_text(candidate.get("stock_name")),
                    "candidate_trade_date": _date_text(candidate.get("trade_date")),
                    "as_of_date": _date_text(candidate.get("as_of_date")),
                    "metadata_json": {
                        **_metadata_dict(match.get("metadata_json")),
                        "field_name": _safe_text(record.get("field_name")),
                    },
                }
                row["as_of_safe"] = _is_as_of_safe(
                    evidence_date=row.get("evidence_date"),
                    as_of_date=candidate.get("as_of_date"),
                    lookback_days=candidate.get("lookback_days") or lookback_days,
                )
                rows.append(row)

    evidence = _sort_evidence_rows(normalize_evidence_rows(pd.DataFrame(rows)))
    source_gap_report = _build_source_gap_report(normalized_candidates, evidence)
    return EvidenceBackfillResult(
        candidates=normalized_candidates,
        evidence=evidence,
        source_gap_report=source_gap_report,
    )


def write_evidence_artifacts(*, result: EvidenceBackfillResult, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "evidence.csv"
    json_path = output_dir / "evidence.json"
    summary_path = output_dir / "coverage_summary.md"
    source_gap_path = output_dir / "source_gap_report.csv"

    result.evidence.to_csv(csv_path, index=False)
    _write_json(json_path, _group_evidence_by_candidate(result.evidence))
    summary_path.write_text(_render_coverage_summary(result), encoding="utf-8")
    result.source_gap_report.to_csv(source_gap_path, index=False)

    return {
        "csv": csv_path,
        "json": json_path,
        "summary": summary_path,
        "source_gap_report": source_gap_path,
    }


def load_evidence_context_from_db(
    candidates: pd.DataFrame,
    *,
    lookback_days: int,
    service: str,
) -> dict[str, pd.DataFrame]:
    asset_ids = sorted(
        {
            _safe_text(value)
            for value in candidates.get("asset_id", pd.Series(dtype=object)).tolist()
            if _safe_text(value)
        }
    )
    if not asset_ids:
        return _empty_evidence_context()

    as_of_dates = pd.to_datetime(candidates.get("as_of_date", pd.Series(dtype=object)), errors="coerce").dropna()
    if as_of_dates.empty:
        return _empty_evidence_context()
    max_as_of = as_of_dates.max().strftime("%Y-%m-%d")
    min_window_start = (as_of_dates.min() - pd.Timedelta(days=int(lookback_days))).strftime("%Y-%m-%d")

    with connect(service) as conn:
        main_business = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT asset_id, report_period, classify_type, item_name, revenue, revenue_ratio, gross_margin
                FROM finance.main_business_composition
                WHERE asset_id = ANY(%s)
                  AND report_period <= %s::date
                ORDER BY asset_id, report_period, classify_type, item_name
                """,
                (asset_ids, max_as_of),
            )
        )
        reports = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT
                    e.asset_id,
                    e.report_id,
                    e.report_date,
                    s.report_title,
                    s.raw_summary,
                    e.company_view,
                    e.industry_view,
                    e.risk_summary,
                    s.source_type,
                    s.broker
                FROM research.stock_report_event e
                LEFT JOIN research.stock_report_source s ON s.report_id = e.report_id
                WHERE e.asset_id = ANY(%s)
                  AND e.report_date BETWEEN %s::date AND %s::date
                ORDER BY e.asset_id, e.report_date, e.report_id
                """,
                (asset_ids, min_window_start, max_as_of),
            )
        )
        events = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT event_id, asset_id, 'institution_survey' AS event_type, survey_date AS event_date, summary
                FROM event.institution_survey
                WHERE asset_id = ANY(%s)
                  AND survey_date BETWEEN %s::date AND %s::date
                UNION ALL
                SELECT event_id, asset_id, 'earnings_forecast' AS event_type, announcement_date AS event_date, summary
                FROM event.earnings_forecast
                WHERE asset_id = ANY(%s)
                  AND announcement_date BETWEEN %s::date AND %s::date
                UNION ALL
                SELECT event_id, asset_id, 'earnings_express' AS event_type, announcement_date AS event_date, '' AS summary
                FROM event.earnings_express
                WHERE asset_id = ANY(%s)
                  AND announcement_date BETWEEN %s::date AND %s::date
                ORDER BY asset_id, event_date, event_type, event_id
                """,
                (
                    asset_ids,
                    min_window_start,
                    max_as_of,
                    asset_ids,
                    min_window_start,
                    max_as_of,
                    asset_ids,
                    min_window_start,
                    max_as_of,
                ),
            )
        )
        news = pd.DataFrame(
            fetch_all(
                conn,
                """
                SELECT
                    m.asset_id,
                    m.source_event_id,
                    s.published_at,
                    s.title,
                    s.content
                FROM research.news_event_mention m
                JOIN research.news_event_source s ON s.source_event_id = m.source_event_id
                WHERE m.asset_id = ANY(%s)
                  AND s.published_at::date BETWEEN %s::date AND %s::date
                ORDER BY m.asset_id, s.published_at, m.source_event_id
                """,
                (asset_ids, min_window_start, max_as_of),
            )
        )

    return {
        "main_business": main_business,
        "reports": reports,
        "events": events,
        "news": news,
    }


def run_evidence_backfill_from_files(
    *,
    candidates_csv: Path,
    output_dir: Path,
    run_id: str,
    run_date: str,
    start_date: str | None,
    end_date: str | None,
    lookback_days: int,
    service: str,
    context_loader: Any | None = None,
) -> dict[str, Path]:
    candidates = pd.read_csv(candidates_csv)
    normalized = normalize_evidence_candidates(
        candidates,
        run_date=run_date,
        start_date=start_date,
        end_date=end_date,
        lookback_days=lookback_days,
    )
    loader = context_loader or load_evidence_context_from_db
    context = loader(normalized, lookback_days=lookback_days, service=service)
    result = build_evidence_backfill(
        candidates=normalized,
        run_id=run_id,
        run_date=run_date,
        start_date=start_date,
        end_date=end_date,
        lookback_days=lookback_days,
        **context,
    )
    return write_evidence_artifacts(result=result, output_dir=output_dir)


def classify_text_evidence(
    *,
    text: str,
    source_type: str,
    source_id: str,
    source_title: str,
    source_date: str,
) -> list[dict[str, Any]]:
    evidence_text = _safe_text(text)
    lowered = evidence_text.lower()
    matches: list[dict[str, Any]] = []

    for evidence_type, keywords in TEXT_EVIDENCE_GROUPS.items():
        for keyword in keywords:
            if keyword.lower() not in lowered:
                continue
            matches.append(
                {
                    "evidence_date": _date_text(source_date),
                    "source_type": _safe_text(source_type),
                    "source_id": _safe_text(source_id),
                    "source_title": _safe_text(source_title),
                    "source_url": "",
                    "evidence_type": evidence_type,
                    "matched_keyword": keyword,
                    "evidence_snippet": _snippet(evidence_text, keyword),
                    "source_confidence": "medium",
                    "is_proxy": evidence_type == "technical_barrier",
                    "as_of_safe": True,
                    "metadata_json": {},
                }
            )
            break

    return matches


def _rows_by_asset(frame: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    if frame.empty or "asset_id" not in frame.columns:
        return {}
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in frame.to_dict("records"):
        asset_id = _safe_text(row.get("asset_id"))
        if asset_id:
            rows[asset_id].append(row)
    return dict(rows)


def _is_product_business_row(row: dict[str, Any]) -> bool:
    return _safe_text(row.get("classify_type")) == "按产品分类" and _safe_text(row.get("item_name")) != ""


def _product_evidence_row(candidate: dict[str, Any], row: dict[str, Any], *, run_id: str) -> dict[str, Any]:
    item_name = _safe_text(row.get("item_name"))
    report_period = _date_text(row.get("report_period"))
    metadata = {
        "classify_type": _safe_text(row.get("classify_type")),
        "item_name": item_name,
        "revenue": row.get("revenue"),
        "revenue_ratio": row.get("revenue_ratio"),
        "gross_margin": row.get("gross_margin"),
    }
    return {
        "run_id": run_id,
        "asset_id": _safe_text(candidate.get("asset_id")),
        "stock_name": _safe_text(candidate.get("stock_name")),
        "candidate_trade_date": _date_text(candidate.get("trade_date")),
        "as_of_date": _date_text(candidate.get("as_of_date")),
        "evidence_date": report_period,
        "source_type": "finance.main_business_composition",
        "source_id": ":".join(
            part
            for part in [
                _safe_text(candidate.get("asset_id")),
                report_period,
                item_name,
            ]
            if part
        ),
        "source_title": "主营构成",
        "source_url": "",
        "evidence_type": "product_revenue_exposure",
        "matched_keyword": "",
        "evidence_snippet": _product_snippet(row),
        "source_confidence": "strong",
        "is_proxy": False,
        "as_of_safe": _is_as_of_safe(
            evidence_date=report_period,
            as_of_date=candidate.get("as_of_date"),
            lookback_days=candidate.get("lookback_days"),
        ),
        "metadata_json": metadata,
    }


def _product_snippet(row: dict[str, Any]) -> str:
    parts = [_safe_text(row.get("item_name"))]
    revenue_ratio = _safe_text(row.get("revenue_ratio"))
    gross_margin = _safe_text(row.get("gross_margin"))
    if revenue_ratio:
        parts.append(f"收入占比{revenue_ratio}%")
    if gross_margin:
        parts.append(f"毛利率{gross_margin}%")
    return "，".join(part for part in parts if part)


def _text_records(
    *,
    reports: list[dict[str, Any]],
    events: list[dict[str, Any]],
    news: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in reports:
        for field_name in ["report_title", "raw_summary", "company_view", "industry_view", "risk_summary"]:
            _append_text_record(
                records,
                row,
                source_type="research.stock_report_event",
                source_id_field="report_id",
                date_field="report_date",
                title_field="report_title",
                field_name=field_name,
            )
    for row in events:
        _append_text_record(
            records,
            row,
            source_type=_event_source_type(row),
            source_id_field="event_id",
            date_field="event_date",
            title_field="event_type",
            field_name="summary",
        )
    for row in news:
        for field_name in ["title", "content"]:
            _append_text_record(
                records,
                row,
                source_type="research.news_event_mention",
                source_id_field="source_event_id",
                date_field="published_at",
                title_field="title",
                field_name=field_name,
            )
    return records


def _sort_evidence_rows(evidence: pd.DataFrame) -> pd.DataFrame:
    if evidence.empty:
        return evidence
    return evidence.sort_values(EVIDENCE_SORT_COLUMNS, kind="mergesort").reset_index(drop=True)


def _append_text_record(
    records: list[dict[str, Any]],
    row: dict[str, Any],
    *,
    source_type: str,
    source_id_field: str,
    date_field: str,
    title_field: str,
    field_name: str,
) -> None:
    text = _safe_text(row.get(field_name))
    if not text:
        return
    records.append(
        {
            "text": text,
            "field_name": field_name,
            "source_type": source_type,
            "source_id": _safe_text(row.get(source_id_field)),
            "source_date": _date_text(row.get(date_field)),
            "source_title": _safe_text(row.get(title_field)),
        }
    )


def _event_source_type(row: dict[str, Any]) -> str:
    event_type = _safe_text(row.get("event_type"))
    if event_type:
        return f"event.{event_type}"
    return "event"


def _is_as_of_safe(*, evidence_date: Any, as_of_date: Any, lookback_days: Any) -> bool:
    evidence_timestamp = _date_timestamp(evidence_date)
    as_of_timestamp = _date_timestamp(as_of_date)
    if evidence_timestamp is None or as_of_timestamp is None:
        return False
    window_start = as_of_timestamp - pd.Timedelta(days=int(lookback_days or 0))
    return bool(window_start <= evidence_timestamp <= as_of_timestamp)


def _build_source_gap_report(candidates: pd.DataFrame, evidence: pd.DataFrame) -> pd.DataFrame:
    safe_evidence = evidence[evidence["as_of_safe"].map(bool)].copy() if not evidence.empty else evidence
    rows: list[dict[str, Any]] = []
    for candidate in candidates.to_dict("records"):
        asset_id = _safe_text(candidate.get("asset_id"))
        trade_date = _date_text(candidate.get("trade_date"))
        if safe_evidence.empty:
            candidate_evidence = safe_evidence
        else:
            candidate_evidence = safe_evidence[
                safe_evidence["asset_id"].eq(asset_id)
                & safe_evidence["candidate_trade_date"].eq(trade_date)
            ]
        present = set(candidate_evidence["evidence_type"].tolist()) if not candidate_evidence.empty else set()
        missing = [evidence_type for evidence_type in REQUIRED_EVIDENCE_TYPES if evidence_type not in present]
        rows.append(
            {
                "asset_id": asset_id,
                "stock_name": _safe_text(candidate.get("stock_name")),
                "candidate_trade_date": trade_date,
                "as_of_date": _date_text(candidate.get("as_of_date")),
                "lookback_days": int(candidate.get("lookback_days") or 0),
                "safe_evidence_count": int(len(candidate_evidence)),
                "missing_evidence_types": ",".join(missing),
            }
        )
    return pd.DataFrame(rows, columns=SOURCE_GAP_COLUMNS)


def _group_evidence_by_candidate(evidence: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in evidence.to_dict("records"):
        key = f"{_safe_text(row.get('asset_id'))}|{_date_text(row.get('candidate_trade_date'))}"
        grouped.setdefault(key, []).append(_json_safe_value(row))
    return dict(sorted(grouped.items()))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(_json_safe_value(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _render_coverage_summary(result: EvidenceBackfillResult) -> str:
    lines = [
        "# tech-bottleneck evidence backfill coverage",
        "",
        f"Candidate count: {len(result.candidates)}",
        f"Evidence row count: {len(result.evidence)}",
        "",
        "## Evidence type counts",
    ]
    lines.extend(_count_lines(result.evidence, "evidence_type"))
    lines.extend(["", "## Source confidence counts"])
    lines.extend(_count_lines(result.evidence, "source_confidence"))
    lines.extend(["", "## As-of safe counts"])
    lines.extend(_count_lines(result.evidence, "as_of_safe"))
    lines.extend(["", "## Source gaps"])
    if result.source_gap_report.empty:
        lines.append("- No candidates.")
    else:
        gap_count = int(
            result.source_gap_report["missing_evidence_types"].map(lambda value: bool(_safe_text(value))).sum()
        )
        lines.append(f"- Candidates with missing safe evidence types: {gap_count}/{len(result.source_gap_report)}")
    return "\n".join(lines) + "\n"


def _count_lines(frame: pd.DataFrame, column: str) -> list[str]:
    if frame.empty or column not in frame.columns:
        return ["- None."]
    counts = frame[column].map(_safe_text).value_counts(dropna=False).sort_index()
    if counts.empty:
        return ["- None."]
    return [f"- {label or '(blank)'}: {int(count)}" for label, count in counts.items()]


def _metadata_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _empty_evidence_context() -> dict[str, pd.DataFrame]:
    return {
        "main_business": pd.DataFrame(),
        "reports": pd.DataFrame(),
        "events": pd.DataFrame(),
        "news": pd.DataFrame(),
    }


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _date_text(value: Any) -> str:
    timestamp = _date_timestamp(value)
    if timestamp is None:
        return ""
    return timestamp.strftime("%Y-%m-%d")


def _date_timestamp(value: Any) -> pd.Timestamp | None:
    text = _safe_text(value)
    if not text:
        return None
    try:
        timestamp = pd.to_datetime(text, errors="coerce")
    except Exception:
        return None
    if pd.isna(timestamp):
        return None
    timestamp = pd.Timestamp(timestamp)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_localize(None)
    return timestamp.normalize()


def _metadata_json(value: Any) -> str:
    if isinstance(value, str):
        text = _safe_text(value)
        if not text:
            return "{}"
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"value": text}
        return json.dumps(_json_safe_value(parsed), ensure_ascii=False, sort_keys=True)
    try:
        if pd.isna(value):
            return "{}"
    except Exception:
        pass
    return json.dumps(_json_safe_value(value), ensure_ascii=False, sort_keys=True)


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {_safe_text(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else str(value)
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return _json_safe_value(value.item())
        except Exception:
            pass
    return value


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _safe_text(value).lower()
    if text in {"", "0", "false", "f", "no", "n", "none", "null", "nan", "na", "n/a", "pd.na"}:
        return False
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    return False


def _snippet(text: str, keyword: str) -> str:
    index = text.lower().find(keyword.lower())
    if index < 0:
        return text[:120]
    start = max(0, index - 40)
    end = min(len(text), index + len(keyword) + 40)
    return text[start:end]
