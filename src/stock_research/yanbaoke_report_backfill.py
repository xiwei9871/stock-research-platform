from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SECTOR_PRIORITY_PATH = PROJECT_ROOT / "config" / "yanbaoke_sector_priority.csv"

DEFAULT_PILOT_QUOTA_BY_BUCKET = {
    "p0_growth_tech_healthcare": 1200,
    "p1_policy_prosperity_export_consumption": 900,
    "p2_finance_real_estate_cycle_macro": 500,
    "cross_sector_macro_theme": 300,
    "manual_correction_reserve": 100,
}

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


def build_yanbaoke_inventory_plan(
    *,
    candidates: pd.DataFrame,
    existing_coverage: pd.DataFrame | None,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    sector_config: pd.DataFrame | None = None,
) -> dict[str, Any]:
    coverage = _shape_existing_coverage(existing_coverage)
    scored = build_scored_candidates(
        candidates,
        existing_coverage=coverage,
        sector_config=sector_config,
    )
    scored = _filter_report_window(scored, start_date=start_date, end_date=end_date)
    sector_gap = build_sector_gap_matrix(scored)
    asset_gap = build_asset_gap_matrix(scored)
    gap_matrix = build_gap_matrix(scored)
    priority_queue = scored.sort_values(
        ["priority_score", "report_date", "report_id"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    pilot_queue = build_sector_quota_pilot_queue(scored, total_limit=3000)
    report = render_inventory_report(
        scored,
        sector_gap,
        asset_gap,
        start_date=start_date,
        end_date=end_date,
    )

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "candidate_reports": target_dir / "yanbaoke_candidate_reports.csv",
        "existing_report_coverage": target_dir / "existing_report_coverage.csv",
        "gap_matrix": target_dir / "yanbaoke_gap_matrix.csv",
        "sector_gap_matrix": target_dir / "yanbaoke_sector_gap_matrix.csv",
        "asset_gap_matrix": target_dir / "yanbaoke_asset_gap_matrix.csv",
        "priority_queue": target_dir / "yanbaoke_priority_queue.csv",
        "pilot_queue": target_dir / "yanbaoke_pilot_queue_top3000.csv",
        "report": target_dir / "yanbaoke_backfill_inventory_report.md",
    }
    scored.to_csv(paths["candidate_reports"], index=False)
    coverage.to_csv(paths["existing_report_coverage"], index=False)
    gap_matrix.to_csv(paths["gap_matrix"], index=False)
    sector_gap.to_csv(paths["sector_gap_matrix"], index=False)
    asset_gap.to_csv(paths["asset_gap_matrix"], index=False)
    priority_queue.to_csv(paths["priority_queue"], index=False)
    pilot_queue.to_csv(paths["pilot_queue"], index=False)
    paths["report"].write_text(report, encoding="utf-8")

    return {
        "candidates": scored,
        "existing_report_coverage": coverage,
        "gap_matrix": gap_matrix,
        "sector_gap_matrix": sector_gap,
        "asset_gap_matrix": asset_gap,
        "priority_queue": priority_queue,
        "pilot_queue": pilot_queue,
        "report": report,
        "paths": {name: str(path) for name, path in paths.items()},
    }


def build_sector_quota_pilot_queue(
    scored: pd.DataFrame,
    *,
    quota_by_bucket: dict[str, int] | None = None,
    total_limit: int = 3000,
) -> pd.DataFrame:
    queue_columns = list(scored.columns)
    if "pilot_rank" not in queue_columns:
        queue_columns.append("pilot_rank")
    if scored.empty or total_limit <= 0:
        return pd.DataFrame(columns=queue_columns)

    quotas = quota_by_bucket if quota_by_bucket is not None else DEFAULT_PILOT_QUOTA_BY_BUCKET
    eligible = scored.loc[~scored["coverage_gap_reason"].eq("existing_duplicate")].copy()
    if eligible.empty:
        return pd.DataFrame(columns=queue_columns)

    sort_columns = ["priority_score", "report_date", "report_id"]
    sort_ascending = [False, False, True]
    selected_parts = []
    selected_indexes: set[Any] = set()
    for bucket, quota in quotas.items():
        if bucket == "manual_correction_reserve" or quota <= 0:
            continue
        bucket_frame = eligible.loc[eligible["sector_quota_bucket"].eq(bucket)]
        bucket_frame = bucket_frame.sort_values(sort_columns, ascending=sort_ascending).head(quota)
        if bucket_frame.empty:
            continue
        selected_parts.append(bucket_frame)
        selected_indexes.update(bucket_frame.index)

    selected = pd.concat(selected_parts) if selected_parts else eligible.head(0)
    if len(selected) < total_limit:
        remaining = eligible.loc[~eligible.index.isin(selected_indexes)]
        remaining = remaining.sort_values(sort_columns, ascending=sort_ascending)
        selected = pd.concat([selected, remaining.head(total_limit - len(selected))])

    selected = selected.head(total_limit).reset_index(drop=True)
    selected["pilot_rank"] = range(1, len(selected) + 1)
    return selected[queue_columns]


def build_gap_matrix(scored: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "month",
        "normalized_broker",
        "industry_lv1",
        "industry_lv2",
        "stock_code",
        "stock_name",
        "report_type_bucket",
        "coverage_gap_reason",
        "candidate_count",
        "max_priority_score",
    ]
    if scored.empty:
        return pd.DataFrame(columns=columns)

    frame = scored.copy()
    frame["month"] = pd.to_datetime(frame["report_date"], errors="coerce").dt.strftime("%Y-%m").fillna("")
    grouped = (
        frame.groupby(
            [
                "month",
                "normalized_broker",
                "industry_lv1",
                "industry_lv2",
                "stock_code",
                "stock_name",
                "report_type_bucket",
                "coverage_gap_reason",
            ],
            dropna=False,
        )
        .agg(
            candidate_count=("report_id", "size"),
            max_priority_score=("priority_score", "max"),
        )
        .reset_index()
    )
    return grouped.sort_values(
        ["month", "max_priority_score", "candidate_count"],
        ascending=[False, False, False],
    ).reset_index(drop=True)[columns]


def build_sector_gap_matrix(scored: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "sector_priority",
        "theme_bucket",
        "candidate_count",
        "p1_count",
        "p2_count",
        "duplicate_count",
        "max_priority_score",
    ]
    if scored.empty:
        return pd.DataFrame(columns=columns)

    frame = scored.copy()
    frame["p1_count"] = frame["report_type_bucket"].eq("P1").astype(int)
    frame["p2_count"] = frame["report_type_bucket"].eq("P2").astype(int)
    frame["duplicate_count"] = frame["coverage_gap_reason"].eq("existing_duplicate").astype(int)
    grouped = (
        frame.groupby(["sector_priority", "theme_bucket"], dropna=False)
        .agg(
            candidate_count=("report_id", "size"),
            p1_count=("p1_count", "sum"),
            p2_count=("p2_count", "sum"),
            duplicate_count=("duplicate_count", "sum"),
            max_priority_score=("priority_score", "max"),
        )
        .reset_index()
    )
    return grouped.sort_values(
        ["sector_priority", "max_priority_score", "candidate_count", "theme_bucket"],
        ascending=[True, False, False, True],
    ).reset_index(drop=True)[columns]


def build_asset_gap_matrix(scored: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "stock_code",
        "stock_name",
        "theme_bucket",
        "candidate_count",
        "best_priority_score",
        "p1_count",
    ]
    if scored.empty or "stock_code" not in scored.columns:
        return pd.DataFrame(columns=columns)

    frame = scored.copy()
    frame = frame[frame["stock_code"].astype("string").fillna("").str.strip().ne("")]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    frame["p1_count"] = frame["report_type_bucket"].eq("P1").astype(int)
    grouped = (
        frame.groupby(["stock_code", "stock_name", "theme_bucket"], dropna=False)
        .agg(
            candidate_count=("report_id", "size"),
            best_priority_score=("priority_score", "max"),
            p1_count=("p1_count", "sum"),
        )
        .reset_index()
    )
    return grouped.sort_values(
        ["best_priority_score", "candidate_count", "stock_code"],
        ascending=[False, False, True],
    ).reset_index(drop=True)[columns]


def render_inventory_report(
    scored: pd.DataFrame,
    sector_gap: pd.DataFrame,
    asset_gap: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
) -> str:
    priority_distribution = _priority_distribution(scored)
    top_sector_gaps = sector_gap.head(10)
    top_asset_gaps = asset_gap.head(10)
    return "\n".join(
        [
            "# Yanbaoke Report Backfill Inventory",
            "",
            f"Window: {start_date} to {end_date}",
            "",
            f"Candidate count: {len(scored)}",
            f"Sector group count: {len(sector_gap)}",
            f"Asset group count: {len(asset_gap)}",
            "",
            "## Priority Distribution",
            "",
            _markdown_table(priority_distribution),
            "",
            "## Top Sector Gaps",
            "",
            _markdown_table(top_sector_gaps),
            "",
            "## Top Asset Gaps",
            "",
            _markdown_table(top_asset_gaps),
            "",
        ]
    )


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


def _filter_report_window(scored: pd.DataFrame, *, start_date: str, end_date: str) -> pd.DataFrame:
    if scored.empty:
        return scored.copy()
    dates = pd.to_datetime(scored["report_date"], errors="coerce")
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    return scored.loc[dates.between(start, end, inclusive="both")].reset_index(drop=True)


def _shape_existing_coverage(existing_coverage: pd.DataFrame | None) -> pd.DataFrame:
    canonical = [
        "report_date",
        "normalized_title",
        "normalized_broker",
        "stock_code",
        "report_type",
    ]
    if existing_coverage is None:
        return pd.DataFrame(columns=canonical)

    coverage = existing_coverage.copy()
    for column in canonical:
        if column not in coverage.columns:
            coverage[column] = ""
    extra_columns = [column for column in coverage.columns if column not in canonical]
    return coverage[canonical + extra_columns]


def _priority_distribution(scored: pd.DataFrame) -> pd.DataFrame:
    columns = ["sector_priority", "report_type_bucket", "candidate_count"]
    if scored.empty or not {"sector_priority", "report_type_bucket"} <= set(scored.columns):
        return pd.DataFrame(columns=columns)
    return (
        scored.groupby(["sector_priority", "report_type_bucket"], dropna=False)
        .size()
        .reset_index(name="candidate_count")
        .sort_values(["sector_priority", "report_type_bucket"])
        .reset_index(drop=True)[columns]
    )


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_None_"
    text_frame = frame.fillna("").astype(str)
    header = "| " + " | ".join(text_frame.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(text_frame.columns)) + " |"
    rows = ["| " + " | ".join(row) + " |" for row in text_frame.to_numpy()]
    return "\n".join([header, separator, *rows])


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
