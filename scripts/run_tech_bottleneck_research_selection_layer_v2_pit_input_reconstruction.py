#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
DESIGN_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_design"
ADMISSION_DIR = RESEARCH_DIR / "tech_bottleneck_research_input_watchlist_forward_return_v1"
ANN_DIR = RESEARCH_DIR / "tech_bottleneck_announcement_fulltext_extraction_v2"
FUND_DIR = RESEARCH_DIR / "tech_bottleneck_fundamental_source_adapter_v1"
BAOSTOCK_DIR = RESEARCH_DIR / "tech_bottleneck_baostock_pe_pb_ps_source_adapter_v1"
BAIDU_DIR = RESEARCH_DIR / "tech_bottleneck_akshare_baidu_valuation_probe_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_pit_input_reconstruction_v1"
RULE_VERSION = "tech_bottleneck_research_selection_layer_v2_pit_input_reconstruction_v1"

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|止损点|交易信号"),
]

FEATURE_SPECS = [
    ("thesis_available", "thesis", "original_research_selection"),
    ("announcement_fulltext_support", "announcement", "announcement_fulltext"),
    ("specific_validation_count", "announcement", "announcement_fulltext"),
    ("specific_risk_event_count", "risk_review", "announcement_fulltext"),
    ("generic_business_description_count", "announcement", "announcement_fulltext"),
    ("generic_disclosure_text_count", "risk_review", "announcement_fulltext"),
    ("title_only_remaining_count", "data_quality", "announcement_fulltext"),
    ("fundamental_support", "fundamental", "fundamental_derived_pit"),
    ("fundamental_recovery_signal", "fundamental", "fundamental_derived_pit"),
    ("fundamental_risk_level", "fundamental", "fundamental_derived_pit"),
    ("fundamental_quality_level", "fundamental", "fundamental_derived_pit"),
    ("fundamental_recovery_score", "fundamental", "fundamental_derived_pit"),
    ("fundamental_risk_score", "fundamental", "fundamental_derived_pit"),
    ("fundamental_quality_score", "fundamental", "fundamental_derived_pit"),
    ("baostock_valuation_support", "valuation", "baostock_valuation"),
    ("pe_meaningfulness", "valuation", "baostock_valuation"),
    ("valuation_context_level", "valuation", "baostock_valuation"),
    ("pe_ttm_percentile_3y", "valuation", "baostock_valuation"),
    ("pb_percentile_3y", "valuation", "baostock_valuation"),
    ("ps_ttm_percentile_3y", "valuation", "baostock_valuation"),
    ("baidu_validation_status", "cross_source_validation", "baidu_validation"),
    ("cross_source_discrepancy_flag", "cross_source_validation", "baidu_validation"),
    ("human_review_required", "data_quality", "dashboard_readonly"),
    ("data_quality_status", "data_quality", "consolidated_snapshot"),
    ("degraded_source_warning", "data_quality", "dashboard_readonly"),
    ("forward_return_context", "forward_return_context", "forward_return"),
]

RULE_REQUIREMENTS = {
    "v2_baseline_plus_fundamental_quality": ["thesis_available", "fundamental_recovery_signal", "fundamental_quality_level"],
    "v2_announcement_risk_review_queue": ["specific_risk_event_count"],
    "v2_specific_validation_review_priority": ["specific_validation_count"],
    "v2_valuation_context_filter": ["baostock_valuation_support", "pe_meaningfulness", "valuation_context_level"],
    "v2_cross_source_discrepancy_warning": ["baidu_validation_status", "cross_source_discrepancy_flag"],
    "v2_high_quality_review_candidates": [
        "thesis_available",
        "announcement_fulltext_support",
        "fundamental_support",
        "baostock_valuation_support",
        "baidu_validation_status",
    ],
}


def contains_actionable_trading_language(text: str) -> bool:
    return any(pattern.search(str(text)) for pattern in FORBIDDEN_PATTERNS)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _git_lines(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, check=False, text=True, capture_output=True)
    return (result.stdout or result.stderr or "").strip()


def _count_output_hits(root: Path) -> int:
    hits = 0
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".csv", ".md", ".txt"}:
            if contains_actionable_trading_language(path.read_text(encoding="utf-8", errors="ignore")):
                hits += 1
    return hits


def _to_date(value: Any) -> pd.Timestamp | pd.NaT:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return pd.NaT
    return pd.to_datetime(value, errors="coerce")


def _date_text(value: Any) -> str:
    dt = _to_date(value)
    return "" if pd.isna(dt) else dt.strftime("%Y-%m-%d")


def _bool_text(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _latest_before(df: pd.DataFrame, date_col: str, cutoff: pd.Timestamp) -> pd.Series | None:
    if df.empty or date_col not in df.columns:
        return None
    dated = df.copy()
    dated[date_col] = pd.to_datetime(dated[date_col], errors="coerce")
    dated = dated[dated[date_col].notna()]
    before = dated[dated[date_col] <= cutoff].sort_values(date_col)
    if before.empty:
        return None
    return before.iloc[-1]


def _first_after(df: pd.DataFrame, date_col: str, cutoff: pd.Timestamp) -> pd.Series | None:
    if df.empty or date_col not in df.columns:
        return None
    dated = df.copy()
    dated[date_col] = pd.to_datetime(dated[date_col], errors="coerce")
    dated = dated[dated[date_col].notna()]
    after = dated[dated[date_col] > cutoff].sort_values(date_col)
    if after.empty:
        return None
    return after.iloc[0]


def load_inputs() -> dict[str, pd.DataFrame]:
    admissions = _read_csv(ADMISSION_DIR / "watchlist_admission_events.csv")
    admissions = admissions[admissions["admission_variant"].eq("standard_research_watchlist")].copy()
    admissions["first_admission_date"] = pd.to_datetime(admissions["first_admission_date"], errors="coerce")

    baidu_raw = _read_baidu_cache_dates(admissions)
    return {
        "admissions": admissions,
        "ann": _read_csv(ANN_DIR / "announcement_fulltext_v2_structured_evidence.csv"),
        "fund": _read_csv(FUND_DIR / "fundamental_structured_outputs.csv"),
        "baostock_raw": _read_csv(BAOSTOCK_DIR / "baostock_raw_candidate_matches.csv"),
        "baostock_structured": _read_csv(BAOSTOCK_DIR / "baostock_structured_outputs.csv"),
        "baostock_percentiles": _read_csv(BAOSTOCK_DIR / "baostock_percentile_outputs.csv"),
        "baidu_structured": _read_csv(BAIDU_DIR / "akshare_baidu_structured_outputs.csv"),
        "baidu_cross": _read_csv(BAIDU_DIR / "akshare_baidu_baostock_cross_validation.csv"),
        "baidu_raw": baidu_raw,
        "rule_candidates": _read_csv(DESIGN_DIR / "research_selection_v2_rule_candidates.csv"),
        "features": _read_csv(DESIGN_DIR / "research_selection_v2_feature_dictionary.csv"),
    }


def _read_baidu_cache_dates(admissions: pd.DataFrame) -> pd.DataFrame:
    cache_dir = BAIDU_DIR / "cache/akshare/baidu_valuation"
    rows: list[dict[str, Any]] = []
    if not cache_dir.exists() or admissions.empty:
        return pd.DataFrame(columns=["asset_id", "symbol", "indicator", "date", "value"])
    for _, event in admissions.iterrows():
        symbol = str(event["symbol"]).zfill(6)
        asset_id = event["asset_id"]
        for path in cache_dir.glob(f"{symbol}_*.csv"):
            indicator = path.stem.replace(f"{symbol}_", "")
            df = _read_csv(path)
            if df.empty or "date" not in df.columns:
                continue
            slim = df[["date"] + (["value"] if "value" in df.columns else [])].copy()
            slim["asset_id"] = asset_id
            slim["symbol"] = symbol
            slim["indicator"] = indicator
            rows.extend(slim.to_dict("records"))
    if not rows:
        return pd.DataFrame(columns=["asset_id", "symbol", "indicator", "date", "value"])
    result = pd.DataFrame(rows)
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    return result[result["date"].notna()].copy()


def build_source_date_inventory(inputs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    def fields(df: pd.DataFrame) -> str:
        return "|".join(df.columns[:80]) if not df.empty else ""

    rows = [
        {
            "source_layer": "announcement_fulltext",
            "source_file": "announcement_fulltext_v2_structured_evidence.csv",
            "asset_id_field": "asset_id",
            "primary_date_field": "announcement_date",
            "as_of_date_field": "as_of_date",
            "usable_date_field": "as_of_date",
            "available_fields": fields(inputs["ann"]),
            "date_coverage_count": int(pd.to_datetime(inputs["ann"].get("as_of_date"), errors="coerce").notna().sum()) if not inputs["ann"].empty else 0,
            "asset_coverage_count": int(inputs["ann"].get("asset_id", pd.Series(dtype=str)).nunique()) if not inputs["ann"].empty else 0,
            "pit_rule": "as_of_date <= first_admission_date",
            "pit_ready": True,
            "pit_gap": "requires event-level date join",
            "notes": "fulltext evidence date available",
        },
        {
            "source_layer": "fundamental_derived_pit",
            "source_file": "fundamental_structured_outputs.csv",
            "asset_id_field": "asset_id",
            "primary_date_field": "financial_as_of_date",
            "as_of_date_field": "announcement_date|as_of_date",
            "usable_date_field": "as_of_date",
            "available_fields": fields(inputs["fund"]),
            "date_coverage_count": int(pd.to_datetime(inputs["fund"].get("as_of_date"), errors="coerce").notna().sum()) if not inputs["fund"].empty else 0,
            "asset_coverage_count": int(inputs["fund"].get("asset_id", pd.Series(dtype=str)).nunique()) if not inputs["fund"].empty else 0,
            "pit_rule": "as_of_date <= first_admission_date",
            "pit_ready": True,
            "pit_gap": "derived detail coverage remains degraded",
            "notes": "PIT dates exist but full statement fields still missing",
        },
        {
            "source_layer": "baostock_valuation",
            "source_file": "baostock_raw_candidate_matches.csv",
            "asset_id_field": "asset_id",
            "primary_date_field": "baostock_date",
            "as_of_date_field": "baostock_date",
            "usable_date_field": "baostock_date",
            "available_fields": fields(inputs["baostock_raw"]),
            "date_coverage_count": int(pd.to_datetime(inputs["baostock_raw"].get("baostock_date"), errors="coerce").notna().sum()) if not inputs["baostock_raw"].empty else 0,
            "asset_coverage_count": int(inputs["baostock_raw"].get("asset_id", pd.Series(dtype=str)).nunique()) if not inputs["baostock_raw"].empty else 0,
            "pit_rule": "baostock_date <= first_admission_date",
            "pit_ready": True,
            "pit_gap": "valuation context labels must be recomputed by event date",
            "notes": "historical raw dates available",
        },
        {
            "source_layer": "baidu_validation",
            "source_file": "cache/akshare/baidu_valuation/*.csv",
            "asset_id_field": "asset_id",
            "primary_date_field": "date",
            "as_of_date_field": "date",
            "usable_date_field": "date",
            "available_fields": fields(inputs["baidu_raw"]),
            "date_coverage_count": int(inputs["baidu_raw"].get("date", pd.Series(dtype="datetime64[ns]")).notna().sum()) if not inputs["baidu_raw"].empty else 0,
            "asset_coverage_count": int(inputs["baidu_raw"].get("asset_id", pd.Series(dtype=str)).nunique()) if not inputs["baidu_raw"].empty else 0,
            "pit_rule": "date <= first_admission_date",
            "pit_ready": True,
            "pit_gap": "cross-source validation status must be recomputed by event date",
            "notes": "Baidu does not validate PS/PS-TTM",
        },
        {
            "source_layer": "consolidated_snapshot",
            "source_file": "watchlist_report_consolidated_summary_by_asset.csv",
            "asset_id_field": "asset_id",
            "primary_date_field": "snapshot_date",
            "as_of_date_field": "none",
            "usable_date_field": "none",
            "available_fields": "snapshot fields",
            "date_coverage_count": 0,
            "asset_coverage_count": 102,
            "pit_rule": "not a PIT source",
            "pit_ready": False,
            "pit_gap": "not PIT source; ex-post snapshot only",
            "notes": "use underlying source layers instead",
        },
        {
            "source_layer": "dashboard_readonly",
            "source_file": "tech_bottleneck_dashboard_table.csv",
            "asset_id_field": "asset_id",
            "primary_date_field": "snapshot_date",
            "as_of_date_field": "none",
            "usable_date_field": "none",
            "available_fields": "dashboard package fields",
            "date_coverage_count": 0,
            "asset_coverage_count": 102,
            "pit_rule": "not a PIT source",
            "pit_ready": False,
            "pit_gap": "not PIT source; review package only",
            "notes": "read-only UI data cannot define historical inputs",
        },
        {
            "source_layer": "forward_return",
            "source_file": "watchlist_forward_return_30_60_90_120.csv",
            "asset_id_field": "asset_id",
            "primary_date_field": "horizon_end_date",
            "as_of_date_field": "future outcome",
            "usable_date_field": "none",
            "available_fields": "forward return fields",
            "date_coverage_count": 0,
            "asset_coverage_count": 102,
            "pit_rule": "outcome only",
            "pit_ready": False,
            "pit_gap": "outcome_only; not feature",
            "notes": "used only after candidate event definition",
        },
    ]
    return pd.DataFrame(rows)


def _ann_feature(feature: str, df: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[Any, pd.Series | None]:
    before = df[pd.to_datetime(df.get("as_of_date"), errors="coerce") <= cutoff].copy() if not df.empty else pd.DataFrame()
    if feature == "announcement_fulltext_support":
        value = bool(len(before) > 0)
    elif feature == "specific_validation_count":
        value = int((before.get("evidence_direction", pd.Series(dtype=str)).eq("positive_or_validation")).sum())
    elif feature == "specific_risk_event_count":
        value = int((before.get("risk_event_score", pd.Series(dtype=float)).fillna(0) > 0).sum())
    elif feature == "generic_business_description_count":
        value = int((before.get("evidence_direction", pd.Series(dtype=str)).eq("generic_business_description")).sum())
    elif feature == "generic_disclosure_text_count":
        value = int((before.get("evidence_strength", pd.Series(dtype=str)).eq("generic_disclosure_text")).sum())
    elif feature == "title_only_remaining_count":
        value = int((before.get("fulltext_status", pd.Series(dtype=str)).eq("title_only")).sum())
    else:
        value = ""
    row = _latest_before(df, "as_of_date", cutoff)
    return value, row


def _fund_feature(feature: str, row: pd.Series | None) -> Any:
    if row is None:
        if feature == "fundamental_support":
            return False
        return ""
    if feature == "fundamental_support":
        return True
    mapping = {
        "fundamental_recovery_signal": "fundamental_recovery_score",
        "fundamental_risk_level": "fundamental_risk_score",
        "fundamental_quality_level": "fundamental_quality_score",
    }
    if feature in mapping:
        value = row.get(mapping[feature], "")
        if feature == "fundamental_recovery_signal":
            if pd.isna(value):
                return "recovery_missing"
            return "recovery_positive" if float(value) >= 0.65 else "recovery_neutral" if float(value) >= 0.45 else "recovery_weak"
        if feature == "fundamental_risk_level":
            if pd.isna(value):
                return "risk_missing"
            return "risk_high" if float(value) >= 0.7 else "risk_medium" if float(value) >= 0.35 else "risk_low"
        if feature == "fundamental_quality_level":
            if pd.isna(value):
                return "quality_missing"
            return "quality_high" if float(value) >= 0.75 else "quality_medium" if float(value) >= 0.55 else "quality_low"
    return row.get(feature, "")


def _baostock_feature(feature: str, asset_rows: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[Any, pd.Series | None]:
    row = _latest_before(asset_rows, "baostock_date", cutoff)
    if row is None:
        if feature == "baostock_valuation_support":
            return False, None
        return "", None
    if feature == "baostock_valuation_support":
        return True, row
    if feature == "pe_meaningfulness":
        return "reconstructable_from_raw_cache", row
    if feature == "valuation_context_level":
        return "requires_event_date_recompute", row
    if feature.endswith("_percentile_3y"):
        return "requires_event_date_recompute", row
    return "", row


def _baidu_feature(feature: str, asset_rows: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[Any, pd.Series | None]:
    row = _latest_before(asset_rows, "date", cutoff)
    if row is None:
        return "", None
    if feature == "baidu_validation_status":
        return "requires_event_date_recompute", row
    if feature == "cross_source_discrepancy_flag":
        return "requires_event_date_recompute", row
    return "", row


def build_feature_availability_by_asset(inputs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    admissions = inputs["admissions"]
    ann = inputs["ann"].copy()
    fund = inputs["fund"].copy()
    baostock = inputs["baostock_raw"].copy()
    baidu = inputs["baidu_raw"].copy()
    rows: list[dict[str, Any]] = []

    for _, event in admissions.iterrows():
        asset_id = event["asset_id"]
        cutoff = event["first_admission_date"]
        ann_asset = ann[ann.get("asset_id", pd.Series(dtype=str)).eq(asset_id)].copy()
        fund_asset = fund[fund.get("asset_id", pd.Series(dtype=str)).eq(asset_id)].copy()
        baostock_asset = baostock[baostock.get("asset_id", pd.Series(dtype=str)).eq(asset_id)].copy()
        baidu_asset = baidu[baidu.get("asset_id", pd.Series(dtype=str)).eq(asset_id)].copy()
        fund_row = _latest_before(fund_asset, "as_of_date", cutoff)

        for feature, group, layer in FEATURE_SPECS:
            value: Any = ""
            source_date = as_of_date = usable_date = pd.NaT
            blocking = ""
            if layer == "original_research_selection":
                value = True
                source_date = as_of_date = usable_date = _to_date(event.get("first_source_date"))
                status = "pit_available" if usable_date <= cutoff else "pit_unavailable_after_admission"
            elif layer == "announcement_fulltext":
                value, row = _ann_feature(feature, ann_asset, cutoff)
                if row is not None:
                    source_date = _to_date(row.get("announcement_date"))
                    as_of_date = usable_date = _to_date(row.get("as_of_date"))
                    status = "pit_available"
                else:
                    after = _first_after(ann_asset, "as_of_date", cutoff)
                    if after is not None:
                        source_date = _to_date(after.get("announcement_date"))
                        as_of_date = usable_date = _to_date(after.get("as_of_date"))
                        status = "pit_unavailable_after_admission"
                        blocking = "source_after_admission"
                    elif ann_asset.empty:
                        status = "source_missing"
                        blocking = "source_missing"
                    else:
                        status = "date_missing"
                        blocking = "date_missing"
            elif layer == "fundamental_derived_pit":
                value = _fund_feature(feature, fund_row)
                if fund_row is not None:
                    source_date = _to_date(fund_row.get("financial_as_of_date"))
                    as_of_date = usable_date = _to_date(fund_row.get("as_of_date"))
                    status = "pit_available"
                else:
                    after = _first_after(fund_asset, "as_of_date", cutoff)
                    if after is not None:
                        source_date = _to_date(after.get("financial_as_of_date"))
                        as_of_date = usable_date = _to_date(after.get("as_of_date"))
                        status = "pit_unavailable_after_admission"
                        blocking = "source_after_admission"
                    elif fund_asset.empty:
                        status = "source_missing"
                        blocking = "source_missing"
                    else:
                        status = "date_missing"
                        blocking = "date_missing"
            elif layer == "baostock_valuation":
                value, row = _baostock_feature(feature, baostock_asset, cutoff)
                if row is not None:
                    source_date = as_of_date = usable_date = _to_date(row.get("baostock_date"))
                    status = "pit_available"
                    if feature != "baostock_valuation_support":
                        blocking = "requires_event_date_recompute"
                elif baostock_asset.empty:
                    status = "source_missing"
                    blocking = "source_missing"
                else:
                    after = _first_after(baostock_asset, "baostock_date", cutoff)
                    if after is not None:
                        source_date = as_of_date = usable_date = _to_date(after.get("baostock_date"))
                        status = "pit_unavailable_after_admission"
                        blocking = "source_after_admission"
                    else:
                        status = "date_missing"
                        blocking = "date_missing"
            elif layer == "baidu_validation":
                value, row = _baidu_feature(feature, baidu_asset, cutoff)
                if row is not None:
                    source_date = as_of_date = usable_date = _to_date(row.get("date"))
                    status = "pit_available"
                    blocking = "requires_event_date_recompute"
                elif baidu_asset.empty:
                    status = "source_missing"
                    blocking = "source_missing"
                else:
                    after = _first_after(baidu_asset, "date", cutoff)
                    if after is not None:
                        source_date = as_of_date = usable_date = _to_date(after.get("date"))
                        status = "pit_unavailable_after_admission"
                        blocking = "source_after_admission"
                    else:
                        status = "date_missing"
                        blocking = "date_missing"
            elif layer in {"consolidated_snapshot", "dashboard_readonly"}:
                value = ""
                status = "snapshot_only"
                blocking = "snapshot_only_feature"
            elif layer == "forward_return":
                value = ""
                status = "outcome_only"
                blocking = "outcome_feature"
            else:
                status = "not_applicable"

            available = status == "pit_available"
            days = ""
            if available and pd.notna(usable_date):
                days = int((cutoff - usable_date).days)
            rows.append(
                {
                    "asset_id": asset_id,
                    "symbol": str(event["symbol"]).zfill(6),
                    "name": event["name"],
                    "feature_name": feature,
                    "feature_group": group,
                    "source_layer": layer,
                    "feature_value": value,
                    "source_date": _date_text(source_date),
                    "as_of_date": _date_text(as_of_date),
                    "usable_date": _date_text(usable_date),
                    "first_admission_date": _date_text(cutoff),
                    "available_before_first_admission": available,
                    "days_between_usable_and_admission": days,
                    "pit_status": status,
                    "availability_status": "available" if available else "blocked",
                    "blocking_reason": blocking or ("none" if available else status),
                    "used_for_signal": False,
                }
            )
    return pd.DataFrame(rows)


def build_event_availability(features: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (asset_id, first_date), group in features.groupby(["asset_id", "first_admission_date"], sort=False):
        first = group.iloc[0]

        def avail(feature: str) -> bool:
            row = group[group["feature_name"].eq(feature)]
            return bool(not row.empty and row["pit_status"].iloc[0] == "pit_available")

        checks = {
            "announcement_pit_available": avail("announcement_fulltext_support"),
            "specific_validation_pit_available": avail("specific_validation_count"),
            "specific_risk_event_pit_available": avail("specific_risk_event_count"),
            "fundamental_pit_available": avail("fundamental_support"),
            "fundamental_recovery_pit_available": avail("fundamental_recovery_signal"),
            "fundamental_quality_pit_available": avail("fundamental_quality_level"),
            "baostock_valuation_pit_available": avail("baostock_valuation_support"),
            "pe_meaningfulness_pit_available": avail("pe_meaningfulness"),
            "valuation_context_pit_available": avail("valuation_context_level"),
            "baidu_validation_pit_available": avail("baidu_validation_status"),
        }
        core = [
            "announcement_pit_available",
            "fundamental_pit_available",
            "baostock_valuation_pit_available",
            "baidu_validation_pit_available",
        ]
        count = int(sum(checks.values()))
        missing = [key.replace("_pit_available", "") for key, value in checks.items() if not value]
        if all(checks[key] for key in core):
            readiness = "ready_for_v2_replay"
        elif count > 0:
            readiness = "partial_ready"
        else:
            readiness = "only_baseline_ready"
        rows.append(
            {
                "asset_id": asset_id,
                "symbol": first["symbol"],
                "name": first["name"],
                "first_admission_date": first_date,
                **checks,
                "all_v2_core_features_pit_available": all(checks[key] for key in core),
                "pit_available_feature_count": count,
                "pit_missing_feature_count": len(checks) - count,
                "pit_blocking_features": "|".join(missing),
                "event_pit_readiness": readiness,
                "used_for_signal": False,
            }
        )
    return pd.DataFrame(rows)


def build_rule_candidate_readiness(features: pd.DataFrame, events: pd.DataFrame, rule_candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    ready_rows: list[dict[str, Any]] = []
    event_groups = {key: group for key, group in features.groupby(["asset_id", "first_admission_date"], sort=False)}

    def row_map(group: pd.DataFrame) -> dict[str, pd.Series]:
        return {row.feature_name: pd.Series(row._asdict()) for row in group.itertuples(index=False)}

    def is_ready(feature_rows: dict[str, pd.Series], feature: str) -> bool:
        row = feature_rows.get(feature)
        return bool(row is not None and row.get("pit_status") == "pit_available")

    def value(feature_rows: dict[str, pd.Series], feature: str) -> Any:
        row = feature_rows.get(feature)
        return "" if row is None else row.get("feature_value", "")

    def numeric_value(feature_rows: dict[str, pd.Series], feature: str) -> float:
        return float(pd.to_numeric(pd.Series([value(feature_rows, feature)]), errors="coerce").fillna(0).iloc[0])

    def rule_condition_met(rule_name: str, feature_rows: dict[str, pd.Series]) -> bool:
        if rule_name == "v2_baseline_plus_fundamental_quality":
            recovery = str(value(feature_rows, "fundamental_recovery_signal"))
            quality = str(value(feature_rows, "fundamental_quality_level"))
            return (
                is_ready(feature_rows, "thesis_available")
                and is_ready(feature_rows, "fundamental_recovery_signal")
                and is_ready(feature_rows, "fundamental_quality_level")
                and (recovery == "recovery_positive" or quality in {"quality_medium", "quality_high"})
            )
        if rule_name == "v2_announcement_risk_review_queue":
            return is_ready(feature_rows, "specific_risk_event_count") and numeric_value(feature_rows, "specific_risk_event_count") > 0
        if rule_name == "v2_specific_validation_review_priority":
            return is_ready(feature_rows, "specific_validation_count") and numeric_value(feature_rows, "specific_validation_count") > 0
        if rule_name == "v2_valuation_context_filter":
            return all(is_ready(feature_rows, f) for f in ["baostock_valuation_support", "pe_meaningfulness", "valuation_context_level"])
        if rule_name == "v2_cross_source_discrepancy_warning":
            return all(is_ready(feature_rows, f) for f in ["baidu_validation_status", "cross_source_discrepancy_flag"])
        if rule_name == "v2_high_quality_review_candidates":
            source_support = is_ready(feature_rows, "announcement_fulltext_support") or is_ready(feature_rows, "fundamental_support")
            return (
                is_ready(feature_rows, "thesis_available")
                and source_support
                and is_ready(feature_rows, "baostock_valuation_support")
                and is_ready(feature_rows, "baidu_validation_status")
            )
        return False

    for _, rule in rule_candidates.iterrows():
        name = rule["rule_candidate_name"]
        required = RULE_REQUIREMENTS.get(name, [])
        candidate_ready = partial = not_ready = 0
        unavailable_features: set[str] = set()
        for (asset_id, first_date), group in event_groups.items():
            req_rows = group[group["feature_name"].isin(required)]
            feature_rows = row_map(group)
            feature_dates_ready = len(req_rows) == len(required) and req_rows["pit_status"].eq("pit_available").all()
            ready = feature_dates_ready and rule_condition_met(name, feature_rows)
            if ready:
                candidate_ready += 1
                first = group.iloc[0]
                ready_rows.append(
                    {
                        "rule_candidate_name": name,
                        "asset_id": asset_id,
                        "symbol": first["symbol"],
                        "name": first["name"],
                        "first_admission_date": first_date,
                        "required_features_available": True,
                        "pit_available_feature_count": len(required),
                        "required_feature_count": len(required),
                        "pit_replay_ready": True,
                        "source_dates_used": "|".join(f"{r.feature_name}:{r.usable_date}" for r in req_rows.itertuples(index=False)),
                        "feature_values_used": "|".join(f"{r.feature_name}:{r.feature_value}" for r in req_rows.itertuples(index=False)),
                        "used_for_signal": False,
                    }
                )
            else:
                available_count = int(req_rows["pit_status"].eq("pit_available").sum())
                if available_count > 0:
                    partial += 1
                else:
                    not_ready += 1
                unavailable_features.update(req_rows.loc[~req_rows["pit_status"].eq("pit_available"), "feature_name"].tolist())
        if candidate_ready >= 10:
            status = "ready_for_replay"
            action = "run_pit_replay"
        elif candidate_ready > 0:
            status = "partial_replay_possible"
            action = "run_limited_replay_with_warning"
        else:
            status = "blocked_by_source_dates"
            action = "backfill_source_dates"
        if name in {"v2_valuation_context_filter", "v2_cross_source_discrepancy_warning", "v2_high_quality_review_candidates"} and candidate_ready > 0:
            status = "partial_replay_possible"
            action = "recompute_event_date_labels_before_replay"
        rows.append(
            {
                "rule_candidate_name": name,
                "required_features": "|".join(required),
                "required_feature_count": len(required),
                "pit_available_feature_count": len(required) - len(unavailable_features),
                "pit_unavailable_feature_count": len(unavailable_features),
                "candidate_event_count": len(event_groups),
                "pit_ready_event_count": candidate_ready,
                "partial_ready_event_count": partial,
                "not_ready_event_count": not_ready,
                "pit_replay_status": status,
                "blocking_gaps": "|".join(sorted(unavailable_features)) if unavailable_features else "event_date_label_recompute_required",
                "recommended_action": action,
                "used_for_signal": False,
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(ready_rows, columns=[
        "rule_candidate_name",
        "asset_id",
        "symbol",
        "name",
        "first_admission_date",
        "required_features_available",
        "pit_available_feature_count",
        "required_feature_count",
        "pit_replay_ready",
        "source_dates_used",
        "feature_values_used",
        "used_for_signal",
    ])


def build_blocker_report(features: pd.DataFrame, readiness: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    blocked = features[~features["pit_status"].eq("pit_available")].copy()
    for (status, layer, feature), group in blocked.groupby(["pit_status", "source_layer", "feature_name"], sort=False):
        if status == "snapshot_only":
            blocker_type = "snapshot_only_feature"
        elif status == "outcome_only":
            blocker_type = "outcome_feature"
        elif status == "date_missing":
            blocker_type = "missing_source_date"
        elif status == "pit_unavailable_after_admission":
            blocker_type = "source_after_admission"
        elif status == "source_missing":
            blocker_type = "missing_source_file"
        else:
            blocker_type = "ambiguous_date_semantics"
        rows.append(
            {
                "blocker_type": blocker_type,
                "source_layer": layer,
                "feature_name": feature,
                "affected_asset_count": int(group["asset_id"].nunique()),
                "affected_event_count": len(group),
                "example_asset_ids": "|".join(group["asset_id"].head(5).tolist()),
                "blocking_reason": "|".join(sorted(set(group["blocking_reason"].astype(str)))),
                "recommended_fix": "use underlying dated source rows" if blocker_type in {"snapshot_only_feature", "outcome_feature"} else "backfill or join source date",
                "recommended_next_task": "tech_bottleneck_source_availability_date_backfill_v1",
            }
        )
    recompute = features[features["blocking_reason"].eq("requires_event_date_recompute")].copy()
    for (layer, feature), group in recompute.groupby(["source_layer", "feature_name"], sort=False):
        rows.append(
            {
                "blocker_type": "ambiguous_date_semantics",
                "source_layer": layer,
                "feature_name": feature,
                "affected_asset_count": int(group["asset_id"].nunique()),
                "affected_event_count": len(group),
                "example_asset_ids": "|".join(group["asset_id"].head(5).tolist()),
                "blocking_reason": "event_date_label_recompute_required",
                "recommended_fix": "recompute feature label using rows no later than first admission date",
                "recommended_next_task": "tech_bottleneck_research_selection_layer_v2_pit_replay_v1",
            }
        )
    insufficient = readiness[~readiness["pit_replay_status"].eq("ready_for_replay")]
    for _, row in insufficient.iterrows():
        rows.append(
            {
                "blocker_type": "insufficient_ready_events",
                "source_layer": "rule_candidate",
                "feature_name": row["rule_candidate_name"],
                "affected_asset_count": int(row["candidate_event_count"]) - int(row["pit_ready_event_count"]),
                "affected_event_count": int(row["candidate_event_count"]) - int(row["pit_ready_event_count"]),
                "example_asset_ids": "",
                "blocking_reason": row["blocking_gaps"],
                "recommended_fix": row["recommended_action"],
                "recommended_next_task": "tech_bottleneck_research_selection_layer_v2_pit_replay_v1",
            }
        )
    return pd.DataFrame(rows)


def build_quality_audit(inventory: pd.DataFrame, features: pd.DataFrame, events: pd.DataFrame, readiness: pd.DataFrame, ready: pd.DataFrame) -> pd.DataFrame:
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    rows = [
        ("source layers evaluated", len(inventory), "source inventory rows"),
        ("features evaluated", int(features["feature_name"].nunique()), "unique feature names"),
        ("assets evaluated", int(features["asset_id"].nunique()), "standard watchlist assets"),
        ("admission events evaluated", len(events), "standard admission events"),
        ("pit_available feature rows", int(features["pit_status"].eq("pit_available").sum()), "usable before admission"),
        ("pit_unavailable_after_admission rows", int(features["pit_status"].eq("pit_unavailable_after_admission").sum()), "source date after admission"),
        ("date_missing rows", int(features["pit_status"].eq("date_missing").sum()), "missing date rows"),
        ("snapshot_only rows", int(features["pit_status"].eq("snapshot_only").sum()), "snapshot not PIT source"),
        ("outcome_only rows", int(features["pit_status"].eq("outcome_only").sum()), "outcome rows"),
        ("rule candidates evaluated", len(readiness), "rule candidates"),
        ("rule candidates ready for replay", int(readiness["pit_replay_status"].eq("ready_for_replay").sum()), "ready candidates"),
        ("rule candidates partial ready", int(readiness["pit_replay_status"].eq("partial_replay_possible").sum()), "partial candidates"),
        ("rule candidates blocked", int(readiness["pit_replay_status"].isin(["blocked_by_source_dates", "ex_post_only", "do_not_replay"]).sum()), "blocked candidates"),
        ("replay ready candidate events", len(ready), "strict ready event rows"),
        ("lookahead violation rows", 0, "all availability checks use usable_date <= first_admission_date"),
        ("used_for_signal false count", int((features["used_for_signal"].astype(str).str.lower() == "false").sum()) + int((readiness["used_for_signal"].astype(str).str.lower() == "false").sum()) + int((ready["used_for_signal"].astype(str).str.lower() == "false").sum()) if not ready.empty else int((features["used_for_signal"].astype(str).str.lower() == "false").sum()) + int((readiness["used_for_signal"].astype(str).str.lower() == "false").sum()), "research-only rows"),
        ("trading language hit count", 0, "computed after write"),
        ("formal strategy file status", status, "untracked status must remain visible"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def render_report(inventory: pd.DataFrame, features: pd.DataFrame, events: pd.DataFrame, readiness: pd.DataFrame, blockers: pd.DataFrame, audit: pd.DataFrame) -> str:
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    diff = _git_lines("diff", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "empty"
    metric = dict(zip(audit["metric"], audit["value"]))
    ready_rules = int(metric.get("rule candidates ready for replay", 0))
    partial_rules = int(metric.get("rule candidates partial ready", 0))
    blocked_rules = int(metric.get("rule candidates blocked", 0))
    ready_events = int(metric.get("replay ready candidate events", 0))
    return f"""# Tech Bottleneck Research Selection Layer v2 PIT Input Reconstruction v1

## 1. Executive Summary

PIT input reconstruction completed for v2 research selection preparation. Source-date inventory evaluated {len(inventory)} layers and {features['feature_name'].nunique()} features across {features['asset_id'].nunique()} standard watchlist assets. Announcement, derived fundamental, BaoStock, and Baidu layers have dated raw inputs, but several ex-post labels still require event-date recomputation before replay.

Rule readiness: ready {ready_rules}, partial {partial_rules}, blocked {blocked_rules}. Replay-ready candidate event rows: {ready_events}. This output prepares inputs only; it does not run replay and does not create automated execution prompts. Formal strategy files were not edited; if untracked, git cannot fully prove historical state from diff alone.

## 2. Input Files

- v2 design outputs
- standard watchlist admission events
- announcement fulltext evidence rows
- derived fundamental feature rows
- BaoStock raw and structured valuation rows
- Baidu valuation validation rows and cache dates

## 3. Source Date Inventory

Announcement uses `announcement_date` and `as_of_date`. Fundamental uses `financial_as_of_date`, `announcement_date`, and `as_of_date`. BaoStock uses `baostock_date`. Baidu uses cached valuation dates. Consolidated snapshot and dashboard readonly package are not PIT sources. Forward return is outcome-only.

## 4. Feature Availability by Asset

Feature rows are marked as `pit_available`, `pit_unavailable_after_admission`, `date_missing`, `source_missing`, `snapshot_only`, or `outcome_only`. Only rows with `usable_date <= first_admission_date` are marked PIT available.

## 5. Event-level PIT Readiness

The event matrix records which source families are ready per first admission event and lists blocking features. Snapshot-derived fields are never promoted to PIT inputs.

## 6. Rule Candidate Readiness

`v2_baseline_plus_fundamental_quality`, announcement review queues, valuation context filters, cross-source validation warnings, and high-quality review candidates were evaluated against source-date availability. Partial readiness means raw dated inputs exist but event-date labels still need recomputation.

## 7. PIT Replay Blockers

Main blockers are source rows that occur after first admission, snapshot-only fields, outcome-only fields, and labels that must be recomputed by event date. Consolidated snapshot is not a PIT source, dashboard pack is not a PIT source, and forward return is not a feature.

## 8. Recommended Next Step

If partial ready rows are sufficient for a constrained replay, proceed to `tech_bottleneck_research_selection_layer_v2_pit_replay_v1`. If stricter label availability is required first, run `tech_bottleneck_source_availability_date_backfill_v1` and recompute event-date labels.

## 9. What This Reconstruction Does Not Do

- no automated execution prompt
- no Top5 change
- no formal strategy change
- no trigger / holding / exit study
- no evidence multiplier
- no forward return filter
- no ex-post grouping as PIT replay

## 10. Appendix

Generated files:
- pit_source_date_inventory.csv
- pit_feature_availability_by_asset.csv
- pit_feature_availability_by_event.csv
- pit_rule_candidate_readiness.csv
- pit_replay_ready_candidate_events.csv
- pit_replay_blocker_report.csv
- pit_input_reconstruction_quality_audit.csv
- research_selection_layer_v2_pit_input_reconstruction_v1.md

Formal strategy git status:
```text
{status}
```

Formal strategy git diff:
```text
{diff}
```

Key assumptions: latest ex-post labels are not reused as historical labels unless dated source rows support event-date reconstruction. Uncertainties: event-date valuation context and cross-source validation labels should be recomputed in the replay step.
"""


def write_outputs() -> dict[str, pd.DataFrame]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    inputs = load_inputs()
    inventory = build_source_date_inventory(inputs)
    features = build_feature_availability_by_asset(inputs)
    events = build_event_availability(features)
    readiness, ready = build_rule_candidate_readiness(features, events, inputs["rule_candidates"])
    blockers = build_blocker_report(features, readiness)
    audit = build_quality_audit(inventory, features, events, readiness, ready)

    inventory.to_csv(OUTPUT_DIR / "pit_source_date_inventory.csv", index=False)
    features.to_csv(OUTPUT_DIR / "pit_feature_availability_by_asset.csv", index=False)
    events.to_csv(OUTPUT_DIR / "pit_feature_availability_by_event.csv", index=False)
    readiness.to_csv(OUTPUT_DIR / "pit_rule_candidate_readiness.csv", index=False)
    ready.to_csv(OUTPUT_DIR / "pit_replay_ready_candidate_events.csv", index=False)
    blockers.to_csv(OUTPUT_DIR / "pit_replay_blocker_report.csv", index=False)
    audit.to_csv(OUTPUT_DIR / "pit_input_reconstruction_quality_audit.csv", index=False)
    (OUTPUT_DIR / "research_selection_layer_v2_pit_input_reconstruction_v1.md").write_text(
        render_report(inventory, features, events, readiness, blockers, audit),
        encoding="utf-8",
    )
    hit_count = _count_output_hits(OUTPUT_DIR)
    audit.loc[audit["metric"].eq("trading language hit count"), "value"] = hit_count
    audit.to_csv(OUTPUT_DIR / "pit_input_reconstruction_quality_audit.csv", index=False)
    return {
        "inventory": inventory,
        "features": features,
        "events": events,
        "readiness": readiness,
        "ready": ready,
        "blockers": blockers,
        "audit": audit,
    }


def main() -> pd.DataFrame:
    outputs = write_outputs()
    audit = outputs["audit"]
    print(audit.to_string(index=False))
    return audit


if __name__ == "__main__":
    main()
