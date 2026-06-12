from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SECTOR_PRIORITY_PATH = PROJECT_ROOT / "config" / "yanbaoke_sector_priority.csv"

A_TIER_BROKER_KEYWORDS = (
    "中信证券",
    "中金",
    "华泰",
    "国泰君安",
    "国泰海通",
    "招商证券",
    "海通证券",
    "广发证券",
    "中信建投",
    "申万宏源",
    "兴业证券",
    "国信证券",
    "光大证券",
    "东吴证券",
    "高盛",
    "摩根士丹利",
    "摩根大通",
    "花旗",
    "瑞银",
    "汇丰",
)


def load_sector_priority_config(path: str | Path | None = None) -> pd.DataFrame:
    config_path = Path(path) if path is not None else DEFAULT_SECTOR_PRIORITY_PATH
    frame = pd.read_csv(config_path, dtype="string").fillna("")
    required = {"sector_name", "match_keywords", "sector_priority", "sector_quota_bucket", "pilot_quota"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"sector priority config missing columns: {sorted(missing)}")
    frame["pilot_quota"] = pd.to_numeric(frame["pilot_quota"], errors="coerce").fillna(0).astype(int)
    return frame


def build_scored_candidates(
    candidates: pd.DataFrame,
    *,
    existing_coverage: pd.DataFrame | None = None,
    sector_config: pd.DataFrame | None = None,
) -> pd.DataFrame:
    sector_rules = sector_config if sector_config is not None else load_sector_priority_config()
    existing = existing_coverage.copy() if existing_coverage is not None else pd.DataFrame()
    frame = _normalize_candidate_columns(candidates)
    frame["normalized_title"] = frame["title"].map(_normalize_text)
    frame["normalized_broker"] = frame["broker"].map(_normalize_text)
    frame["report_type_bucket"] = frame["title"].map(classify_report_type_bucket)
    if frame.empty:
        frame["theme_bucket"] = pd.Series(dtype="string")
        frame["sector_priority"] = pd.Series(dtype="string")
        frame["sector_quota_bucket"] = pd.Series(dtype="string")
        frame["sector_pilot_quota"] = pd.Series(dtype="int64")
        frame["asset_priority"] = pd.Series(dtype="string")
        frame["coverage_gap_reason"] = pd.Series(dtype="string")
        frame["priority_score"] = pd.Series(dtype="float64")
        return frame.sort_values(
            ["priority_score", "report_date", "report_id"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
    sector_fields = frame.apply(lambda row: _classify_sector(row, sector_rules), axis=1, result_type="expand")
    frame[["theme_bucket", "sector_priority", "sector_quota_bucket", "sector_pilot_quota"]] = sector_fields
    frame["asset_priority"] = frame.apply(_asset_priority, axis=1)
    frame["coverage_gap_reason"] = frame.apply(lambda row: _coverage_gap_reason(row, existing), axis=1)
    frame["priority_score"] = frame.apply(_priority_score, axis=1)
    return frame.sort_values(
        ["priority_score", "report_date", "report_id"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def classify_report_type_bucket(title: Any) -> str:
    text = "" if _is_missing(title) else str(title)
    if any(keyword in text for keyword in ["深度", "首次覆盖", "行业策略", "年度策略", "中期策略", "专题", "框架"]):
        return "P1"
    if any(keyword in text for keyword in ["业绩", "点评", "预告", "季报", "年报", "评级", "目标价", "政策"]):
        return "P2"
    return "P3"


def _normalize_candidate_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    defaults = {
        "report_id": "",
        "report_date": "",
        "title": "",
        "broker": "",
        "stock_code": "",
        "stock_name": "",
        "industry_lv1": "",
        "industry_lv2": "",
        "theme": "",
    }
    for column, default in defaults.items():
        if column not in result.columns:
            result[column] = default
    for column in defaults:
        result[column] = result[column].astype("string").fillna("").str.strip()
    result["report_date"] = pd.to_datetime(result["report_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    result["report_id"] = result.apply(
        lambda row: row["report_id"] or "|".join([row["report_date"], row["broker"], row["stock_code"], row["title"]]),
        axis=1,
    )
    return result


def _normalize_text(value: Any) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip().lower().replace(" ", "")


def _is_missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _classify_sector(row: pd.Series, sector_rules: pd.DataFrame) -> pd.Series:
    haystack = "|".join(str(row.get(column, "")) for column in ["title", "industry_lv1", "industry_lv2", "theme"])
    for rule in sector_rules.to_dict("records"):
        keywords = [item for item in str(rule["match_keywords"]).split("|") if item]
        if any(keyword in haystack for keyword in keywords):
            return pd.Series(
                [
                    str(rule["sector_name"]),
                    str(rule["sector_priority"]),
                    str(rule["sector_quota_bucket"]),
                    int(rule["pilot_quota"]),
                ]
            )
    return pd.Series(["未分类", "P3", "p3_long_tail", 0])


def _asset_priority(row: pd.Series) -> str:
    stock_code = str(row.get("stock_code", "")).strip()
    stock_name = str(row.get("stock_name", "")).strip()
    if stock_code or stock_name:
        return "core_candidate"
    return "cross_sector"


def _coverage_gap_reason(row: pd.Series, existing: pd.DataFrame) -> str:
    if existing.empty:
        return "missing_asset_report" if str(row.get("stock_code", "")).strip() else "missing_sector_report"
    normalized = existing.copy()
    for column in ["stock_code", "normalized_title", "normalized_broker"]:
        if column not in normalized.columns:
            normalized[column] = ""
        normalized[column] = normalized[column].astype("string").fillna("").map(_normalize_text)
    same_asset = normalized["stock_code"].eq(_normalize_text(row.get("stock_code", "")))
    same_title = normalized["normalized_title"].eq(_normalize_text(row.get("title", "")))
    same_broker = normalized["normalized_broker"].eq(_normalize_text(row.get("broker", "")))
    if bool((same_asset & same_title & same_broker).any()):
        return "existing_duplicate"
    if str(row.get("stock_code", "")).strip() and not bool(same_asset.any()):
        return "missing_asset_report"
    return "missing_sector_report"


def _priority_score(row: pd.Series) -> float:
    report_type_score = {"P1": 30, "P2": 20, "P3": 5}.get(str(row.get("report_type_bucket")), 0)
    sector_score = {"P0": 25, "P1": 18, "P2": 10, "P3": 0}.get(str(row.get("sector_priority")), 0)
    broker = str(row.get("broker", ""))
    broker_score = 20 if any(keyword in broker for keyword in A_TIER_BROKER_KEYWORDS) else 8
    date = pd.to_datetime(row.get("report_date"), errors="coerce")
    time_score = 15 if pd.notna(date) and date >= pd.Timestamp("2026-01-01") else 8
    gap_score = {
        "missing_asset_report": 10,
        "missing_sector_report": 8,
        "existing_duplicate": -30,
    }.get(str(row.get("coverage_gap_reason")), 0)
    return float(report_type_score + sector_score + broker_score + time_score + gap_score)
