from __future__ import annotations

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
    "替代",
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


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
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
