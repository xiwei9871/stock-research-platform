from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.factor_config import manual_v1_config
from stock_research.factor_pipeline import _latest_technical_factor_names
from stock_research.technical_features import TECHNICAL_FEATURE_COLUMNS
from stock_research.technical_method_validation import (
    compute_validation_features,
    load_validation_bars,
    load_validation_technical_table,
)


PROMOTION_AUDIT_COLUMNS = [
    "field_name",
    "field_type",
    "current_layer",
    "target_layer",
    "priority",
    "promotion_decision",
    "signal_type",
    "recommended_usage",
    "sample_count",
    "null_rate",
    "strongest_existing_proxy",
    "max_abs_correlation_with_proxy",
    "code_state",
    "storage_verification",
    "readiness_status",
    "next_action",
    "note",
]

WATCHLIST_READINESS_COLUMNS = [
    "field_name",
    "target_layer",
    "signal_type",
    "sample_count",
    "null_rate",
    "readiness_status",
    "reason",
]

_PROXY_MAP = {
    "amount_vs_20d": ["amount_ratio_5_20", "volume_ratio_5_20", "turnover_ratio_5_20"],
    "volatility_5d": ["volatility_20", "atr_pct_proxy"],
    "high_to_close_drawdown": ["close_position_in_day", "upper_shadow_ratio"],
    "max_drawdown_20d": ["max_drawdown_20", "volatility_20"],
    "atr_pct14": ["atr_pct_proxy", "volatility_20"],
}


def run_technical_feature_promotion_audit(
    *,
    start_date: str,
    end_date: str,
    adjust_type: str = "qfq",
    sample_size: int | None = None,
    asset_id: str | None = None,
    ts_code: str | None = None,
    feature_source: str = "technical_table",
    output_dir: str | Path,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    warnings: list[str] = []
    bars = load_validation_bars(
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        sample_size=sample_size,
        asset_id=asset_id,
        ts_code=ts_code,
        service=service,
    )
    tech_table = pd.DataFrame()
    source_used = feature_source
    if feature_source == "technical_table":
        tech_table = load_validation_technical_table(
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
            sample_size=sample_size,
            asset_id=asset_id,
            ts_code=ts_code,
            service=service,
        )
        if tech_table.empty:
            warnings.append("technical_table had no matching rows in requested window; fell back to computed_on_fly")
            source_used = "computed_on_fly"
    dataset = compute_validation_features(
        bars,
        technical_features=tech_table if source_used == "technical_table" else None,
    )
    out = Path(output_dir)
    recommendation = _load_csv(out / "technical_method_recommendation.csv", warnings, "technical_method_recommendation.csv")
    promotion_matrix = _load_csv(out / "technical_feature_promotion_matrix.csv", warnings, "technical_feature_promotion_matrix.csv")
    result = build_promotion_audit_from_frames(
        dataset=dataset,
        recommendation=recommendation,
        promotion_matrix=promotion_matrix,
        feature_source=source_used,
        warnings=warnings,
    )
    report = build_promotion_audit_report(
        promotion_audit=result["promotion_audit"],
        watchlist_readiness=result["watchlist_readiness"],
        start_date=start_date,
        end_date=end_date,
        adjust_type=adjust_type,
        feature_source=source_used,
        warnings=result["warnings"],
    )
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "promotion_audit": str(out / "technical_feature_promotion_audit.csv"),
        "watchlist_readiness": str(out / "technical_feature_watchlist_readiness.csv"),
        "report": str(out / "technical_feature_promotion_audit_report.md"),
    }
    result["promotion_audit"].to_csv(paths["promotion_audit"], index=False)
    result["watchlist_readiness"].to_csv(paths["watchlist_readiness"], index=False)
    Path(paths["report"]).write_text(report, encoding="utf-8")
    return {
        **result,
        "dataset": dataset,
        "paths": paths,
    }


def build_promotion_audit_from_frames(
    *,
    dataset: pd.DataFrame,
    recommendation: pd.DataFrame,
    promotion_matrix: pd.DataFrame,
    feature_source: str,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    warnings = list(warnings or [])
    matrix = promotion_matrix.copy()
    rec = recommendation.copy()
    if matrix.empty:
        return {
            "promotion_audit": pd.DataFrame(columns=PROMOTION_AUDIT_COLUMNS),
            "watchlist_readiness": pd.DataFrame(columns=WATCHLIST_READINESS_COLUMNS),
            "warnings": warnings + ["technical_feature_promotion_matrix.csv was not available"],
        }
    dataset = dataset.copy()
    dataset = _append_existing_factor_proxies(dataset)
    rec_map = {}
    if not rec.empty and "feature_or_method" in rec.columns:
        rec_map = _recommendation_lookup(rec)
    factor_config = manual_v1_config()
    factor_groups = set(factor_config["factor_groups"])
    technical_factor_names = set(_latest_technical_factor_names())
    atomic_features = set(TECHNICAL_FEATURE_COLUMNS)
    rows: list[dict[str, Any]] = []
    for record in matrix.to_dict("records"):
        field_name = str(record.get("field_name", ""))
        rec_row = rec_map.get(field_name, {})
        sample_count, null_rate = _dataset_stats(dataset, field_name)
        proxy_name, proxy_corr = _strongest_proxy(dataset, field_name)
        target_layer = str(record.get("target_layer", ""))
        if target_layer == "stock_technical_features_daily":
            code_state = "implemented" if field_name in atomic_features else "missing"
            storage_verification = "verified_from_table" if feature_source == "technical_table" else "backfill_pending"
        elif target_layer == "factor_daily":
            code_state = "implemented" if field_name in factor_groups and field_name in technical_factor_names else "missing"
            storage_verification = "config_and_pipeline_ready"
        else:
            code_state = "derived_only"
            storage_verification = "not_applicable"
        readiness_status, note = _readiness(
            target_layer=target_layer,
            promotion_decision=str(record.get("promotion_decision", "")),
            code_state=code_state,
            storage_verification=storage_verification,
            sample_count=sample_count,
            null_rate=null_rate,
        )
        rows.append(
            {
                "field_name": field_name,
                "field_type": str(record.get("field_type", "")),
                "current_layer": str(record.get("current_layer", "")),
                "target_layer": target_layer,
                "priority": str(record.get("priority", "")),
                "promotion_decision": str(record.get("promotion_decision", "")),
                "signal_type": str(rec_row.get("signal_type", "")),
                "recommended_usage": str(rec_row.get("recommended_usage", record.get("recommended_usage", ""))),
                "sample_count": sample_count,
                "null_rate": null_rate,
                "strongest_existing_proxy": proxy_name,
                "max_abs_correlation_with_proxy": proxy_corr,
                "code_state": code_state,
                "storage_verification": storage_verification,
                "readiness_status": readiness_status,
                "next_action": str(rec_row.get("next_action", "")),
                "note": note,
            }
        )
    audit = pd.DataFrame(rows, columns=PROMOTION_AUDIT_COLUMNS)
    watchlist = audit[audit["target_layer"].isin(["factor_daily", "stock_technical_features_daily"])].copy()
    watchlist = watchlist[
        [
            "field_name",
            "target_layer",
            "signal_type",
            "sample_count",
            "null_rate",
            "readiness_status",
            "note",
        ]
    ].rename(columns={"note": "reason"})
    return {
        "promotion_audit": audit,
        "watchlist_readiness": watchlist.reindex(columns=WATCHLIST_READINESS_COLUMNS),
        "warnings": warnings,
    }


def build_promotion_audit_report(
    *,
    promotion_audit: pd.DataFrame,
    watchlist_readiness: pd.DataFrame,
    start_date: str,
    end_date: str,
    adjust_type: str,
    feature_source: str,
    warnings: list[str],
) -> str:
    implemented_atomic = promotion_audit[
        (promotion_audit["target_layer"] == "stock_technical_features_daily")
        & (promotion_audit["code_state"] == "implemented")
    ]
    implemented_factor = promotion_audit[
        (promotion_audit["target_layer"] == "factor_daily")
        & (promotion_audit["code_state"] == "implemented")
    ]
    lines = [
        "# Technical Feature Promotion Audit",
        "",
        "## 1. Scope",
        f"start_date={start_date}, end_date={end_date}, adjust_type={adjust_type}, feature_source={feature_source}.",
        "",
        "## 2. Atomic Store Status",
        implemented_atomic[[
            "field_name",
            "storage_verification",
            "sample_count",
            "null_rate",
            "readiness_status",
        ]].to_markdown(index=False) if not implemented_atomic.empty else "No implemented atomic promotion rows.",
        "",
        "## 3. Factor Layer Status",
        implemented_factor[[
            "field_name",
            "sample_count",
            "null_rate",
            "strongest_existing_proxy",
            "max_abs_correlation_with_proxy",
            "readiness_status",
        ]].to_markdown(index=False) if not implemented_factor.empty else "No implemented factor promotion rows.",
        "",
        "## 4. Watchlist Readiness",
        watchlist_readiness.to_markdown(index=False) if not watchlist_readiness.empty else "No watchlist readiness rows.",
        "",
        "## 5. Interpretation",
        "- `backfill_pending` means code/schema are ready but the promoted atomic fields still need technical-feature backfill before table-backed verification is complete.",
        "- `ready_for_watchlist_validation` means the field is implemented and can be used in later watchlist diagnostics without changing factor weights yet.",
        "- This audit does not change manual_v1 score weights.",
    ]
    if warnings:
        lines.extend(["", "## 6. Warnings", *[f"- {warning}" for warning in warnings]])
    return "\n".join(lines) + "\n"


def _load_csv(path: Path, warnings: list[str], label: str) -> pd.DataFrame:
    if not path.exists():
        warnings.append(f"{label} was not available")
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def _recommendation_lookup(recommendation: pd.DataFrame) -> dict[str, dict[str, Any]]:
    frame = recommendation.copy()
    if frame.empty or "feature_or_method" not in frame.columns:
        return {}
    if "category" in frame.columns:
        category_priority = {
            "technical_feature": 0,
            "technical_combo": 1,
        }
        frame["_category_priority"] = frame["category"].map(category_priority).fillna(9)
        frame = frame.sort_values(["feature_or_method", "_category_priority"]).drop(columns=["_category_priority"])
    frame = frame.drop_duplicates(subset=["feature_or_method"], keep="first")
    return frame.set_index("feature_or_method").to_dict("index")


def _dataset_stats(dataset: pd.DataFrame, field_name: str) -> tuple[int, float]:
    if dataset.empty or field_name not in dataset.columns:
        return 0, 1.0
    series = pd.to_numeric(dataset[field_name], errors="coerce")
    return int(series.notna().sum()), float(series.isna().mean())


def _append_existing_factor_proxies(dataset: pd.DataFrame) -> pd.DataFrame:
    if dataset.empty:
        return dataset
    frame = dataset.copy()
    amount = pd.to_numeric(frame.get("amount"), errors="coerce")
    volume = pd.to_numeric(frame.get("volume"), errors="coerce")
    turnover = pd.to_numeric(frame.get("turnover_rate"), errors="coerce")
    high = pd.to_numeric(frame.get("high"), errors="coerce")
    low = pd.to_numeric(frame.get("low"), errors="coerce")
    close = pd.to_numeric(frame.get("close"), errors="coerce")
    open_ = pd.to_numeric(frame.get("open"), errors="coerce")
    if "amount_ratio_5_20" not in frame.columns:
        frame["amount_ratio_5_20"] = amount.rolling(5).mean() / amount.rolling(20).mean()
    if "volume_ratio_5_20" not in frame.columns:
        frame["volume_ratio_5_20"] = volume.rolling(5).mean() / volume.rolling(20).mean()
    if "turnover_ratio_5_20" not in frame.columns:
        frame["turnover_ratio_5_20"] = turnover.rolling(5).mean() / turnover.rolling(20).mean()
    if "volatility_20" not in frame.columns and "ret_1d" in frame.columns:
        frame["volatility_20"] = pd.to_numeric(frame["ret_1d"], errors="coerce").rolling(20).std()
    if "max_drawdown_20" not in frame.columns:
        frame["max_drawdown_20"] = pd.to_numeric(frame.get("max_drawdown_20d"), errors="coerce")
    if "atr_pct_proxy" not in frame.columns:
        frame["atr_pct_proxy"] = pd.to_numeric(frame.get("atr_pct14"), errors="coerce")
    if "upper_shadow_ratio" not in frame.columns:
        upper_shadow = high - pd.concat([open_, close], axis=1).max(axis=1)
        full_range = (high - low).replace(0.0, pd.NA)
        frame["upper_shadow_ratio"] = upper_shadow / full_range
    return frame


def _strongest_proxy(dataset: pd.DataFrame, field_name: str) -> tuple[str, float | None]:
    proxies = _PROXY_MAP.get(field_name, [])
    if dataset.empty or field_name not in dataset.columns or not proxies:
        return "", None
    target = pd.to_numeric(dataset[field_name], errors="coerce")
    target_clean = target.dropna()
    if len(target_clean) < 2 or float(target_clean.std()) == 0.0:
        return "", None
    best_name = ""
    best_corr: float | None = None
    for proxy in proxies:
        if proxy not in dataset.columns:
            continue
        proxy_series = pd.to_numeric(dataset[proxy], errors="coerce")
        proxy_clean = proxy_series.dropna()
        if len(proxy_clean) < 2 or float(proxy_clean.std()) == 0.0:
            continue
        corr = target.corr(proxy_series)
        if pd.isna(corr):
            continue
        abs_corr = abs(float(corr))
        if best_corr is None or abs_corr > best_corr:
            best_name = proxy
            best_corr = abs_corr
    return best_name, best_corr


def _readiness(
    *,
    target_layer: str,
    promotion_decision: str,
    code_state: str,
    storage_verification: str,
    sample_count: int,
    null_rate: float,
) -> tuple[str, str]:
    if target_layer == "derived_only":
        return "keep_derived_only", "Remain a derived downstream rule."
    if code_state != "implemented":
        return "not_ready", "Code path is not fully implemented."
    if target_layer == "stock_technical_features_daily":
        if storage_verification == "verified_from_table":
            return "ready_for_reuse", "Atomic field is implemented and table-backed."
        return "ready_for_backfill", "Schema/code are ready; run technical-feature backfill to verify table coverage."
    if target_layer == "factor_daily":
        if promotion_decision == "holdout":
            return "holdout_candidate", "Keep as a factor holdout until later diagnostics justify activation."
        if sample_count > 0 and null_rate <= 0.10:
            return "ready_for_watchlist_validation", "Implemented in factor layer and suitable for later watchlist diagnostics."
        return "not_ready", "Coverage or null-rate is too weak for next-stage use."
    return "not_ready", "No readiness rule matched."
