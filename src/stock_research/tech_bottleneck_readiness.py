from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd


READINESS_FLAGS = [
    "has_industry_context",
    "has_product_revenue_exposure",
    "has_research_report",
    "has_bottleneck_keywords",
    "has_capacity_evidence",
    "has_customer_certification_evidence",
    "has_patent_or_technical_barrier",
    "has_news_or_announcement_catalyst",
    "has_invalidation_evidence",
]

FOUNDATION_FLAGS = [
    "has_industry_context",
    "has_product_revenue_exposure",
    "has_research_report",
]

READINESS_COLUMNS = [
    "run_id",
    "asset_id",
    "stock_name",
    "trade_date",
    "candidate_source",
    "rank",
    "as_of_date",
    "lookback_days",
    *READINESS_FLAGS,
    "coverage_score",
    "coverage_status",
    "missing_flags",
    "proxy_flags",
    "source_gap_flags",
]

BOTTLENECK_KEYWORDS = [
    "卡脖子",
    "瓶颈",
    "稀缺",
    "国产替代",
    "自主可控",
    "关键材料",
    "关键设备",
    "核心零部件",
    "供应链安全",
    "受限",
    "进口替代",
    "bottleneck",
    "chokepoint",
    "scarce",
    "shortage",
    "localization",
    "substitution",
    "critical material",
    "critical equipment",
]

CAPACITY_KEYWORDS = [
    "产能",
    "扩产",
    "爬坡",
    "良率",
    "交付周期",
    "供给受限",
    "供需缺口",
    "满产",
    "达产",
    "建设周期",
    "瓶颈产线",
    "capacity",
    "ramp",
    "yield",
    "lead time",
    "supply constraint",
    "utilization",
]

CUSTOMER_CERTIFICATION_KEYWORDS = [
    "客户认证",
    "客户验证",
    "导入",
    "定点",
    "合格供应商",
    "供应商认证",
    "批量供货",
    "订单",
    "在手订单",
    "客户突破",
    "qualification",
    "qualified supplier",
    "design win",
    "certification",
    "customer validation",
    "order backlog",
]

TECHNICAL_BARRIER_KEYWORDS = [
    "专利",
    "技术壁垒",
    "工艺壁垒",
    "配方",
    "know-how",
    "核心技术",
    "自研",
    "高精度",
    "高可靠",
    "高纯",
    "先进制程",
    "patent",
    "process know-how",
    "technical barrier",
    "proprietary",
    "high purity",
    "advanced process",
]

INVALIDATION_KEYWORDS = [
    "降价",
    "需求不及预期",
    "产能过剩",
    "客户流失",
    "毛利下滑",
    "延期",
    "减值",
    "竞争加剧",
    "路线变化",
    "技术替代",
    "price cut",
    "substitution",
    "demand miss",
    "oversupply",
    "customer loss",
    "margin pressure",
    "delay",
    "impairment",
    "route change",
]


def normalize_readiness_candidates(
    candidates: pd.DataFrame,
    *,
    run_date: str,
    as_of_date: str | None,
    lookback_days: int,
) -> pd.DataFrame:
    if "asset_id" not in candidates.columns:
        raise ValueError("readiness candidates must include asset_id")

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

    explicit_as_of_date = _date_text(as_of_date)
    fallback_run_date = _date_text(run_date)
    normalized["as_of_date"] = normalized["trade_date"].map(
        lambda trade_date: explicit_as_of_date or trade_date or fallback_run_date
    )
    normalized["lookback_days"] = int(lookback_days)

    return normalized[
        ["asset_id", "stock_name", "trade_date", "candidate_source", "rank", "as_of_date", "lookback_days"]
    ]


class ReadinessAuditResult:
    def __init__(self, *, summary: pd.DataFrame, details: list[dict[str, Any]]) -> None:
        self.summary = summary
        self.details = details


def build_readiness_audit(
    *,
    candidates: pd.DataFrame,
    run_id: str,
    run_date: str,
    as_of_date: str | None,
    lookback_days: int,
    industry: pd.DataFrame,
    main_business: pd.DataFrame,
    reports: pd.DataFrame,
    report_features: pd.DataFrame,
    events: pd.DataFrame,
    news: pd.DataFrame,
    source_tables_empty: dict[str, bool] | None = None,
) -> ReadinessAuditResult:
    """Build readiness flags from evidence frames pre-filtered to each candidate's as-of/lookback window.

    The caller or DB loader is responsible for point-in-time and lookback filtering before invoking this pure function.
    """
    normalized = normalize_readiness_candidates(
        candidates,
        run_date=run_date,
        as_of_date=as_of_date,
        lookback_days=lookback_days,
    )
    empty_sources = source_tables_empty or {}
    lookups = {
        "industry": _rows_by_asset(industry),
        "main_business": _rows_by_asset(main_business),
        "reports": _rows_by_asset(reports),
        "report_features": _rows_by_asset(report_features),
        "events": _rows_by_asset(events),
        "news": _rows_by_asset(news),
    }

    summary_rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    for candidate in normalized.to_dict("records"):
        asset_id = candidate["asset_id"]
        industry_rows = lookups["industry"].get(asset_id, [])
        main_business_rows = [
            row
            for row in lookups["main_business"].get(asset_id, [])
            if _safe_text(row.get("classify_type")) == "按产品分类" and _safe_text(row.get("item_name"))
        ]
        report_rows = lookups["reports"].get(asset_id, [])
        report_feature_rows = [
            row
            for row in lookups["report_features"].get(asset_id, [])
            if _safe_number(row.get("report_count_90d")) > 0 or _safe_number(row.get("source_count")) > 0
        ]
        event_rows = lookups["events"].get(asset_id, [])
        news_rows = lookups["news"].get(asset_id, [])
        corpus = _build_text_corpus(
            asset_id=asset_id,
            reports=report_rows,
            events=event_rows,
            news=news_rows,
            main_business=main_business_rows,
        )

        flag_details: dict[str, list[dict[str, Any]]] = {flag: [] for flag in READINESS_FLAGS}
        flags = {
            "has_industry_context": bool(industry_rows),
            "has_product_revenue_exposure": bool(main_business_rows),
            "has_research_report": bool(report_rows or report_feature_rows),
            "has_bottleneck_keywords": False,
            "has_capacity_evidence": False,
            "has_customer_certification_evidence": False,
            "has_patent_or_technical_barrier": False,
            "has_news_or_announcement_catalyst": bool(news_rows or event_rows),
            "has_invalidation_evidence": False,
        }

        flag_details["has_industry_context"] = _sample_rows(industry_rows, "industry")
        flag_details["has_product_revenue_exposure"] = _sample_rows(main_business_rows, "main_business")
        flag_details["has_research_report"] = _sample_rows(report_rows or report_feature_rows, "reports")
        flag_details["has_news_or_announcement_catalyst"] = _sample_rows(
            news_rows or event_rows,
            "news" if news_rows else "events",
        )

        for flag, keywords in [
            ("has_bottleneck_keywords", BOTTLENECK_KEYWORDS),
            ("has_capacity_evidence", CAPACITY_KEYWORDS),
            ("has_customer_certification_evidence", CUSTOMER_CERTIFICATION_KEYWORDS),
            ("has_patent_or_technical_barrier", TECHNICAL_BARRIER_KEYWORDS),
            ("has_invalidation_evidence", INVALIDATION_KEYWORDS),
        ]:
            matches = _keyword_matches(corpus, keywords)
            if matches:
                flags[flag] = True
                flag_details[flag] = matches[:3]

        proxy_flags = []
        if flags["has_patent_or_technical_barrier"]:
            proxy_flags.append("has_patent_or_technical_barrier")
        if flags["has_bottleneck_keywords"] and all(
            match.get("proxy_only") for match in flag_details["has_bottleneck_keywords"]
        ):
            proxy_flags.append("has_bottleneck_keywords")

        source_gap_flags = []
        if not flags["has_news_or_announcement_catalyst"] and empty_sources.get("news"):
            source_gap_flags.append("has_news_or_announcement_catalyst")

        missing_flags = [flag for flag in READINESS_FLAGS if not flags[flag]]
        coverage_score = _coverage_score(flags)
        coverage_status = _coverage_status(
            flags=flags,
            coverage_score=coverage_score,
            source_gap_flags=source_gap_flags,
        )
        summary_rows.append(
            {
                "run_id": run_id,
                **candidate,
                **flags,
                "coverage_score": coverage_score,
                "coverage_status": coverage_status,
                "missing_flags": missing_flags,
                "proxy_flags": proxy_flags,
                "source_gap_flags": source_gap_flags,
            }
        )
        details.append(
            {
                "run_id": run_id,
                "asset_id": asset_id,
                "stock_name": candidate.get("stock_name", ""),
                "as_of_date": candidate.get("as_of_date", ""),
                "flags": flags,
                "coverage_score": coverage_score,
                "coverage_status": coverage_status,
                "missing_flags": missing_flags,
                "proxy_flags": proxy_flags,
                "source_gap_flags": source_gap_flags,
                "evidence_counts": {
                    "industry": len(industry_rows),
                    "main_business": len(main_business_rows),
                    "reports": len(report_rows),
                    "report_features": len(report_feature_rows),
                    "events": len(event_rows),
                    "news": len(news_rows),
                },
                "flag_details": flag_details,
            }
        )

    summary = pd.DataFrame(summary_rows, columns=READINESS_COLUMNS)
    for flag in READINESS_FLAGS:
        if flag in summary.columns:
            summary[flag] = summary[flag].astype(object)
    return ReadinessAuditResult(summary=summary, details=details)


def _rows_by_asset(frame: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    if frame.empty or "asset_id" not in frame.columns:
        return {}
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in frame.to_dict("records"):
        asset_id = _safe_text(row.get("asset_id"))
        if asset_id:
            rows[asset_id].append(row)
    return dict(rows)


def _build_text_corpus(
    *,
    asset_id: str,
    reports: list[dict[str, Any]],
    events: list[dict[str, Any]],
    news: list[dict[str, Any]],
    main_business: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    del asset_id
    records: list[dict[str, Any]] = []
    for row in reports:
        for field_name in ["report_title", "raw_summary", "company_view", "industry_view", "risk_summary"]:
            _append_text(records, row, source_table="reports", field_name=field_name, proxy_only=False)
    for row in events:
        _append_text(records, row, source_table="events", field_name="summary", proxy_only=False)
    for row in news:
        for field_name in ["title", "content"]:
            _append_text(records, row, source_table="news", field_name=field_name, proxy_only=False)
    for row in main_business:
        _append_text(records, row, source_table="main_business", field_name="item_name", proxy_only=True)
    return records


def _append_text(
    records: list[dict[str, Any]],
    row: dict[str, Any],
    *,
    source_table: str,
    field_name: str,
    proxy_only: bool,
) -> None:
    text = _safe_text(row.get(field_name))
    if not text:
        return
    records.append(
        {
            "source_table": source_table,
            "source_id": _safe_text(
                row.get("report_id")
                or row.get("event_id")
                or row.get("news_id")
                or row.get("source_event_id")
            ),
            "source_date": _date_text(
                row.get("report_date")
                or row.get("event_date")
                or row.get("published_at")
                or row.get("report_period")
            ),
            "field_name": field_name,
            "text": text,
            "proxy_only": proxy_only,
        }
    )


def _keyword_matches(corpus: list[dict[str, Any]], keywords: list[str]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for record in corpus:
        text = _safe_text(record.get("text"))
        lowered = text.lower()
        for keyword in keywords:
            if keyword.lower() in lowered:
                matches.append(
                    {
                        "source_table": record.get("source_table", ""),
                        "source_id": record.get("source_id", ""),
                        "source_date": record.get("source_date", ""),
                        "field_name": record.get("field_name", ""),
                        "keyword": keyword,
                        "snippet": _snippet(text, keyword),
                        "proxy_only": bool(record.get("proxy_only")),
                    }
                )
                break
    return matches


def _coverage_score(flags: dict[str, bool]) -> int:
    return (2 * sum(int(flags[flag]) for flag in FOUNDATION_FLAGS)) + sum(
        int(flags[flag]) for flag in READINESS_FLAGS if flag not in FOUNDATION_FLAGS
    )


def _coverage_status(
    *,
    flags: dict[str, bool],
    coverage_score: int,
    source_gap_flags: list[str],
) -> str:
    if not flags["has_industry_context"] or not flags["has_product_revenue_exposure"]:
        return "data_blocked"
    if (
        flags["has_research_report"]
        and flags["has_bottleneck_keywords"]
        and coverage_score >= 7
    ):
        return "ready_for_scoring"
    if source_gap_flags:
        return "source_gap"
    return "needs_evidence_backfill"


def _sample_rows(rows: list[dict[str, Any]], source_table: str) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for row in rows[:3]:
        samples.append(
            {
                "source_table": source_table,
                "source_date": _date_text(
                    row.get("report_date")
                    or row.get("trade_date")
                    or row.get("event_date")
                    or row.get("published_at")
                    or row.get("report_period")
                ),
                "summary": _safe_text(
                    row.get("industry_name")
                    or row.get("item_name")
                    or row.get("report_title")
                    or row.get("title")
                    or row.get("summary")
                ),
            }
        )
    return samples


def _snippet(text: str, keyword: str) -> str:
    index = text.lower().find(keyword.lower())
    if index < 0:
        return text[:120]
    start = max(0, index - 40)
    end = min(len(text), index + len(keyword) + 40)
    return text[start:end]


def _safe_number(value: Any) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


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
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")
