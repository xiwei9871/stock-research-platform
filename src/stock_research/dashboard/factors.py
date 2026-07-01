from __future__ import annotations

import math
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_config import manual_v1_config
from stock_research.factor_registry import list_factor_metadata
from stock_research.scoring import composite_score, rank_score
from stock_research.scoring.base import normalize_trade_keys


def list_factor_library(service: str = SETTINGS.research_service) -> list[dict[str, Any]]:
    config = manual_v1_config()
    weights = dict(config["weights"])
    coverage = _factor_coverage(service)
    rows = []
    for meta in list_factor_metadata():
        score_name = f"{meta.factor_name}_score"
        coverage_row = coverage.get(meta.factor_name, {})
        rows.append(
            {
                "factor_name": meta.factor_name,
                "factor_group": meta.factor_group,
                "direction": meta.direction,
                "description": meta.description,
                "source": meta.source,
                "calc_version": meta.calc_version,
                "status": str(coverage_row.get("approval_status") or meta.status),
                "availability_start_date": meta.availability_start_date,
                "availability_reason": meta.availability_reason,
                "latest_available_date": coverage_row.get("latest_available_date"),
                "coverage_count": int(coverage_row.get("coverage_count") or 0),
                "used_in_manual_v1": score_name in weights,
                "manual_v1_weight": weights.get(score_name),
            }
        )
    return rows


def build_factor_score_preview(
    trade_date: str,
    selected_factors: list[dict[str, Any]],
    top_n: int = 30,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    normalized = _normalize_selected_factors(selected_factors)
    factor_names = [row["factor_name"] for row in normalized]
    factor_rows = _load_factor_rows(trade_date, factor_names, service=service)
    if factor_rows.empty:
        return {"trade_date": trade_date, "selected_factors": normalized, "items": []}

    wide = (
        normalize_trade_keys(factor_rows)
        .pivot_table(
            index=["trade_date", "asset_id"],
            columns="factor_name",
            values="factor_value",
            aggfunc="first",
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    scored = wide
    weights: dict[str, float] = {}
    for row in normalized:
        factor_name = row["factor_name"]
        score_col = f"{factor_name}_score"
        scored = rank_score.rank_score_by_date(
            scored,
            value_col=factor_name,
            ascending=row["direction"] == "lower",
            output_col=score_col,
        )
        weights[score_col] = float(row["weight"])

    composite = composite_score.build_composite_scores(
        scored,
        weights=weights,
        score_version="preview",
    )
    component_cols = list(weights)
    composite = composite.sort_values(["rank", "asset_id"]).head(top_n).copy()
    composite["score_components"] = composite[component_cols].to_dict("records")
    items = composite[
        ["trade_date", "asset_id", "rank", "score_total", "score_components"]
    ].to_dict("records")
    return {"trade_date": trade_date, "selected_factors": normalized, "items": items}


def parse_factor_selection(text: str) -> list[dict[str, Any]]:
    rows = []
    for raw in [item.strip() for item in text.split(",") if item.strip()]:
        parts = raw.split(":")
        if len(parts) != 3:
            raise ValueError("factor selection must use factor_name:direction:weight")
        rows.append(
            {
                "factor_name": parts[0],
                "direction": parts[1],
                "weight": float(parts[2]),
            }
        )
    return _normalize_selected_factors(rows)


def _factor_coverage(service: str) -> dict[str, dict[str, Any]]:
    sql = """
    WITH latest AS (
        SELECT max(trade_date) AS latest_date
        FROM factor.factor_daily
    )
    SELECT
        daily.factor_name,
        max(daily.trade_date)::text AS latest_available_date,
        count(*) AS coverage_count,
        max(approval.status) AS approval_status
    FROM factor.factor_daily daily
    JOIN latest ON daily.trade_date = latest.latest_date
    LEFT JOIN factor.factor_approval approval
      ON approval.factor_name = daily.factor_name
     AND approval.calc_version = daily.calc_version
    GROUP BY daily.factor_name
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql)
    return {str(row["factor_name"]): dict(row) for row in rows}


def _load_factor_rows(
    trade_date: str,
    factor_names: list[str],
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    if not factor_names:
        return pd.DataFrame(
            columns=["trade_date", "asset_id", "factor_name", "factor_value"]
        )
    parameter_slots = ",".join(["%s"] * len(factor_names))
    sql = f"""
    SELECT trade_date, asset_id, factor_name, factor_value
    FROM factor.factor_daily
    WHERE trade_date = %s
      AND factor_name IN ({parameter_slots})
    ORDER BY asset_id, factor_name
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date, *factor_names])
    return pd.DataFrame(rows)


def _normalize_selected_factors(
    selected_factors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for row in selected_factors:
        factor_name = str(row["factor_name"]).strip()
        direction = str(row["direction"]).strip()
        if not factor_name:
            raise ValueError("factor name must not be empty")
        if direction not in {"higher", "lower"}:
            raise ValueError("factor direction must be higher or lower")
        weight = float(row["weight"])
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError("factor weight must be a positive finite number")
        rows.append(
            {
                "factor_name": factor_name,
                "direction": direction,
                "weight": weight,
            }
        )
    if not rows:
        raise ValueError("at least one factor is required")
    return rows
