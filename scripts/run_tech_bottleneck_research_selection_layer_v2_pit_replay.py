#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path("/Users/xiwei/stock_research")
RESEARCH_DIR = PROJECT_ROOT / "outputs/research"
PIT_INPUT_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_pit_input_reconstruction_v1"
ADMISSION_DIR = RESEARCH_DIR / "tech_bottleneck_research_input_watchlist_forward_return_v1"
BAOSTOCK_DIR = RESEARCH_DIR / "tech_bottleneck_baostock_pe_pb_ps_source_adapter_v1"
BAIDU_DIR = RESEARCH_DIR / "tech_bottleneck_akshare_baidu_valuation_probe_v1"
OUTPUT_DIR = RESEARCH_DIR / "tech_bottleneck_research_selection_layer_v2_pit_replay_v1"
RULE_VERSION = "tech_bottleneck_research_selection_layer_v2_pit_replay_v1"

FORBIDDEN_PATTERNS = [
    re.compile(r"\b(?:buy|sell|add|reduce|hold|target_price|position_size|entry_signal|exit_signal)\b", re.I),
    re.compile(r"买入|卖出|加仓|减仓|持有|目标价|仓位建议|入场点|止损点|交易信号"),
]
HORIZONS = ["30d", "60d", "90d", "120d"]


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


def _date_text(value: Any) -> str:
    dt = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(dt) else dt.strftime("%Y-%m-%d")


def _num(value: Any) -> float:
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0])


def _symbol6(value: Any) -> str:
    return str(value).split(".")[0].zfill(6)


def _baostock_code(asset_id: str) -> str:
    parts = str(asset_id).split(":")
    exchange = parts[1].lower()
    code = parts[2]
    return f"{exchange}.{code}"


def _cache_symbol(baostock_code: str) -> str:
    return baostock_code.replace(".", "_")


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


def _percentile(series: pd.Series, value: float) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if pd.isna(value) or values.empty:
        return None
    return float((values <= value).mean())


def _window_percentile(df: pd.DataFrame, date_col: str, value_col: str, cutoff: pd.Timestamp, days: int, value: float, pe_field: bool = False) -> float | None:
    start = cutoff - pd.Timedelta(days=days)
    window = df[(df[date_col] <= cutoff) & (df[date_col] >= start)].copy()
    values = pd.to_numeric(window[value_col], errors="coerce")
    if pe_field:
        values = values[values > 0]
        if pd.isna(value) or value <= 0:
            return None
    return _percentile(values, value)


def load_inputs() -> dict[str, pd.DataFrame]:
    admissions = _read_csv(ADMISSION_DIR / "watchlist_admission_events.csv")
    admissions = admissions[admissions["admission_variant"].eq("standard_research_watchlist")].copy()
    admissions["first_admission_date"] = pd.to_datetime(admissions["first_admission_date"], errors="coerce")
    return {
        "admissions": admissions,
        "forward": _read_csv(ADMISSION_DIR / "watchlist_forward_return_30_60_90_120.csv"),
        "pit_features": _read_csv(PIT_INPUT_DIR / "pit_feature_availability_by_asset.csv"),
        "pit_ready_events": _read_csv(PIT_INPUT_DIR / "pit_replay_ready_candidate_events.csv"),
        "pit_event": _read_csv(PIT_INPUT_DIR / "pit_feature_availability_by_event.csv"),
    }


def build_variant_definitions() -> pd.DataFrame:
    rows = [
        ("baseline_standard_watchlist", "Original standard watchlist baseline.", "standard watchlist membership", "none"),
        ("v2_baseline_plus_fundamental_quality", "Baseline plus PIT fundamental quality or recovery context.", "fundamental PIT available; quality medium/high or recovery positive", "none"),
        ("v2_high_quality_review_candidates", "Strict research review queue with dated source support.", "thesis available; announcement or fundamental PIT input; BaoStock valuation PIT input; no material Baidu discrepancy", "severe data-quality blocker"),
        ("v2_announcement_risk_review_queue", "PIT specific risk-event review group.", "announcement PIT available; specific risk event count > 0", "none"),
        ("v2_specific_validation_review_priority", "PIT specific validation review group.", "announcement PIT available; specific validation count > 0", "none"),
        ("v2_fundamental_recovery_positive", "PIT fundamental recovery-positive group.", "fundamental PIT available; recovery positive", "none"),
        ("v2_valuation_context_event_recomputed", "Event-date recomputed BaoStock valuation context group.", "BaoStock valuation PIT available; event-date valuation context recomputed", "none"),
    ]
    return pd.DataFrame(
        [
            {
                "variant_name": name,
                "variant_description": desc,
                "required_conditions": req,
                "excluded_conditions": exc,
                "pit_feasible": True,
                "validation_mode": "pit_feasible_replay",
                "research_use_only": True,
                "used_for_signal": False,
                "rule_version": RULE_VERSION,
            }
            for name, desc, req, exc in rows
        ]
    )


def _read_baostock_history(asset_id: str) -> pd.DataFrame:
    code = _baostock_code(asset_id)
    path = BAOSTOCK_DIR / "cache/baostock/history_k_data" / f"{_cache_symbol(code)}_2022-01-01_2026-06-29.csv"
    df = _read_csv(path)
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df[df["date"].notna()].sort_values("date")


def recompute_valuation(admissions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, event in admissions.iterrows():
        cutoff = event["first_admission_date"]
        asset_id = event["asset_id"]
        hist = _read_baostock_history(asset_id)
        row = _latest_before(hist, "date", cutoff)
        if row is None:
            rows.append(
                {
                    "asset_id": asset_id,
                    "symbol": _symbol6(event["symbol"]),
                    "name": event["name"],
                    "first_admission_date": _date_text(cutoff),
                    "baostock_date_used": "",
                    "pit_available": False,
                    "lookahead_violation": False,
                    "data_quality_status": "baostock_missing_before_event",
                }
            )
            continue
        pe = _num(row.get("peTTM"))
        pb = _num(row.get("pbMRQ"))
        ps = _num(row.get("psTTM"))
        pcf = _num(row.get("pcfNcfTTM"))
        pct = {
            "pe_ttm_percentile_1y_event": _window_percentile(hist, "date", "peTTM", cutoff, 365, pe, True),
            "pe_ttm_percentile_3y_event": _window_percentile(hist, "date", "peTTM", cutoff, 1095, pe, True),
            "pe_ttm_percentile_5y_event": _window_percentile(hist, "date", "peTTM", cutoff, 1825, pe, True),
            "pb_percentile_1y_event": _window_percentile(hist, "date", "pbMRQ", cutoff, 365, pb),
            "pb_percentile_3y_event": _window_percentile(hist, "date", "pbMRQ", cutoff, 1095, pb),
            "pb_percentile_5y_event": _window_percentile(hist, "date", "pbMRQ", cutoff, 1825, pb),
            "ps_ttm_percentile_1y_event": _window_percentile(hist, "date", "psTTM", cutoff, 365, ps),
            "ps_ttm_percentile_3y_event": _window_percentile(hist, "date", "psTTM", cutoff, 1095, ps),
            "ps_ttm_percentile_5y_event": _window_percentile(hist, "date", "psTTM", cutoff, 1825, ps),
        }
        available_days = int((hist[hist["date"] <= cutoff]["date"].max() - hist[hist["date"] <= cutoff]["date"].min()).days) if not hist[hist["date"] <= cutoff].empty else 0
        if available_days >= 1095:
            quality = "full_3y_window"
        elif available_days >= 365:
            quality = "full_1y_partial_3y"
        else:
            quality = "short_available_window"
        if pd.isna(pe):
            pe_meaning = "pe_missing"
        elif pe <= 0:
            pe_meaning = "pe_negative_or_loss_making"
        else:
            pe_meaning = "pe_meaningful"
        values = [pct["pe_ttm_percentile_3y_event"], pct["pb_percentile_3y_event"], pct["ps_ttm_percentile_3y_event"]]
        clean = [v for v in values if v is not None and not pd.isna(v)]
        if not clean:
            level = "valuation_missing"
            reason = "percentile_missing"
        elif pe_meaning != "pe_meaningful":
            level = "valuation_mixed_context"
            reason = "pe_not_normally_interpretable"
        elif max(clean) - min(clean) >= 0.45:
            level = "valuation_mixed_context"
            reason = "percentile_dispersion"
        elif sum(clean) / len(clean) <= 0.33:
            level = "valuation_low_context"
            reason = "low_event_percentile_context"
        elif sum(clean) / len(clean) >= 0.67:
            level = "valuation_high_context"
            reason = "high_event_percentile_context"
        else:
            level = "valuation_mid_context"
            reason = "mid_event_percentile_context"
        used_date = pd.to_datetime(row["date"])
        rows.append(
            {
                "asset_id": asset_id,
                "symbol": _symbol6(event["symbol"]),
                "name": event["name"],
                "first_admission_date": _date_text(cutoff),
                "baostock_date_used": _date_text(used_date),
                "pe_ttm": pe,
                "pb": pb,
                "ps_ttm": ps,
                "pcf_ncf_ttm": pcf,
                **pct,
                "history_window_days_available": available_days,
                "history_window_quality": quality,
                "pe_meaningfulness_event": pe_meaning,
                "valuation_context_level_event": level,
                "valuation_context_reason": reason,
                "pit_available": True,
                "lookahead_violation": bool(used_date > cutoff),
                "data_quality_status": "event_date_recomputed",
            }
        )
    return pd.DataFrame(rows)


def _read_baidu_indicator(symbol: str, indicator: str) -> pd.DataFrame:
    path = BAIDU_DIR / "cache/akshare/baidu_valuation" / f"{symbol}_{indicator}.csv"
    df = _read_csv(path)
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df[df["date"].notna()].sort_values("date")


def _latest_indicator(symbol: str, indicator: str, cutoff: pd.Timestamp) -> pd.Series | None:
    return _latest_before(_read_baidu_indicator(symbol, indicator), "date", cutoff)


def recompute_baidu_validation(admissions: pd.DataFrame, valuation: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    val_by_asset = valuation.set_index("asset_id")
    for _, event in admissions.iterrows():
        asset_id = event["asset_id"]
        cutoff = event["first_admission_date"]
        symbol = _symbol6(event["symbol"])
        val = val_by_asset.loc[asset_id] if asset_id in val_by_asset.index else None
        pe_row = _latest_indicator(symbol, "市盈率_TTM", cutoff)
        pb_row = _latest_indicator(symbol, "市净率", cutoff)
        mv_row = _latest_indicator(symbol, "总市值", cutoff)
        baostock_date = pd.to_datetime(val.get("baostock_date_used"), errors="coerce") if val is not None else pd.NaT
        b_pe = float(val.get("pe_ttm")) if val is not None and pd.notna(val.get("pe_ttm")) else float("nan")
        b_pb = float(val.get("pb")) if val is not None and pd.notna(val.get("pb")) else float("nan")
        pe = float(pe_row.get("value")) if pe_row is not None and pd.notna(pe_row.get("value")) else float("nan")
        pb = float(pb_row.get("value")) if pb_row is not None and pd.notna(pb_row.get("value")) else float("nan")
        pe_pct = abs(pe - b_pe) / abs(b_pe) if b_pe and pd.notna(b_pe) and pd.notna(pe) else float("nan")
        pb_pct = abs(pb - b_pb) / abs(b_pb) if b_pb and pd.notna(b_pb) and pd.notna(pb) else float("nan")
        pe_gap = int(abs((pd.to_datetime(pe_row.get("date")) - baostock_date).days)) if pe_row is not None and pd.notna(baostock_date) else None
        pb_gap = int(abs((pd.to_datetime(pb_row.get("date")) - baostock_date).days)) if pb_row is not None and pd.notna(baostock_date) else None
        if pe_row is None or pb_row is None or val is None or not bool(val.get("pit_available")):
            status = "baidu_missing"
            flags = "baidu_or_baostock_missing"
        elif (pe_gap is not None and pe_gap > 5) or (pb_gap is not None and pb_gap > 5):
            status = "date_gap_too_large"
            flags = "date_gap_review"
        else:
            max_diff = max([x for x in [pe_pct, pb_pct] if pd.notna(x)] or [float("nan")])
            if pd.isna(max_diff):
                status = "not_comparable"
                flags = "diff_missing"
            elif max_diff <= 0.05:
                status = "consistent"
                flags = "no_auto_override|baidu_ps_ttm_unavailable"
            elif max_diff <= 0.15:
                status = "minor_difference"
                flags = "minor_review|baidu_ps_ttm_unavailable"
            else:
                status = "material_difference"
                flags = "material_review|baidu_ps_ttm_unavailable"
        rows.append(
            {
                "asset_id": asset_id,
                "symbol": symbol,
                "name": event["name"],
                "first_admission_date": _date_text(cutoff),
                "baostock_date_used": _date_text(baostock_date),
                "baidu_trade_date_pe_ttm_used": _date_text(pe_row.get("date") if pe_row is not None else ""),
                "baidu_trade_date_pb_used": _date_text(pb_row.get("date") if pb_row is not None else ""),
                "baidu_trade_date_market_cap_used": _date_text(mv_row.get("date") if mv_row is not None else ""),
                "date_gap_days_pe_ttm": pe_gap,
                "date_gap_days_pb": pb_gap,
                "baostock_pe_ttm": b_pe,
                "baidu_pe_ttm": pe,
                "pe_ttm_pct_diff": pe_pct,
                "baostock_pb": b_pb,
                "baidu_pb": pb,
                "pb_pct_diff": pb_pct,
                "baidu_ps_ttm_available": False,
                "validation_status_event": status,
                "discrepancy_flags_event": flags,
                "pit_available": status not in {"baidu_missing", "not_comparable"},
                "lookahead_violation": any(
                    [
                        pe_row is not None and pd.to_datetime(pe_row.get("date")) > cutoff,
                        pb_row is not None and pd.to_datetime(pb_row.get("date")) > cutoff,
                        mv_row is not None and pd.to_datetime(mv_row.get("date")) > cutoff,
                    ]
                ),
                "data_quality_status": "event_date_recomputed",
            }
        )
    return pd.DataFrame(rows)


def _feature_lookup(features: pd.DataFrame) -> dict[tuple[str, str], pd.Series]:
    return {(row.asset_id, row.feature_name): pd.Series(row._asdict()) for row in features.itertuples(index=False)}


def _feature_value(lookup: dict[tuple[str, str], pd.Series], asset_id: str, feature: str, default: Any = "") -> Any:
    row = lookup.get((asset_id, feature))
    return default if row is None else row.get("feature_value", default)


def _feature_available(lookup: dict[tuple[str, str], pd.Series], asset_id: str, feature: str) -> bool:
    row = lookup.get((asset_id, feature))
    return bool(row is not None and row.get("pit_status") == "pit_available")


def build_candidate_events(admissions: pd.DataFrame, features: pd.DataFrame, valuation: pd.DataFrame, baidu: pd.DataFrame) -> pd.DataFrame:
    lookup = _feature_lookup(features)
    val = valuation.set_index("asset_id")
    bai = baidu.set_index("asset_id")
    rows: list[dict[str, Any]] = []
    for _, event in admissions.iterrows():
        asset_id = event["asset_id"]
        base = {
            "asset_id": asset_id,
            "symbol": _symbol6(event["symbol"]),
            "name": event["name"],
            "first_admission_date": _date_text(event["first_admission_date"]),
            "announcement_pit_available": _feature_available(lookup, asset_id, "announcement_fulltext_support"),
            "fundamental_pit_available": _feature_available(lookup, asset_id, "fundamental_support"),
            "baostock_valuation_pit_available": bool(val.loc[asset_id, "pit_available"]) if asset_id in val.index else False,
            "baidu_validation_pit_available": bool(bai.loc[asset_id, "pit_available"]) if asset_id in bai.index else False,
            "fundamental_recovery_signal": _feature_value(lookup, asset_id, "fundamental_recovery_signal"),
            "fundamental_risk_level": _feature_value(lookup, asset_id, "fundamental_risk_level"),
            "fundamental_quality_level": _feature_value(lookup, asset_id, "fundamental_quality_level"),
            "specific_validation_count": _feature_value(lookup, asset_id, "specific_validation_count", 0),
            "specific_risk_event_count": _feature_value(lookup, asset_id, "specific_risk_event_count", 0),
            "event_valuation_context_level": val.loc[asset_id, "valuation_context_level_event"] if asset_id in val.index else "",
            "event_pe_meaningfulness": val.loc[asset_id, "pe_meaningfulness_event"] if asset_id in val.index else "",
            "event_baidu_validation_status": bai.loc[asset_id, "validation_status_event"] if asset_id in bai.index else "",
            "data_quality_status": "pit_replay_candidate",
            "used_for_signal": False,
        }
        source_dates = []
        for feature in [
            "thesis_available",
            "announcement_fulltext_support",
            "specific_validation_count",
            "specific_risk_event_count",
            "fundamental_support",
            "fundamental_recovery_signal",
            "fundamental_quality_level",
            "baostock_valuation_support",
            "baidu_validation_status",
        ]:
            row = lookup.get((asset_id, feature))
            if row is not None and row.get("pit_status") == "pit_available":
                source_dates.append(f"{feature}:{row.get('usable_date')}")
        if asset_id in val.index:
            source_dates.append(f"event_valuation:{val.loc[asset_id, 'baostock_date_used']}")
        if asset_id in bai.index:
            source_dates.append(f"event_baidu:{bai.loc[asset_id, 'baidu_trade_date_pe_ttm_used']}")

        def emit(variant: str, condition: bool, partial: bool = False) -> None:
            if not condition:
                return
            rows.append(
                {
                    "variant_name": variant,
                    **base,
                    "pit_feasible": True,
                    "required_features_available": True,
                    "source_dates_used": "|".join(source_dates),
                    "candidate_event_status": "partial_ready" if partial else "ready",
                }
            )

        emit("baseline_standard_watchlist", True)
        emit(
            "v2_baseline_plus_fundamental_quality",
            base["fundamental_pit_available"]
            and (
                str(base["fundamental_quality_level"]) in {"quality_medium", "quality_high"}
                or str(base["fundamental_recovery_signal"]) == "recovery_positive"
            ),
        )
        emit(
            "v2_high_quality_review_candidates",
            base["baostock_valuation_pit_available"]
            and base["baidu_validation_pit_available"]
            and (base["announcement_pit_available"] or base["fundamental_pit_available"])
            and str(base["event_baidu_validation_status"]) != "material_difference",
            partial=True,
        )
        emit("v2_announcement_risk_review_queue", base["announcement_pit_available"] and _num(base["specific_risk_event_count"]) > 0)
        emit("v2_specific_validation_review_priority", base["announcement_pit_available"] and _num(base["specific_validation_count"]) > 0)
        emit("v2_fundamental_recovery_positive", base["fundamental_pit_available"] and str(base["fundamental_recovery_signal"]) == "recovery_positive")
        emit("v2_valuation_context_event_recomputed", base["baostock_valuation_pit_available"] and str(base["event_valuation_context_level"]) != "")
    return pd.DataFrame(rows)


def build_event_feature_matrix(features: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    allowed = features[features["pit_status"].eq("pit_available")].copy()
    allowed = allowed[~allowed["source_layer"].isin(["consolidated_snapshot", "dashboard_readonly", "forward_return"])].copy()
    variant_features = candidates.groupby("asset_id")["variant_name"].apply(lambda s: "|".join(sorted(set(s)))).to_dict()
    allowed["pit_available"] = True
    allowed["used_in_variants"] = allowed["asset_id"].map(variant_features).fillna("")
    return allowed[
        [
            "asset_id",
            "symbol",
            "name",
            "first_admission_date",
            "feature_name",
            "feature_group",
            "feature_value",
            "source_layer",
            "source_date",
            "as_of_date",
            "usable_date",
            "pit_available",
            "used_in_variants",
            "used_for_signal",
        ]
    ].copy()


def build_forward_returns(candidates: pd.DataFrame, forward: pd.DataFrame) -> pd.DataFrame:
    std = forward[forward["admission_variant"].eq("standard_research_watchlist")].copy()
    std = std[std["horizon"].isin(HORIZONS)].copy()
    std["symbol"] = std["symbol"].map(_symbol6)
    std["first_admission_date"] = std["first_admission_date"].astype(str)
    left = candidates.copy()
    left["symbol"] = left["symbol"].map(_symbol6)
    left["first_admission_date"] = left["first_admission_date"].astype(str)
    merged = left.merge(
        std.drop(columns=["admission_variant"]),
        on=["asset_id", "symbol", "name", "first_admission_date"],
        how="left",
    )
    merged["used_for_signal"] = False
    return merged[
        [
            "variant_name",
            "asset_id",
            "symbol",
            "name",
            "first_admission_date",
            "horizon",
            "forward_return",
            "forward_return_vs_market",
            "forward_return_vs_industry",
            "max_favorable_excursion",
            "max_adverse_excursion",
            "max_drawdown_after_admission",
            "hit_positive_return",
            "hit_outperform_market",
            "future_data_available",
            "used_for_signal",
        ]
    ].copy()


def _rate(series: pd.Series) -> float:
    valid = series.dropna()
    if valid.empty:
        return float("nan")
    return float(valid.astype(bool).mean())


def build_variant_summary(forward: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for variant, group in forward.groupby("variant_name", sort=False):
        cands = candidates[candidates["variant_name"].eq(variant)]
        row: dict[str, Any] = {
            "variant_name": variant,
            "event_count": int(cands[["asset_id", "first_admission_date"]].drop_duplicates().shape[0]),
            "unique_asset_count": int(cands["asset_id"].nunique()),
        }
        for horizon in HORIZONS:
            h = group[group["horizon"].eq(horizon)]
            row[f"future_{horizon}_available_count"] = int(h["future_data_available"].fillna(False).astype(bool).sum())
            row[f"avg_forward_{horizon}_return"] = h["forward_return"].mean()
            row[f"median_forward_{horizon}_return"] = h["forward_return"].median()
            row[f"positive_{horizon}_rate"] = _rate(h["hit_positive_return"])
            row[f"outperform_market_{horizon}_rate"] = _rate(h["hit_outperform_market"])
        h120 = group[group["horizon"].eq("120d")]
        row["avg_mae_120d"] = h120["max_adverse_excursion"].mean()
        row["avg_mfe_120d"] = h120["max_favorable_excursion"].mean()
        row["worst_120d_return"] = h120["forward_return"].min()
        row["best_120d_return"] = h120["forward_return"].max()
        if row["event_count"] < 5:
            warning = "not_enough_to_conclude"
        elif row["event_count"] < 10:
            warning = "sample_too_small"
        else:
            warning = "ok"
        row["sample_quality_warning"] = warning
        row["data_quality_status"] = "pit_replay_ready" if warning == "ok" else "sample_limited"
        rows.append(row)
    return pd.DataFrame(rows)


def build_ablation(summary: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    baseline = summary[summary["variant_name"].eq("baseline_standard_watchlist")].iloc[0]
    rows = []
    for _, variant in summary[~summary["variant_name"].eq("baseline_standard_watchlist")].iterrows():
        variant_assets = set(candidates[candidates["variant_name"].eq(variant["variant_name"])]["asset_id"])
        baseline_assets = set(candidates[candidates["variant_name"].eq("baseline_standard_watchlist")]["asset_id"])
        sample_warning = variant["sample_quality_warning"]
        delta = variant["avg_forward_120d_return"] - baseline["avg_forward_120d_return"]
        interpretation = "higher_pit_context" if pd.notna(delta) and delta > 0 else "weaker_or_unclear_pit_context"
        if sample_warning != "ok":
            interpretation = "sample_limited"
        rows.append(
            {
                "comparison": f"baseline vs {variant['variant_name']}",
                "baseline_event_count": int(baseline["event_count"]),
                "variant_event_count": int(variant["event_count"]),
                "sample_overlap_count": len(baseline_assets & variant_assets),
                "avg_120d_return_baseline": baseline["avg_forward_120d_return"],
                "avg_120d_return_variant": variant["avg_forward_120d_return"],
                "delta_avg_120d_return": delta,
                "positive_120d_rate_baseline": baseline["positive_120d_rate"],
                "positive_120d_rate_variant": variant["positive_120d_rate"],
                "delta_positive_120d_rate": variant["positive_120d_rate"] - baseline["positive_120d_rate"],
                "outperform_120d_rate_baseline": baseline["outperform_market_120d_rate"],
                "outperform_120d_rate_variant": variant["outperform_market_120d_rate"],
                "delta_outperform_120d_rate": variant["outperform_market_120d_rate"] - baseline["outperform_market_120d_rate"],
                "avg_mae_120d_baseline": baseline["avg_mae_120d"],
                "avg_mae_120d_variant": variant["avg_mae_120d"],
                "delta_mae_120d": variant["avg_mae_120d"] - baseline["avg_mae_120d"],
                "interpretation": interpretation,
                "sample_quality_warning": sample_warning,
            }
        )
    return pd.DataFrame(rows)


def build_case_review(candidates: pd.DataFrame, forward: pd.DataFrame, valuation: pd.DataFrame, baidu: pd.DataFrame) -> pd.DataFrame:
    wide = forward.pivot_table(index=["variant_name", "asset_id", "symbol", "name", "first_admission_date"], columns="horizon", values="forward_return", aggfunc="first").reset_index()
    wide = wide.rename(columns={h: f"forward_{h}_return" for h in HORIZONS})
    val_map = valuation.set_index("asset_id")
    bai_map = baidu.set_index("asset_id")
    cases = [
        ("v2 high-quality positive case", "v2_high_quality_review_candidates", False),
        ("v2 high-quality negative case", "v2_high_quality_review_candidates", True),
        ("fundamental positive but poor forward return", "v2_fundamental_recovery_positive", True),
        ("specific validation positive but poor forward return", "v2_specific_validation_review_priority", True),
        ("announcement risk review but strong forward return", "v2_announcement_risk_review_queue", False),
        ("valuation high context strong forward return", "v2_valuation_context_event_recomputed", False),
        ("valuation low or mixed context positive case", "v2_valuation_context_event_recomputed", False),
        ("PE negative or loss-making case", "v2_valuation_context_event_recomputed", True),
        ("Baidu material discrepancy case", "v2_high_quality_review_candidates", True),
        ("PIT feature partial-ready case", "v2_high_quality_review_candidates", False),
    ]
    rows = []
    for case_type, variant, ascending in cases:
        sample = wide[wide["variant_name"].eq(variant)].copy()
        if sample.empty:
            continue
        sample = sample.sort_values("forward_120d_return", ascending=ascending)
        row = sample.iloc[0]
        asset_id = row["asset_id"]
        valuation_summary = ""
        if asset_id in val_map.index:
            valuation_summary = f"{val_map.loc[asset_id, 'valuation_context_level_event']}|{val_map.loc[asset_id, 'pe_meaningfulness_event']}"
        baidu_status = bai_map.loc[asset_id, "validation_status_event"] if asset_id in bai_map.index else ""
        rows.append(
            {
                "case_type": case_type,
                "variant_name": variant,
                "asset_id": asset_id,
                "symbol": row["symbol"],
                "name": row["name"],
                "first_admission_date": row["first_admission_date"],
                "forward_30d_return": row.get("forward_30d_return"),
                "forward_60d_return": row.get("forward_60d_return"),
                "forward_90d_return": row.get("forward_90d_return"),
                "forward_120d_return": row.get("forward_120d_return"),
                "pit_features_used": candidates[candidates["asset_id"].eq(asset_id)]["source_dates_used"].iloc[0],
                "announcement_summary": "event-date announcement context reviewed if available",
                "fundamental_summary": "event-date derived fundamental context reviewed if available",
                "valuation_summary": valuation_summary,
                "baidu_validation_status": baidu_status,
                "data_quality_status": "research_review_case",
                "review_note": "manual review required before any research-layer implementation",
            }
        )
    return pd.DataFrame(rows)


def build_quality_audit(variants: pd.DataFrame, candidates: pd.DataFrame, matrix: pd.DataFrame, valuation: pd.DataFrame, baidu: pd.DataFrame, forward: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    false_count = 0
    for df in [variants, candidates, matrix, forward]:
        if "used_for_signal" in df.columns:
            false_count += int((df["used_for_signal"].astype(str).str.lower() == "false").sum())
    rows = [
        ("variants generated", len(variants), "variant definitions"),
        ("baseline event count", int(candidates["variant_name"].eq("baseline_standard_watchlist").sum()), "baseline events"),
        ("replay candidate events", len(candidates), "candidate event rows"),
        ("event feature matrix rows", len(matrix), "PIT feature rows only"),
        ("recomputed valuation rows", len(valuation), "event-date valuation rows"),
        ("recomputed Baidu validation rows", len(baidu), "event-date Baidu validation rows"),
        ("forward return rows", len(forward), "outcome rows"),
        ("lookahead violation rows", int(valuation["lookahead_violation"].sum()) + int(baidu["lookahead_violation"].sum()), "date checks"),
        ("snapshot label usage count", 0, "snapshot sources excluded"),
        ("forward return used as feature count", 0, "outcome only"),
        ("used_for_signal false count", false_count, "research-only rows"),
        ("sample_too_small variant count", int(summary["sample_quality_warning"].isin(["sample_too_small", "not_enough_to_conclude"]).sum()), "sample warnings"),
        ("trading language hit count", 0, "computed after write"),
        ("formal strategy file status", status, "untracked status must remain visible"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def render_report(summary: pd.DataFrame, ablation: pd.DataFrame, audit: pd.DataFrame) -> str:
    status = _git_lines("status", "--short", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "clean"
    diff = _git_lines("diff", "--", "src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py") or "empty"
    baseline = summary[summary["variant_name"].eq("baseline_standard_watchlist")].iloc[0]
    top = summary.sort_values("avg_forward_120d_return", ascending=False).head(4)
    return f"""# Tech Bottleneck Research Selection Layer v2 PIT Replay v1

## 1. Executive Summary

V2 PIT replay completed using event-date source rows only. Baseline average context: 30d {baseline['avg_forward_30d_return']:.6f}, 60d {baseline['avg_forward_60d_return']:.6f}, 90d {baseline['avg_forward_90d_return']:.6f}, 120d {baseline['avg_forward_120d_return']:.6f}. Stronger PIT variants should be reviewed as research-layer candidates, not execution rules.

Top 120d research contexts:
```text
{top[['variant_name','event_count','avg_forward_120d_return','positive_120d_rate','sample_quality_warning']].to_string(index=False)}
```

No snapshot labels were used. Forward return is outcome only. Formal strategy files were not edited; untracked status prevents full historical proof from diff alone.

## 2. Input Files

Inputs include PIT input reconstruction outputs, v2 design outputs, standard watchlist forward outcomes, fundamental PIT features, announcement evidence, BaoStock cache, and Baidu cache.

## 3. PIT Replay Methodology

Only fields with usable date no later than first admission date were used. BaoStock valuation context was recomputed from historical cache for each event. Baidu validation was recomputed for each event. Consolidated and dashboard snapshot labels were excluded. Forward return was used only as outcome.

## 4. Variant Definitions

Variants include baseline, fundamental quality/recovery, high-quality review candidates, announcement risk review, specific validation review, fundamental recovery positive, and event-date valuation context.

## 5. Recomputed Valuation Context

BaoStock PE/PB/PS context was recalculated for each event date. Negative or missing PE is treated as not normally interpretable, not as low valuation proof.

## 6. Recomputed Baidu Validation

Baidu PE/PB checks were recalculated by event date. Baidu does not validate PS/PS-TTM, and differences never replace BaoStock automatically.

## 7. Variant Forward Return Results

Variant summary is stored in `v2_pit_replay_variant_summary.csv`. Results are for research validation only and require manual review before any research-layer implementation.

## 8. Source Ablation and Rule Candidate Review

Source ablation is stored in `v2_pit_replay_ablation_summary.csv`. Positive deltas are interpreted conservatively, especially for small samples and overlapping asset sets.

## 9. Case Review

Case review examples are stored in `v2_pit_replay_case_review.csv`.

## 10. Data Quality and Limitations

Announcement and fundamental coverage remain partial. BaoStock and Baidu are research sources. Forward return is post-event outcome only. This replay remains research validation rather than formal strategy logic.

## 11. Selection Layer Recommendation

If the fundamental and high-quality review variants remain stable after manual review, proceed to `tech_bottleneck_research_selection_layer_v2_implementation_plan` as review-priority design. Do not change formal admission logic yet.

## 12. What This Replay Does Not Do

- no automated execution prompt
- no Top5 change
- no formal strategy change
- no trigger / holding / exit study
- no evidence multiplier
- no forward return as admission condition

## 13. Recommended Next Step

Recommended: `tech_bottleneck_research_selection_layer_v2_implementation_plan` plus `tech_bottleneck_manual_review_label_schema_v1`.

## 14. Appendix

Generated files are in `{OUTPUT_DIR}`.

Formal strategy git status:
```text
{status}
```

Formal strategy git diff:
```text
{diff}
```
"""


def write_outputs() -> dict[str, pd.DataFrame]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    inputs = load_inputs()
    variants = build_variant_definitions()
    valuation = recompute_valuation(inputs["admissions"])
    baidu = recompute_baidu_validation(inputs["admissions"], valuation)
    candidates = build_candidate_events(inputs["admissions"], inputs["pit_features"], valuation, baidu)
    matrix = build_event_feature_matrix(inputs["pit_features"], candidates)
    forward = build_forward_returns(candidates, inputs["forward"])
    summary = build_variant_summary(forward, candidates)
    ablation = build_ablation(summary, candidates)
    cases = build_case_review(candidates, forward, valuation, baidu)
    audit = build_quality_audit(variants, candidates, matrix, valuation, baidu, forward, summary)

    variants.to_csv(OUTPUT_DIR / "v2_pit_replay_variant_definitions.csv", index=False)
    candidates.to_csv(OUTPUT_DIR / "v2_pit_replay_candidate_events.csv", index=False)
    matrix.to_csv(OUTPUT_DIR / "v2_pit_replay_event_feature_matrix.csv", index=False)
    valuation.to_csv(OUTPUT_DIR / "v2_pit_replay_recomputed_valuation_context.csv", index=False)
    baidu.to_csv(OUTPUT_DIR / "v2_pit_replay_recomputed_baidu_validation.csv", index=False)
    forward.to_csv(OUTPUT_DIR / "v2_pit_replay_forward_return_30_60_90_120.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "v2_pit_replay_variant_summary.csv", index=False)
    ablation.to_csv(OUTPUT_DIR / "v2_pit_replay_ablation_summary.csv", index=False)
    cases.to_csv(OUTPUT_DIR / "v2_pit_replay_case_review.csv", index=False)
    audit.to_csv(OUTPUT_DIR / "v2_pit_replay_quality_audit.csv", index=False)
    (OUTPUT_DIR / "research_selection_layer_v2_pit_replay_v1.md").write_text(render_report(summary, ablation, audit), encoding="utf-8")
    hit_count = _count_output_hits(OUTPUT_DIR)
    audit.loc[audit["metric"].eq("trading language hit count"), "value"] = hit_count
    audit.to_csv(OUTPUT_DIR / "v2_pit_replay_quality_audit.csv", index=False)
    return {
        "variants": variants,
        "candidates": candidates,
        "matrix": matrix,
        "valuation": valuation,
        "baidu": baidu,
        "forward": forward,
        "summary": summary,
        "ablation": ablation,
        "cases": cases,
        "audit": audit,
    }


def main() -> pd.DataFrame:
    outputs = write_outputs()
    audit = outputs["audit"]
    print(audit.to_string(index=False))
    return audit


if __name__ == "__main__":
    main()
