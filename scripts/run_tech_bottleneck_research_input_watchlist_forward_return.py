#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.tech_bottleneck_v1 import _load_prices


RESEARCH_SELECTION_DIR = Path("outputs/research/tech_bottleneck_research_selection_layer_v1")
EVIDENCE_REPLAY_DIR = Path("outputs/research/tech_bottleneck_pit_evidence_replay_neutral_missing_v1_20250101_20260629")
OUTPUT_DIR = Path("outputs/research/tech_bottleneck_research_input_watchlist_forward_return_v1")
RULE_VERSION = "tech_bottleneck_research_input_watchlist_forward_return_v1"
HORIZONS = [30, 60, 90, 120]
FORBIDDEN_TRADING_WORDS = {
    "buy",
    "sell",
    "add",
    "reduce",
    "hold",
    "target_price",
    "position_size",
    "entry_signal",
    "exit_signal",
}


def neutral_confidence(value: Any) -> float:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return 0.5
    return float(np.clip(parsed, 0.0, 1.0))


def _num(value: Any, default: float = np.nan) -> float:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(default if pd.isna(parsed) else parsed)


def _symbol(asset_id: Any) -> str:
    return str(asset_id).split(":")[-1]


def _nonempty(value: Any) -> bool:
    return pd.notna(value) and str(value).strip() not in {"", "nan", "None", "<NA>"}


def _source_id_from_path(path: Any, source_type: Any, source_date: Any, asset_id: Any) -> str:
    if _nonempty(path):
        return Path(str(path)).name
    return f"{asset_id}|{source_type}|{source_date}"


def validate_no_trading_language(frame: pd.DataFrame) -> None:
    text_columns = [column for column in frame.columns if frame[column].dtype == object]
    for column in text_columns:
        lowered = frame[column].fillna("").astype(str).str.lower()
        for word in FORBIDDEN_TRADING_WORDS:
            if lowered.str.contains(word, regex=False).any():
                raise ValueError(f"trading instruction language found in {column}: {word}")


def validate_structured_output_pit(frame: pd.DataFrame) -> None:
    trade_date = pd.to_datetime(frame["trade_date"], errors="coerce")
    source_date = pd.to_datetime(frame["source_date"], errors="coerce")
    as_of_date = pd.to_datetime(frame["as_of_date"], errors="coerce")
    violation = source_date.gt(trade_date).fillna(False) | as_of_date.gt(trade_date).fillna(False)
    if "lookahead_violation" in frame.columns:
        violation = violation | frame["lookahead_violation"].astype(bool)
    if violation.any():
        raise ValueError("lookahead violation in structured research output")


def _load_research_inputs(input_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    candidates = pd.read_csv(input_dir / "tech_bottleneck_research_candidates.csv", low_memory=False)
    low_position = pd.read_csv(input_dir / "research_selection_low_position_breakdown.csv", low_memory=False)
    risk = pd.read_csv(input_dir / "research_selection_risk_audit.csv", low_memory=False)
    for frame in [candidates, low_position, risk]:
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        frame["asset_id"] = frame["asset_id"].astype(str)
    return candidates, low_position, risk


def _load_evidence(replay_dir: Path) -> pd.DataFrame:
    path = replay_dir / "new_evidence_seed_pit_usable.csv"
    if not path.exists():
        return pd.DataFrame(
            columns=["asset_id", "field", "source_type", "source_path", "source_date", "claim", "evidence_tier", "excerpt"]
        )
    frame = pd.read_csv(path, low_memory=False)
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["source_date"] = pd.to_datetime(frame["source_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return frame


def _aggregate_evidence_events(evidence: pd.DataFrame) -> pd.DataFrame:
    if evidence.empty:
        return pd.DataFrame(columns=["asset_id", "source_type", "source_id", "source_date", "field_keys"])
    frame = evidence.copy()
    frame["source_id"] = frame.apply(
        lambda row: _source_id_from_path(row.get("source_path"), row.get("source_type"), row.get("source_date"), row.get("asset_id")),
        axis=1,
    )
    rows: list[dict[str, Any]] = []
    for keys, group in frame.groupby(["asset_id", "source_type", "source_id", "source_date"], dropna=False):
        asset_id, source_type, source_id, source_date = keys
        fields = sorted(set(group["field"].dropna().astype(str)))
        claims = [str(value) for value in group.get("claim", pd.Series(dtype="object")).dropna().head(3)]
        excerpts = [str(value)[:160] for value in group.get("excerpt", pd.Series(dtype="object")).dropna().head(1)]
        rows.append(
            {
                "asset_id": asset_id,
                "source_type": source_type,
                "source_id": source_id,
                "source_date": source_date,
                "field_keys": "|".join(fields),
                "key_thesis": "；".join(claims) if claims else "missing",
                "source_excerpt": excerpts[0] if excerpts else "",
                "evidence_tier": "|".join(sorted(set(group.get("evidence_tier", pd.Series(dtype="object")).dropna().astype(str)))),
                "source_path": "|".join(sorted(set(group.get("source_path", pd.Series(dtype="object")).dropna().astype(str)))),
            }
        )
    return pd.DataFrame(rows)


def _score_from_fields(field_keys: str, token_group: list[str], positive_score: float) -> float:
    text = str(field_keys or "").lower()
    return positive_score if any(token in text for token in token_group) else 0.0


def _source_confidence(source_type: str, tier: str) -> float:
    if "tier3" in str(tier):
        return 0.85
    if "tier2" in str(tier):
        return 0.75
    if str(source_type) == "broker_report":
        return 0.70
    return 0.55


def build_structured_outputs(
    candidates: pd.DataFrame,
    low_position: pd.DataFrame,
    risk: pd.DataFrame,
    evidence: pd.DataFrame,
) -> pd.DataFrame:
    base = candidates.merge(low_position, on=["trade_date", "asset_id"], how="left", suffixes=("", "_lp"))
    base = base.merge(risk[["trade_date", "asset_id", "risk_flags"]], on=["trade_date", "asset_id"], how="left")
    snapshot_rows = []
    for row in base.itertuples(index=False):
        trade_date = str(row.trade_date)
        asset_id = str(row.asset_id)
        stock_event_id = f"{asset_id}|research_selection_snapshot|{trade_date}"
        missing_fields = _missing_fields_from_row(row)
        snapshot_rows.append(
            {
                "trade_date": trade_date,
                "asset_id": asset_id,
                "symbol": getattr(row, "symbol", _symbol(asset_id)),
                "name": getattr(row, "name", ""),
                "stock_event_id": stock_event_id,
                "source_type": "research_selection_snapshot",
                "source_id": stock_event_id,
                "source_date": trade_date,
                "as_of_date": trade_date,
                "is_pit_valid": True,
                "lookahead_violation": False,
                "industry_bottleneck_theme": getattr(row, "industry_bottleneck_theme", ""),
                "bottleneck_theme": getattr(row, "industry_bottleneck_theme", ""),
                "key_thesis": getattr(row, "thesis_summary", "missing"),
                "evidence_tags": getattr(row, "evidence_tags", "unverified"),
                "commercial_validation_score": _num(getattr(row, "commercial_validation_score", np.nan), 0.5),
                "customer_validation_score": 0.0,
                "revenue_exposure_score": 0.0,
                "supplier_dependency_risk": 0.0,
                "policy_catalyst_score": 0.0,
                "announcement_validation_score": 0.0,
                "fundamental_recovery_score": np.nan,
                "fundamental_risk_score": _num(getattr(row, "fundamental_risk_score", np.nan), 0.0),
                "price_position_score": _num(getattr(row, "price_position_score", np.nan), np.nan),
                "valuation_position_score": _num(getattr(row, "valuation_position_score", np.nan), np.nan),
                "expectation_position_score": _num(getattr(row, "expectation_position_score", np.nan), np.nan),
                "fundamental_position_score": _num(getattr(row, "fundamental_position_score", np.nan), np.nan),
                "technical_position_score": _num(getattr(row, "technical_position_score", np.nan), np.nan),
                "low_position_score": _num(getattr(row, "low_position_score", np.nan), 0.5),
                "source_confidence": 0.5,
                "extraction_confidence": 0.5,
                "data_quality_status": getattr(row, "data_quality_status", "ok"),
                "missing_fields": missing_fields,
                "conflict_flags": "",
                "research_priority": getattr(row, "research_priority", "watch_only"),
                "risk_flags": getattr(row, "risk_flags", ""),
                "rule_version": RULE_VERSION,
            }
        )
    snapshot = pd.DataFrame(snapshot_rows)
    event_rows: list[dict[str, Any]] = []
    evidence_events = _aggregate_evidence_events(evidence)
    if not evidence_events.empty:
        for event in evidence_events.itertuples(index=False):
            candidate_days = base[
                base["asset_id"].astype(str).eq(str(event.asset_id))
                & base["trade_date"].astype(str).ge(str(event.source_date))
            ].copy()
            for row in candidate_days.itertuples(index=False):
                field_keys = str(event.field_keys or "")
                trade_date = str(row.trade_date)
                source_date = str(event.source_date)
                source_conf = _source_confidence(str(event.source_type), str(event.evidence_tier))
                customer = _score_from_fields(field_keys, ["customer", "certification", "客户", "认证"], 0.8)
                revenue = _score_from_fields(field_keys, ["revenue", "收入", "订单"], 0.75)
                supplier = _score_from_fields(field_keys, ["supplier", "concentration", "国产", "稀缺"], 0.35)
                commercial = max(customer, revenue, 0.65)
                lookahead = source_date > trade_date
                event_rows.append(
                    {
                        "trade_date": trade_date,
                        "asset_id": str(event.asset_id),
                        "symbol": getattr(row, "symbol", _symbol(event.asset_id)),
                        "name": getattr(row, "name", ""),
                        "stock_event_id": f"{event.asset_id}|{event.source_type}|{event.source_id}|{event.source_date}",
                        "source_type": event.source_type,
                        "source_id": event.source_id,
                        "source_date": source_date,
                        "as_of_date": source_date,
                        "is_pit_valid": not lookahead,
                        "lookahead_violation": lookahead,
                        "industry_bottleneck_theme": getattr(row, "industry_bottleneck_theme", ""),
                        "bottleneck_theme": getattr(row, "industry_bottleneck_theme", ""),
                        "key_thesis": getattr(event, "key_thesis", "missing"),
                        "evidence_tags": field_keys,
                        "commercial_validation_score": commercial,
                        "customer_validation_score": customer,
                        "revenue_exposure_score": revenue,
                        "supplier_dependency_risk": supplier,
                        "policy_catalyst_score": 0.0,
                        "announcement_validation_score": 0.0,
                        "fundamental_recovery_score": np.nan,
                        "fundamental_risk_score": _num(getattr(row, "fundamental_risk_score", np.nan), 0.0),
                        "price_position_score": _num(getattr(row, "price_position_score", np.nan), np.nan),
                        "valuation_position_score": _num(getattr(row, "valuation_position_score", np.nan), np.nan),
                        "expectation_position_score": _num(getattr(row, "expectation_position_score", np.nan), np.nan),
                        "fundamental_position_score": _num(getattr(row, "fundamental_position_score", np.nan), np.nan),
                        "technical_position_score": _num(getattr(row, "technical_position_score", np.nan), np.nan),
                        "low_position_score": _num(getattr(row, "low_position_score", np.nan), 0.5),
                        "source_confidence": source_conf,
                        "extraction_confidence": 0.75,
                        "data_quality_status": getattr(row, "data_quality_status", "ok"),
                        "missing_fields": _missing_fields_from_row(row),
                        "conflict_flags": "",
                        "research_priority": getattr(row, "research_priority", "watch_only"),
                        "risk_flags": getattr(row, "risk_flags", ""),
                        "rule_version": RULE_VERSION,
                    }
                )
    result = pd.concat([snapshot, pd.DataFrame(event_rows)], ignore_index=True)
    result["lookahead_violation"] = (
        pd.to_datetime(result["source_date"], errors="coerce").gt(pd.to_datetime(result["trade_date"], errors="coerce")).fillna(False)
        | pd.to_datetime(result["as_of_date"], errors="coerce").gt(pd.to_datetime(result["trade_date"], errors="coerce")).fillna(False)
    )
    result["is_pit_valid"] = ~result["lookahead_violation"]
    return result


def _missing_fields_from_row(row: Any) -> str:
    missing = []
    for field in ["valuation_position_score", "expectation_position_score", "fundamental_position_score"]:
        if pd.isna(getattr(row, field, np.nan)):
            missing.append(field)
    return "|".join(missing) if missing else ""


def build_quality_audit(structured: pd.DataFrame) -> pd.DataFrame:
    total = len(structured)
    usable = structured[
        structured["is_pit_valid"].astype(bool)
        & ~structured["lookahead_violation"].astype(bool)
        & ~structured["data_quality_status"].fillna("").astype(str).str.contains("invalid", case=False, regex=False)
    ]
    metrics = [
        ("total_structured_output_rows", total, "all structured research rows"),
        ("unique_asset_count", structured["asset_id"].nunique(), "unique assets"),
        ("unique_stock_event_count", structured["stock_event_id"].nunique(), "unique source/event identifiers"),
        ("source_type_distribution", json.dumps(structured["source_type"].value_counts().to_dict(), ensure_ascii=False), "row distribution"),
        ("pit_valid_ratio", float(structured["is_pit_valid"].mean()) if total else np.nan, "PIT-valid rows / total rows"),
        ("lookahead_violation_rows", int(structured["lookahead_violation"].sum()), "must be zero"),
        ("missing_key_thesis_ratio", float(structured["key_thesis"].fillna("").astype(str).isin(["", "missing"]).mean()), "thesis missing"),
        ("missing_commercial_validation_ratio", float(pd.to_numeric(structured["commercial_validation_score"], errors="coerce").isna().mean()), "commercial score missing"),
        ("missing_fundamental_ratio", float(pd.to_numeric(structured["fundamental_recovery_score"], errors="coerce").isna().mean()), "fundamental recovery missing"),
        ("missing_valuation_ratio", float(pd.to_numeric(structured["valuation_position_score"], errors="coerce").isna().mean()), "valuation position missing"),
        ("missing_low_position_ratio", float(pd.to_numeric(structured["low_position_score"], errors="coerce").isna().mean()), "low position missing"),
        ("extraction_confidence_distribution", json.dumps(_bucket_confidence(structured["extraction_confidence"]).value_counts().to_dict(), ensure_ascii=False), "confidence buckets"),
        ("source_confidence_distribution", json.dumps(_bucket_confidence(structured["source_confidence"]).value_counts().to_dict(), ensure_ascii=False), "confidence buckets"),
        ("conflict_flag_count", int(structured["conflict_flags"].fillna("").astype(str).ne("").sum()), "explicit conflicts"),
        ("degraded_rows", int(structured["data_quality_status"].fillna("").astype(str).str.contains("degraded", case=False, regex=False).sum()), "degraded data quality"),
        ("usable_rows", len(usable), "PIT-valid, not invalid"),
        ("usable_ratio", len(usable) / total if total else np.nan, "usable rows / total rows"),
    ]
    return pd.DataFrame(metrics, columns=["metric", "value", "note"])


def _bucket_confidence(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return pd.cut(values, bins=[-0.01, 0.55, 0.75, 1.01], labels=["low_or_neutral", "medium", "high"]).astype(str)


def build_watchlist_admissions(structured: pd.DataFrame) -> pd.DataFrame:
    frame = structured.copy()
    for column, default in [
        ("commercial_validation_score", 0.0),
        ("customer_validation_score", 0.0),
        ("announcement_validation_score", 0.0),
        ("revenue_exposure_score", 0.0),
        ("fundamental_risk_score", 0.0),
        ("source_confidence", 0.5),
        ("extraction_confidence", 0.5),
        ("data_quality_status", "missing"),
        ("conflict_flags", ""),
        ("research_priority", "watch_only"),
    ]:
        if column not in frame.columns:
            frame[column] = default
    frame["validation_max"] = frame[[
        "commercial_validation_score",
        "customer_validation_score",
        "announcement_validation_score",
        "revenue_exposure_score",
    ]].apply(pd.to_numeric, errors="coerce").max(axis=1)
    frame["theme_available"] = frame["bottleneck_theme"].map(_nonempty) | frame["industry_bottleneck_theme"].map(_nonempty)
    frame["thesis_clear"] = frame["key_thesis"].map(_nonempty) & ~frame["key_thesis"].fillna("").astype(str).eq("missing")
    frame["low_available"] = pd.to_numeric(frame["low_position_score"], errors="coerce").notna() | pd.to_numeric(
        frame["price_position_score"], errors="coerce"
    ).notna()
    variants = {
        "loose_research_watchlist": (
            frame["is_pit_valid"].astype(bool)
            & frame["low_available"]
            & pd.to_numeric(frame["fundamental_risk_score"], errors="coerce").fillna(0.0).le(0.75)
            & ~frame["data_quality_status"].fillna("").astype(str).str.contains("invalid", case=False, regex=False)
        ),
        "standard_research_watchlist": (
            frame["is_pit_valid"].astype(bool)
            & frame["theme_available"]
            & frame["validation_max"].ge(0.5)
            & pd.to_numeric(frame["low_position_score"], errors="coerce").fillna(0.0).ge(0.55)
            & pd.to_numeric(frame["fundamental_risk_score"], errors="coerce").fillna(0.0).le(0.5)
            & ~frame["data_quality_status"].fillna("").astype(str).str.contains("invalid", case=False, regex=False)
        ),
        "strict_research_watchlist": (
            frame["is_pit_valid"].astype(bool)
            & frame["thesis_clear"]
            & pd.to_numeric(frame["source_confidence"], errors="coerce").fillna(0.0).ge(0.7)
            & pd.to_numeric(frame["extraction_confidence"], errors="coerce").fillna(0.0).ge(0.7)
            & frame["validation_max"].ge(0.7)
            & pd.to_numeric(frame["low_position_score"], errors="coerce").fillna(0.0).ge(0.60)
            & pd.to_numeric(frame["fundamental_risk_score"], errors="coerce").fillna(0.0).le(0.35)
            & frame["conflict_flags"].fillna("").astype(str).eq("")
        ),
    }
    rows: list[pd.DataFrame] = []
    for variant, mask in variants.items():
        subset = frame[mask].copy()
        if subset.empty:
            continue
        subset = subset.sort_values(["asset_id", "trade_date", "source_confidence", "extraction_confidence"], ascending=[True, True, False, False])
        first = subset.groupby("asset_id", as_index=False).first()
        first["admission_variant"] = variant
        first["first_admission_date"] = first["trade_date"]
        first["first_source_date"] = first["source_date"]
        first["admission_reason"] = variant.replace("_watchlist", "_coverage")
        first["human_review_required"] = first["admission_variant"].isin(["standard_research_watchlist", "strict_research_watchlist"]) | first[
            "research_priority"
        ].isin(["high", "medium"])
        rows.append(first)
    if not rows:
        return pd.DataFrame()
    admissions = pd.concat(rows, ignore_index=True)
    columns = [
        "admission_variant",
        "asset_id",
        "symbol",
        "name",
        "first_admission_date",
        "first_source_date",
        "stock_event_id",
        "source_type",
        "industry_bottleneck_theme",
        "bottleneck_theme",
        "admission_reason",
        "research_priority",
        "low_position_score",
        "commercial_validation_score",
        "fundamental_risk_score",
        "source_confidence",
        "extraction_confidence",
        "data_quality_status",
        "human_review_required",
    ]
    result = admissions[[column for column in columns if column in admissions.columns]].sort_values(
        ["admission_variant", "first_admission_date", "asset_id"]
    )
    validate_no_trading_language(result)
    return result


def _load_price_frame(asset_ids: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    prices = _load_prices(
        start_date=start_date,
        end_date=end_date,
        adjust_type="hfq",
        asset_ids=asset_ids,
        service=SETTINGS.research_service,
    )
    prices["trade_date"] = pd.to_datetime(prices["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    prices["asset_id"] = prices["asset_id"].astype(str)
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    return prices.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)


def build_watchlist_forward_returns(admissions: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    if admissions.empty:
        return pd.DataFrame()
    prices = prices.sort_values(["asset_id", "trade_date"]).copy()
    market_close = prices.groupby("trade_date")["close"].mean().sort_index()
    market_dates = list(market_close.index)
    price_by_asset = {asset_id: group.reset_index(drop=True) for asset_id, group in prices.groupby("asset_id")}
    rows: list[dict[str, Any]] = []
    for event in admissions.itertuples(index=False):
        asset_prices = price_by_asset.get(str(event.asset_id))
        if asset_prices is None:
            continue
        locs = asset_prices.index[asset_prices["trade_date"].eq(str(event.first_admission_date))].tolist()
        if not locs:
            continue
        start_idx = locs[0]
        start_close = _num(asset_prices.loc[start_idx, "close"])
        market_start = market_close.get(str(event.first_admission_date), np.nan)
        market_start_idx = market_dates.index(str(event.first_admission_date)) if str(event.first_admission_date) in market_dates else None
        for horizon in HORIZONS:
            end_idx = start_idx + horizon
            available = bool(end_idx < len(asset_prices) and pd.notna(start_close) and start_close != 0)
            end_close = _num(asset_prices.loc[end_idx, "close"]) if available else np.nan
            window = asset_prices.loc[start_idx : min(end_idx, len(asset_prices) - 1), "close"]
            forward = float(end_close / start_close - 1.0) if available else np.nan
            market_return = np.nan
            if market_start_idx is not None and market_start_idx + horizon < len(market_dates) and pd.notna(market_start) and market_start != 0:
                market_return = float(market_close.iloc[market_start_idx + horizon] / market_start - 1.0)
            drawdown = _max_drawdown(window) if available else np.nan
            rows.append(
                {
                    "admission_variant": event.admission_variant,
                    "asset_id": event.asset_id,
                    "symbol": event.symbol,
                    "name": event.name,
                    "first_admission_date": event.first_admission_date,
                    "horizon": f"{horizon}d",
                    "forward_return": forward,
                    "forward_return_vs_market": forward - market_return if pd.notna(forward) and pd.notna(market_return) else np.nan,
                    "forward_return_vs_industry": np.nan,
                    "industry_forward_status": "missing",
                    "max_favorable_excursion": float(window.max() / start_close - 1.0) if available and not window.empty else np.nan,
                    "max_adverse_excursion": float(window.min() / start_close - 1.0) if available and not window.empty else np.nan,
                    "max_drawdown_after_admission": drawdown,
                    "hit_positive_return": bool(forward > 0) if pd.notna(forward) else False,
                    "hit_outperform_market": bool(forward > market_return) if pd.notna(forward) and pd.notna(market_return) else False,
                    "future_data_available": available,
                    "used_for_signal": False,
                }
            )
    return pd.DataFrame(rows)


def _max_drawdown(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return np.nan
    peak = values.cummax()
    return float((values / peak - 1.0).min())


def build_variant_summary(admissions: pd.DataFrame, forward: pd.DataFrame) -> pd.DataFrame:
    if admissions.empty:
        return pd.DataFrame()
    pivot = forward.pivot_table(
        index=["admission_variant", "asset_id", "first_admission_date"],
        columns="horizon",
        values=["forward_return", "hit_positive_return", "hit_outperform_market", "future_data_available"],
        aggfunc="first",
    )
    pivot.columns = [f"{metric}_{horizon}" for metric, horizon in pivot.columns]
    pivot = pivot.reset_index()
    mfe120 = forward[forward["horizon"].eq("120d")].groupby(["admission_variant"], as_index=False).agg(
        avg_mae_120d=("max_adverse_excursion", "mean"),
        avg_mfe_120d=("max_favorable_excursion", "mean"),
        worst_120d_return=("forward_return", "min"),
        best_120d_return=("forward_return", "max"),
    )
    rows: list[dict[str, Any]] = []
    for variant, group in pivot.groupby("admission_variant"):
        admission_group = admissions[admissions["admission_variant"].eq(variant)]
        row: dict[str, Any] = {
            "admission_variant": variant,
            "admission_event_count": int(len(admission_group)),
            "unique_asset_count": int(admission_group["asset_id"].nunique()),
            "future_data_available_count": int(group.get("future_data_available_120d", pd.Series(dtype=bool)).astype(bool).sum()),
            "data_quality_status": _dominant_status(admission_group.get("data_quality_status", pd.Series(dtype="object"))),
        }
        for horizon in ["30d", "60d", "90d", "120d"]:
            returns = pd.to_numeric(group.get(f"forward_return_{horizon}", pd.Series(dtype=float)), errors="coerce")
            available = group.get(f"future_data_available_{horizon}", pd.Series(dtype=bool)).astype(bool)
            row[f"avg_forward_{horizon}_return"] = float(returns.mean())
            row[f"median_forward_{horizon}_return"] = float(returns.median())
            positives = group.get(f"hit_positive_return_{horizon}", pd.Series(dtype=bool)).astype(bool)
            outperform = group.get(f"hit_outperform_market_{horizon}", pd.Series(dtype=bool)).astype(bool)
            row[f"positive_{horizon}_rate"] = float(positives[available].mean()) if available.any() else np.nan
            row[f"outperform_market_{horizon}_rate"] = float(outperform[available].mean()) if available.any() else np.nan
        rows.append(row)
    summary = pd.DataFrame(rows).merge(mfe120, on="admission_variant", how="left")
    return summary


def _dominant_status(series: pd.Series) -> str:
    if series.empty:
        return "missing"
    return str(series.fillna("missing").astype(str).value_counts().idxmax())


def write_contract(output_dir: Path) -> None:
    text = """# Research Input Contract v1

This contract defines research-only structured output for Technical Bottleneck candidates. It does not define any trade signal.

## broker_report

Required fields: `source_id`, `source_type`, `source_title`, `source_date`, `as_of_date`, `asset_id`, `symbol`, `name`, `analyst_org`, `report_type`, `industry_theme`, `bottleneck_theme`, `key_thesis`, `commercial_validation`, `customer_validation`, `revenue_exposure`, `supplier_dependency`, `capacity_expansion`, `risk_points`, `source_confidence`, `extraction_confidence`, `is_pit_valid`.

## news

Required fields: `source_id`, `source_type`, `source_title`, `source_date`, `as_of_date`, `asset_id`, `event_type`, `industry_catalyst`, `policy_catalyst`, `supply_chain_event`, `customer_event`, `risk_event`, `evidence_direction`, `source_confidence`, `is_pit_valid`.

## announcement

Required fields: `announcement_id`, `announcement_date`, `as_of_date`, `asset_id`, `announcement_type`, `order_contract`, `customer_contract`, `capacity_project`, `fundraising_project`, `equity_incentive`, `risk_disclosure`, `financial_guidance`, `evidence_direction`, `is_pit_valid`.

## fundamentals

Required fields: `financial_as_of_date`, `asset_id`, `revenue_growth`, `profit_growth`, `gross_margin_trend`, `cashflow_quality`, `debt_risk`, `inventory_risk`, `receivable_risk`, `fundamental_risk_score`, `fundamental_recovery_score`, `is_pit_valid`.

## valuation / low position

Required fields: `trade_date`, `asset_id`, `price_position_score`, `valuation_position_score`, `expectation_position_score`, `fundamental_position_score`, `technical_position_score`, `low_position_score`, `price_drawdown_from_120d_high`, `price_percentile_120d`, `valuation_data_status`, `expectation_data_status`, `fundamental_data_status`.

## PIT Rule

Every source must satisfy `source_date <= trade_date` and `as_of_date <= trade_date`. Missing fields are marked `missing`; missing data must not receive a 0.6 penalty multiplier.
"""
    (output_dir / "research_input_contract_v1.md").write_text(text, encoding="utf-8")


def write_interpretation(
    output_dir: Path,
    structured: pd.DataFrame,
    audit: pd.DataFrame,
    admissions: pd.DataFrame,
    forward: pd.DataFrame,
    summary: pd.DataFrame,
    git_info: dict[str, str],
) -> None:
    audit_lookup = dict(zip(audit["metric"], audit["value"]))
    source_dist = structured["source_type"].value_counts().rename_axis("source_type").reset_index(name="rows").to_markdown(index=False)
    admission_counts = admissions["admission_variant"].value_counts().rename_axis("variant").reset_index(name="events").to_markdown(index=False)
    summary_table = summary.to_markdown(index=False) if not summary.empty else "No admission summary rows."
    examples_positive, examples_negative, examples_degraded = _case_tables(admissions, forward)
    text = f"""# Tech Bottleneck Research Input Contract and Watchlist Forward Return v1

## 1. Executive Summary

- Research input contract v1 was generated.
- Structured output rows: {len(structured):,}; usable ratio: {audit_lookup.get('usable_ratio')}.
- PIT valid ratio: {audit_lookup.get('pit_valid_ratio')}; lookahead violation rows: {audit_lookup.get('lookahead_violation_rows')}.
- Watchlist admission events: {len(admissions):,}.
- Admission coverage:

{admission_counts}

- Main forward-return horizons are 30/60/90/120 trading rows; no 5/10/20 horizon is used as a main conclusion.
- Current reliable inputs: research selection snapshot, low-position score, PIT broker-report evidence where available.
- Current missing-heavy inputs: valuation, expectation, fundamental recovery, industry relative forward return.
- No trading signal columns are emitted; forward returns are marked `used_for_signal=false`.
- Formal strategy files remain untracked in git; this task did not write them, but git diff alone cannot fully prove historical immutability.

## 2. Research Input Contract

See `research_input_contract_v1.md`. It defines standard fields for broker reports, news, announcements, fundamentals, and valuation / low-position inputs.

## 3. Structured Output Quality

Source type distribution:

{source_dist}

Quality audit highlights:

{audit.to_markdown(index=False)}

The structured output is usable as a research layer if PIT-valid rows stay high and lookahead rows remain zero. It is not yet complete for fundamental / valuation attribution because those fields are mostly missing.

## 4. Watchlist Admission Rule Definitions

- `loose_research_watchlist`: PIT-valid structured output with available low-position information and no invalid data status.
- `standard_research_watchlist`: PIT-valid, theme available, validation score present, low-position score reasonable, risk score not high.
- `strict_research_watchlist`: PIT-valid, clear thesis, confidence thresholds met, validation score strong, low-position score strong, risk acceptable.

Admission means research observation only. It is not an execution instruction and does not alter any strategy ranking.

## 5. Watchlist Forward Return Results

{summary_table}

Forward returns are post-admission diagnostics only and are not used by admission rules.

## 6. Source Type / Field Reliability

- `research_selection_snapshot` has broad coverage and stable PIT dates, but mainly reflects low-position and existing candidate metadata.
- `broker_report` evidence is more explanatory but has limited coverage.
- Valuation / expectation / fundamental recovery fields are currently missing-heavy and should not drive admission strictness alone.
- Low-position score is currently the most reusable non-evidence input for broad watchlist construction.

## 7. Case Review

Positive 120d cases:

{examples_positive}

Negative 120d cases:

{examples_negative}

Data-quality degraded cases:

{examples_degraded}

## 8. What This Layer Does Not Do

- 不产生买入信号。
- 不产生卖出信号。
- 不改变 Top5。
- 不改变正式策略。
- 不研究 trigger / holding / exit。
- 不使用 evidence multiplier。
- 不输出交易指令。

## 9. Recommendation

- Continue improving research input coverage before trigger / holding / exit replay.
- Add announcement/news/fundamental PIT sources to reduce dependence on research selection snapshots.
- Add dashboard watchlist only as a review artifact.
- Build a small manual labeling workflow for watchlist admissions to calibrate thesis clarity and false positives.

## 10. Appendix

Generated files:

- `research_input_contract_v1.md`
- `research_structured_outputs.csv`
- `research_output_quality_audit.csv`
- `watchlist_admission_events.csv`
- `watchlist_forward_return_30_60_90_120.csv`
- `watchlist_admission_variant_summary.csv`
- `watchlist_forward_return_interpretation.md`

Git / formal strategy check:

```text
repo_root: {git_info.get('repo_root')}
status:
{git_info.get('formal_strategy_status') or '(empty)'}
ls-files:
{git_info.get('formal_strategy_ls_files') or '(empty; files are not tracked)'}
stat:
{git_info.get('formal_strategy_stat')}
```

Assumptions:

- `research_selection_snapshot` is a research input source, not a trading source.
- Broker-report PIT evidence is active only on and after `source_date`.
- Industry forward return is missing in v1 and explicitly marked missing.
"""
    (output_dir / "watchlist_forward_return_interpretation.md").write_text(text, encoding="utf-8")


def _case_tables(admissions: pd.DataFrame, forward: pd.DataFrame) -> tuple[str, str, str]:
    merged = forward[forward["horizon"].eq("120d")].merge(
        admissions,
        on=["admission_variant", "asset_id", "symbol", "name", "first_admission_date"],
        how="left",
    )
    cols = ["admission_variant", "asset_id", "name", "first_admission_date", "forward_return", "data_quality_status", "source_type"]
    positive = merged.sort_values("forward_return", ascending=False).head(10)[cols].to_markdown(index=False) if not merged.empty else "No cases."
    negative = merged.sort_values("forward_return", ascending=True).head(10)[cols].to_markdown(index=False) if not merged.empty else "No cases."
    degraded = (
        merged[merged["data_quality_status"].fillna("").astype(str).str.contains("degraded", case=False, regex=False)]
        .head(10)[cols]
        .to_markdown(index=False)
        if not merged.empty
        else "No cases."
    )
    return positive, negative, degraded


def _git_info(repo_root: Path) -> dict[str, str]:
    targets = ["src/stock_research/tech_bottleneck_v1.py", "src/stock_research/tech_bottleneck_candidates.py"]

    def run(args: list[str]) -> str:
        completed = subprocess.run(["git", *args], cwd=repo_root, text=True, capture_output=True, check=False)
        return (completed.stdout + completed.stderr).strip()

    return {
        "repo_root": run(["rev-parse", "--show-toplevel"]),
        "formal_strategy_status": run(["status", "--short", "--", *targets]),
        "formal_strategy_ls_files": run(["ls-files", "--", *targets]),
        "formal_strategy_stat": subprocess.run(
            ["stat", "-f", "%Sm %N", *targets], cwd=repo_root, text=True, capture_output=True, check=False
        ).stdout.strip(),
    }


def run(output_dir: Path = OUTPUT_DIR, input_dir: Path = RESEARCH_SELECTION_DIR, evidence_dir: Path = EVIDENCE_REPLAY_DIR) -> dict[str, pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates, low_position, risk = _load_research_inputs(input_dir)
    evidence = _load_evidence(evidence_dir)
    structured = build_structured_outputs(candidates, low_position, risk, evidence)
    validate_structured_output_pit(structured)
    audit = build_quality_audit(structured)
    admissions = build_watchlist_admissions(structured)
    start_date = str(candidates["trade_date"].min())
    end_date = (pd.Timestamp(str(candidates["trade_date"].max())) + pd.Timedelta(days=220)).strftime("%Y-%m-%d")
    prices = _load_price_frame(sorted(admissions["asset_id"].dropna().astype(str).unique().tolist()), start_date, end_date)
    forward = build_watchlist_forward_returns(admissions, prices)
    if not forward.empty and forward["used_for_signal"].astype(bool).any():
        raise ValueError("forward returns must not be used for signals")
    summary = build_variant_summary(admissions, forward)
    validate_no_trading_language(admissions)

    write_contract(output_dir)
    structured.to_csv(output_dir / "research_structured_outputs.csv", index=False)
    audit.to_csv(output_dir / "research_output_quality_audit.csv", index=False)
    admissions.to_csv(output_dir / "watchlist_admission_events.csv", index=False)
    forward.to_csv(output_dir / "watchlist_forward_return_30_60_90_120.csv", index=False)
    summary.to_csv(output_dir / "watchlist_admission_variant_summary.csv", index=False)
    write_interpretation(output_dir, structured, audit, admissions, forward, summary, _git_info(Path.cwd()))
    return {
        "structured": structured,
        "audit": audit,
        "admissions": admissions,
        "forward": forward,
        "summary": summary,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build research input contract and watchlist forward-return analysis.")
    parser.add_argument("--input-dir", default=str(RESEARCH_SELECTION_DIR))
    parser.add_argument("--evidence-dir", default=str(EVIDENCE_REPLAY_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run(output_dir=Path(args.output_dir), input_dir=Path(args.input_dir), evidence_dir=Path(args.evidence_dir))
    audit_lookup = dict(zip(result["audit"]["metric"], result["audit"]["value"]))
    print(f"structured_rows={len(result['structured']):,}")
    print(f"usable_ratio={audit_lookup.get('usable_ratio')}")
    print(result["admissions"]["admission_variant"].value_counts().to_string())


if __name__ == "__main__":
    main()
