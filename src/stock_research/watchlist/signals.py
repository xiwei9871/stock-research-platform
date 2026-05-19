from __future__ import annotations

import pandas as pd

from stock_research.watchlist.risk import classify_watchlist_risks
from stock_research.watchlist.store import WATCHLIST_SIGNAL_COLUMNS


WATCHLIST_SIGNAL_OUTPUT_COLUMNS = list(WATCHLIST_SIGNAL_COLUMNS)


def _feature_map(feature_snapshot: pd.DataFrame) -> dict[str, dict[str, float]]:
    if feature_snapshot.empty:
        return {}

    feature_values: dict[str, dict[str, float]] = {}
    for row in feature_snapshot.to_dict("records"):
        asset_id = str(row.get("asset_id", ""))
        feature_name = row.get("feature_name")
        if not asset_id or not feature_name:
            continue
        value = row.get("feature_value")
        try:
            if pd.isna(value):
                continue
        except Exception:
            pass
        feature_values.setdefault(asset_id, {})[str(feature_name)] = float(value)
    return feature_values


def _signal_tags(feature_values: dict[str, float], score_row: dict[str, object]) -> list[str]:
    tags: list[str] = []
    if score_row:
        tags.append("candidate")

    ret_20d = feature_values.get("ret_20d")
    ma20_deviation = feature_values.get("ma20_deviation")
    ret_5d = feature_values.get("ret_5d")

    if ret_20d is not None and ma20_deviation is not None:
        if ret_20d > 0 and ma20_deviation < 0:
            tags.append("pullback")
        if ret_20d < 0 and ma20_deviation < 0:
            tags.append("breakdown")

    if ret_5d is not None and ret_5d >= 0.15:
        tags.append("overheat")
    elif ma20_deviation is not None and ma20_deviation >= 0.12:
        tags.append("overheat")

    return tags


def _signal_row(
    item: dict[str, object],
    feature_values: dict[str, float],
    score_row: dict[str, object],
    signal_tags: list[str],
    risk_tags: list[str],
    output_version: str,
) -> dict[str, object]:
    must_watch = "candidate" in signal_tags and "risk_excluded" not in risk_tags
    primary_signal = _primary_signal(signal_tags)
    score_total = score_row.get("score_total") if score_row else 0.0
    sector_context = item.get("sector_context", {})
    reason_json = {
        "score_rank": score_row.get("rank") if score_row else None,
        "score_total": score_total,
        "feature_values": {
            key: feature_values[key]
            for key in sorted(feature_values)
            if key in {"ret_5d", "ret_20d", "ma20_deviation", "max_drawdown_20d"}
        },
        "sector_context": sector_context,
        "market_state": item.get("market_state", {}),
        "signal_tags": signal_tags,
        "risk_tags": risk_tags,
        "must_watch": must_watch,
        "final_tags": {
            "signal_tags": signal_tags,
            "risk_tags": risk_tags,
            "must_watch": must_watch,
        },
        "output_version": output_version,
    }
    return {
        "watchlist_id": None,
        "trade_date": None,
        "asset_id": item.get("asset_id"),
        "stock_code": item.get("stock_code"),
        "stock_name": item.get("stock_name"),
        "priority": item.get("priority", 100),
        "signal_score": score_total,
        "primary_signal": primary_signal,
        "signal_tags": signal_tags,
        "risk_tags": risk_tags,
        "must_watch": must_watch,
        "reason_json": reason_json,
        "output_version": output_version,
    }


def build_watchlist_signal_rows(
    *,
    watchlist_items: pd.DataFrame,
    top_scores: list[dict[str, object]],
    feature_snapshot: pd.DataFrame,
    market_state: dict[str, object],
    sector_strength: pd.DataFrame,
    industry_map: dict[str, dict[str, object]],
    output_version: str,
) -> pd.DataFrame:
    feature_lookup = _feature_map(feature_snapshot)
    score_map = {str(row.get("asset_id")): dict(row) for row in top_scores if row.get("asset_id")}
    sector_map = {
        str(row.get("industry_code")): dict(row)
        for row in sector_strength.to_dict("records")
        if row.get("industry_code")
    }

    records: list[dict[str, object]] = []
    ordered_items = watchlist_items.copy()
    if not ordered_items.empty:
        ordered_items = ordered_items.sort_values(
            by=[column for column in ["priority", "stock_code", "asset_id"] if column in ordered_items.columns]
        )

    for item in ordered_items.to_dict("records"):
        asset_id = str(item.get("asset_id", ""))
        feature_values = feature_lookup.get(asset_id, {})
        score_row = score_map.get(asset_id, {})
        industry_context = industry_map.get(asset_id, {})
        sector_row = None
        industry_code = industry_context.get("industry_code")
        if industry_code:
            sector_row = sector_map.get(str(industry_code))
        sector_context = dict(industry_context)
        if sector_row:
            sector_context |= {
                "strength_rank": sector_row.get("strength_rank"),
                "strength_score": sector_row.get("strength_score"),
            }
        item_context = dict(item)
        item_context["market_state"] = market_state
        item_context["sector_context"] = sector_context

        signal_tags = _signal_tags(feature_values, score_row)
        risk_tags = classify_watchlist_risks(
            feature_values=feature_values,
            market_state=market_state,
            sector_row=sector_row,
        )
        if "candidate" in signal_tags and "risk_excluded" not in risk_tags:
            signal_tags = signal_tags + ["must_watch"]

        records.append(
            _signal_row(
                item_context,
                feature_values,
                score_row,
                signal_tags,
                risk_tags,
                output_version,
            )
        )

    frame = pd.DataFrame(records, columns=WATCHLIST_SIGNAL_OUTPUT_COLUMNS)
    if not frame.empty:
        frame["must_watch"] = frame["must_watch"].map(bool).astype(object)
    return frame.reindex(columns=WATCHLIST_SIGNAL_OUTPUT_COLUMNS)


def _primary_signal(signal_tags: list[str]) -> str:
    for tag in ("candidate", "breakdown", "pullback", "overheat", "must_watch"):
        if tag in signal_tags:
            return tag
    return "neutral"
