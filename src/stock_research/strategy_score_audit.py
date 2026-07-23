from __future__ import annotations

from collections import Counter
import json
from typing import Any

import pandas as pd


DETAIL_COLUMNS = [
    "trade_date",
    "strategy_id",
    "strategy_name",
    "asset_id",
    "stock_name",
    "stock_name_source",
    "confirmation_state",
    "phase12a_rule_layer",
    "phase12a_rule_action",
    "fill_status",
    "eligibility_status",
    "top5_eligible",
    "backtest_entry_eligible",
    "eligibility_reason_codes",
    "eligibility_warning_codes",
    "buy_signal_status",
    "eligibility_contract_version",
    "risk_gate_code",
    "risk_gate_reason",
    "price_limit_regime",
    "near_limit_down_threshold",
    "data_quality_status",
    "pct_chg",
    "selected_flag",
    "selected_rank",
    "source_rank",
    "raw_candidate_score",
    "raw_candidate_score_source",
    "published_score",
    "published_score_source",
    "display_score",
    "display_score_source",
    "selection_reason",
    "eligibility_layer",
    "filter_reason",
    "data_date_used",
    "review_tier",
    "source_type",
    "strategy_run_id",
    "anomaly_flags",
    "notes",
]


def build_strategy_score_audit(
    *,
    trade_date: str,
    review_rows: list[dict[str, Any]],
    strategy_results: dict[str, dict[str, Any]],
    display_rows: list[dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    display_lookup = _display_rows_by_key(display_rows, trade_date=trade_date)
    for review_row in review_rows:
        strategy_id = str(review_row.get("strategy_id") or "")
        strategy_result = strategy_results.get(strategy_id) or {}
        lineage_row = _resolve_lineage_row(
            strategy_id=strategy_id,
            trade_date=trade_date,
            review_row=review_row,
            strategy_result=strategy_result,
        )
        display_row = display_lookup.get(_display_row_key(trade_date, review_row))
        rows.append(
            _build_audit_row(
                trade_date=trade_date,
                review_row=review_row,
                display_row=display_row,
                lineage_row=lineage_row,
            )
        )
    return pd.DataFrame(rows).reindex(columns=DETAIL_COLUMNS)


def summarize_strategy_score_audit(detail: pd.DataFrame, *, trade_date: str) -> dict[str, Any]:
    if detail.empty:
        return {
            "trade_date": trade_date,
            "generated_at": "",
            "strategies": [],
            "total_rows": 0,
            "selected_rows": 0,
            "anomaly_row_count": 0,
            "anomaly_counts_by_type": {},
            "strategy_counts": {},
        }

    anomaly_counter: Counter[str] = Counter()
    for flags in detail["anomaly_flags"]:
        for flag in flags or []:
            anomaly_counter[str(flag)] += 1

    strategy_summaries: list[dict[str, Any]] = []
    for strategy_id, group in detail.groupby("strategy_id", dropna=False):
        flagged = group[group["anomaly_flags"].map(bool)]
        strategy_summaries.append(
            {
                "strategy_id": str(strategy_id or ""),
                "row_count": int(len(group)),
                "selected_count": int(group["selected_flag"].fillna(False).astype(bool).sum()),
                "anomaly_count": int(len(flagged)),
                "published_score_sources": _sorted_non_empty(group["published_score_source"]),
                "display_score_sources": _sorted_non_empty(group["display_score_source"]),
                "raw_score_sources": _sorted_non_empty(group["raw_candidate_score_source"]),
                "sample_anomalies": flagged.head(3)[["asset_id", "anomaly_flags"]].to_dict("records"),
            }
        )

    return {
        "trade_date": trade_date,
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "strategies": strategy_summaries,
        "total_rows": int(len(detail)),
        "selected_rows": int(detail["selected_flag"].fillna(False).astype(bool).sum()),
        "anomaly_row_count": int(detail["anomaly_flags"].map(bool).sum()),
        "anomaly_counts_by_type": dict(sorted(anomaly_counter.items())),
        "strategy_counts": {item["strategy_id"]: item["row_count"] for item in strategy_summaries},
    }


def _build_audit_row(
    *,
    trade_date: str,
    review_row: dict[str, Any],
    display_row: dict[str, Any] | None,
    lineage_row: dict[str, Any] | None,
) -> dict[str, Any]:
    strategy_id = str(review_row.get("strategy_id") or "")
    published_score = _optional_float(review_row.get("score_total"))
    published_score_source = _text(review_row.get("score_source"))

    raw_candidate_score, raw_candidate_score_source = _raw_score_for_strategy(
        strategy_id=strategy_id,
        review_row=review_row,
        lineage_row=lineage_row,
    )
    normalized_published_source = _published_source_for_strategy(
        strategy_id=strategy_id,
        review_source=published_score_source,
        raw_candidate_score=raw_candidate_score,
    )
    display_score = _optional_float((display_row or {}).get("score_total"))
    if display_score is None:
        display_score = published_score
    display_score_source = _text((display_row or {}).get("score_source"))
    if display_score_source:
        display_score_source = _published_source_for_strategy(
            strategy_id=strategy_id,
            review_source=display_score_source,
            raw_candidate_score=raw_candidate_score,
        )
    elif display_score == published_score:
        display_score_source = normalized_published_source
    stock_name = _text(
        (lineage_row or {}).get("stock_name")
        or (lineage_row or {}).get("name")
        or review_row.get("stock_name")
    )
    selection_reason = _selection_reason(lineage_row)
    eligibility_layer = _text((lineage_row or {}).get("phase12a_rule_layer") or (lineage_row or {}).get("eligibility_layer"))
    data_date_used = _lineage_trade_date(lineage_row) or _text(review_row.get("trade_date") or trade_date)[:10]

    row = {
        "trade_date": trade_date,
        "strategy_id": strategy_id,
        "strategy_name": _text(review_row.get("strategy_name")),
        "asset_id": _text(review_row.get("asset_id")),
        "stock_name": stock_name,
        "stock_name_source": _text(review_row.get("stock_name_source")),
        "confirmation_state": _text(review_row.get("confirmation_state")),
        "phase12a_rule_layer": _text(review_row.get("phase12a_rule_layer")),
        "phase12a_rule_action": _text(review_row.get("phase12a_rule_action")),
        "fill_status": _text(review_row.get("fill_status")),
        "eligibility_status": _text(review_row.get("eligibility_status")),
        "top5_eligible": review_row.get("top5_eligible"),
        "backtest_entry_eligible": review_row.get("backtest_entry_eligible"),
        "eligibility_reason_codes": _list_field(review_row.get("eligibility_reason_codes")),
        "eligibility_warning_codes": _list_field(review_row.get("eligibility_warning_codes")),
        "buy_signal_status": str(review_row.get("buy_signal_status") or ""),
        "eligibility_contract_version": _text(review_row.get("eligibility_contract_version")),
        "risk_gate_code": _text(review_row.get("risk_gate_code")),
        "risk_gate_reason": _text(review_row.get("risk_gate_reason")),
        "price_limit_regime": _text(review_row.get("price_limit_regime")),
        "near_limit_down_threshold": _optional_float(review_row.get("near_limit_down_threshold")),
        "data_quality_status": _text(review_row.get("data_quality_status")),
        "pct_chg": _optional_float(review_row.get("pct_chg")),
        "selected_flag": True,
        "selected_rank": _optional_int(review_row.get("rank")),
        "source_rank": _optional_int(review_row.get("source_rank") or review_row.get("rank")),
        "raw_candidate_score": raw_candidate_score,
        "raw_candidate_score_source": raw_candidate_score_source,
        "published_score": published_score,
        "published_score_source": normalized_published_source,
        "display_score": display_score,
        "display_score_source": display_score_source,
        "selection_reason": selection_reason,
        "eligibility_layer": eligibility_layer,
        "filter_reason": "",
        "data_date_used": data_date_used,
        "review_tier": _text(review_row.get("review_tier")),
        "source_type": _text(review_row.get("source_type")),
        "strategy_run_id": _text(review_row.get("strategy_run_id")),
        "anomaly_flags": [],
        "notes": "",
    }
    row["anomaly_flags"] = _anomaly_flags(
        strategy_id=strategy_id,
        review_row=review_row,
        display_row=display_row,
        lineage_row=lineage_row,
        audit_row=row,
    )
    return row


def _resolve_lineage_row(
    *,
    strategy_id: str,
    trade_date: str,
    review_row: dict[str, Any],
    strategy_result: dict[str, Any],
) -> dict[str, Any] | None:
    if _review_row_is_current_mid_trend_manifest_score(
        trade_date=trade_date,
        review_row=review_row,
    ):
        return dict(review_row)
    requested_asset_key = _row_key(trade_date, review_row.get("asset_id"))[1]
    audit_date = _text(review_row.get("trade_date"))[:10] or trade_date
    for frame_name in _candidate_frame_order(strategy_id):
        rows = _records_list(strategy_result.get(frame_name))
        if not rows:
            continue
        matched = _latest_eligible_row(rows, asset_key=requested_asset_key, trade_date=audit_date)
        if matched is not None:
            return matched
    return None


def _review_row_is_current_mid_trend_manifest_score(
    *,
    trade_date: str,
    review_row: dict[str, Any],
) -> bool:
    return (
        _text(review_row.get("strategy_id")) == "mid_trend"
        and _text(review_row.get("source_type")) == "strategy_manifest"
        and _text(review_row.get("trade_date"))[:10] == trade_date
        and _text(review_row.get("score_source")) == "mid_trend_funnel_score"
        and _optional_float(review_row.get("score_total")) is not None
    )


def _candidate_frame_order(strategy_id: str) -> list[str]:
    if strategy_id == "tech_bottleneck":
        return ["review_rows", "candidates", "signals"]
    if strategy_id == "lhb_shortline":
        return ["candidates", "signals", "review_rows"]
    if strategy_id == "mid_trend":
        return ["signals", "candidates", "positions", "review_rows"]
    return ["review_rows", "candidates", "signals", "positions"]


def _rows_by_key(rows: list[dict[str, Any]], *, trade_date: str) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        row_trade_date = _text(row.get("trade_date") or row.get("date") or row.get("rebalance_date"))[:10] or trade_date
        asset_values = [
            row.get("asset_id"),
            row.get("ts_code"),
            row.get("symbol"),
            row.get("stock_code"),
        ]
        for asset_value in asset_values:
            key = _row_key(row_trade_date, asset_value)
            if key[1]:
                lookup[key] = row
    return lookup


def _display_rows_by_key(rows: list[dict[str, Any]], *, trade_date: str) -> dict[tuple[str, str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = _display_row_key(trade_date, row)
        if key[1]:
            lookup[key] = row
    return lookup


def _latest_eligible_row(rows: list[dict[str, Any]], *, asset_key: str, trade_date: str) -> dict[str, Any] | None:
    matched: dict[str, Any] | None = None
    matched_date = ""
    for row in rows:
        row_asset_key = _row_asset_key(row)
        row_date = _lineage_trade_date(row)
        if not row_asset_key or row_asset_key != asset_key or not row_date:
            continue
        if row_date > trade_date:
            continue
        if matched is None or row_date > matched_date:
            matched = row
            matched_date = row_date
    return matched


def _row_key(trade_date: str, asset_id: Any) -> tuple[str, str]:
    text = _text(asset_id)
    normalized = _normalize_asset_id(text)
    return trade_date[:10], normalized or text


def _display_row_key(trade_date: str, row: dict[str, Any]) -> tuple[str, str, str]:
    row_trade_date = _text(row.get("trade_date") or row.get("date") or row.get("rebalance_date"))[:10] or trade_date[:10]
    asset_key = _row_key(row_trade_date, row.get("asset_id") or row.get("ts_code") or row.get("symbol") or row.get("stock_code"))[1]
    strategy_id = _text(row.get("strategy_id"))
    return row_trade_date, asset_key, strategy_id


def _row_asset_key(row: dict[str, Any]) -> str:
    for asset_value in (row.get("asset_id"), row.get("ts_code"), row.get("symbol"), row.get("stock_code")):
        key = _row_key("", asset_value)[1]
        if key:
            return key
    return ""


def _lineage_trade_date(row: dict[str, Any] | None) -> str:
    source_row = row or {}
    return _text(source_row.get("trade_date") or source_row.get("date") or source_row.get("rebalance_date"))[:10]


def _records_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, pd.DataFrame):
        return value.to_dict("records")
    if isinstance(value, list):
        return [dict(row) for row in value]
    return []


def _normalize_asset_id(value: str) -> str:
    text = value.upper().strip()
    if not text:
        return ""
    parts = text.split(":")
    if len(parts) == 3 and parts[0] == "CN":
        return text
    if "." in text:
        symbol, exchange = text.split(".", 1)
        if exchange in {"SH", "SZ", "BJ"}:
            return f"CN:{exchange}:{symbol}"
    return text


def _raw_score_for_strategy(
    *,
    strategy_id: str,
    review_row: dict[str, Any],
    lineage_row: dict[str, Any] | None,
) -> tuple[float | None, str]:
    source_row = lineage_row or {}
    if strategy_id == "lhb_shortline":
        for column in ("final_score", "score_total", "lhb_shortline_score", "auction_enhanced_score"):
            value = _optional_float(source_row.get(column))
            if value is not None:
                return value, column
        if _text(review_row.get("score_source")) == "score_total":
            value = _optional_float(review_row.get("score_total"))
            if value is not None:
                return value, "score_total"
        return None, ""
    if strategy_id == "mid_trend":
        value = _optional_float(source_row.get("mid_trend_funnel_score"))
        if value is not None:
            return value, "mid_trend_funnel_score"
        if _text(review_row.get("score_source")) == "mid_trend_funnel_score":
            return _optional_float(review_row.get("score_total")), "mid_trend_funnel_score"
        return None, ""
    if strategy_id == "tech_bottleneck":
        value = _optional_float(source_row.get("bottleneck_score"))
        if value is not None:
            return value, "bottleneck_score"
        return None, ""
    value = _optional_float(source_row.get("score_total"))
    if value is not None:
        return value, "score_total"
    return None, ""


def _published_source_for_strategy(
    *,
    strategy_id: str,
    review_source: str,
    raw_candidate_score: float | None,
) -> str:
    if strategy_id == "tech_bottleneck" and raw_candidate_score is not None:
        return "bottleneck_score_x100"
    return review_source


def _selection_reason(lineage_row: dict[str, Any] | None) -> str:
    source_row = lineage_row or {}
    for column in ("candidate_reason", "selection_reason", "reason", "signal_reason"):
        text = _text(source_row.get(column))
        if text:
            return text
    return ""


def _anomaly_flags(
    *,
    strategy_id: str,
    review_row: dict[str, Any],
    display_row: dict[str, Any] | None,
    lineage_row: dict[str, Any] | None,
    audit_row: dict[str, Any],
) -> list[str]:
    flags: list[str] = []
    if audit_row["published_score"] is not None and not audit_row["published_score_source"]:
        flags.append("missing_published_score_source")
    if audit_row["display_score"] is not None and not audit_row["display_score_source"]:
        flags.append("missing_display_score_source")
    self_contained_lhb_score = _is_self_contained_lhb_score_total(strategy_id=strategy_id, audit_row=audit_row)
    if lineage_row is None and not self_contained_lhb_score:
        flags.append("missing_candidate_source")
    mapped_without_raw = (
        strategy_id == "lhb_shortline"
        and audit_row["raw_candidate_score"] is None
        and audit_row["published_score"] is not None
        and audit_row["published_score_source"] == "auction_enhanced_score"
    )
    if audit_row["raw_candidate_score"] is None and not mapped_without_raw:
        flags.append("missing_raw_candidate_score")
    if mapped_without_raw:
        flags.append("mapped_score_without_raw_score")
    if (
        strategy_id == "tech_bottleneck"
        and audit_row["raw_candidate_score"] is not None
        and audit_row["published_score"] is not None
    ):
        expected_score = round(float(audit_row["raw_candidate_score"]) * 100.0, 6)
        if abs(expected_score - float(audit_row["published_score"])) > 1e-6:
            flags.append("published_score_mismatch")
    if (
        audit_row["published_score"] is not None
        and audit_row["display_score"] is not None
        and abs(float(audit_row["published_score"]) - float(audit_row["display_score"])) > 1e-6
    ):
        flags.append("published_display_score_mismatch")
    if lineage_row is None and not self_contained_lhb_score and not audit_row["selection_reason"] and not audit_row["eligibility_layer"]:
        flags.append("unknown_selection_reason")
    lineage_trade_date = _lineage_trade_date(lineage_row)
    if lineage_trade_date and lineage_trade_date < audit_row["trade_date"]:
        flags.append("stale_source")
    return flags


def _is_self_contained_lhb_score_total(*, strategy_id: str, audit_row: dict[str, Any]) -> bool:
    return (
        strategy_id == "lhb_shortline"
        and audit_row["raw_candidate_score"] is not None
        and audit_row["raw_candidate_score_source"] == "score_total"
        and audit_row["published_score_source"] == "score_total"
    )


def _sorted_non_empty(values: pd.Series) -> list[str]:
    items = {_text(value) for value in values.dropna()}
    return sorted(item for item in items if item)


def _optional_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(result):
        return None
    return result


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list_field(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    text = _text(value)
    if not text or text.lower() == "nan":
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return [text]
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return [text]
