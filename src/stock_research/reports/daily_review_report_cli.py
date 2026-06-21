from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_store import load_top_scores
from stock_research.report_run_store import apply_report_run_schema
from stock_research.reports.daily_review_report_workflow import (
    build_daily_review,
    write_daily_review_package,
)

REQUIRED_INPUT_KEYS = (
    "data_readiness",
    "market_review",
    "lhb_review",
    "mid_trend_review",
    "technical_bottleneck_review",
    "holding_reviews",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m stock_research.reports.daily_review_report_cli")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--apply-report-run-schema", action="store_true")
    parser.add_argument("--record-run", action="store_true")
    return parser


def load_daily_review_inputs(trade_date: str) -> dict[str, Any]:
    data_readiness = _load_data_readiness(trade_date)
    top_scores = load_top_scores(trade_date=trade_date, score_version="manual_v1", top_n=5)
    names_by_asset = _load_asset_names([str(row.get("asset_id") or "") for row in top_scores])
    return {
        "data_readiness": data_readiness,
        "market_review": _load_market_review(trade_date, data_readiness),
        "lhb_review": _load_lhb_review(trade_date, data_readiness),
        "mid_trend_review": _load_mid_trend_review(top_scores, names_by_asset),
        "technical_bottleneck_review": _load_technical_bottleneck_review(trade_date),
        "holding_reviews": [],
    }


def run_daily_review_report(
    trade_date: str,
    output_root: str | Path,
    apply_report_run_schema_first: bool = False,
    record_run: bool = False,
) -> dict[str, Any]:
    if apply_report_run_schema_first:
        apply_report_run_schema()

    inputs = load_daily_review_inputs(trade_date)
    validated_inputs = _validate_daily_review_inputs(inputs)
    review = build_daily_review(
        trade_date=trade_date,
        run_id=f"daily_review_v1_{trade_date.replace('-', '')}_2200",
        data_readiness=validated_inputs["data_readiness"],
        market_review=validated_inputs["market_review"],
        lhb_review=validated_inputs["lhb_review"],
        mid_trend_review=validated_inputs["mid_trend_review"],
        technical_bottleneck_review=validated_inputs["technical_bottleneck_review"],
        holding_reviews=validated_inputs["holding_reviews"],
    )
    report_paths = write_daily_review_package(
        review,
        output_root=output_root,
        record_run=record_run,
    )
    return {"review": review, "report_paths": report_paths}


def iter_daily_review_report_path_lines(
    report_paths: dict[str, Any],
    *,
    prefix: str = "daily_review_v1",
):
    for key, value in _flatten_report_paths(report_paths):
        yield f"{prefix}|{key}|{value}"


def _flatten_report_paths(
    report_paths: dict[str, Any],
    parent_key: str = "",
):
    for key, value in report_paths.items():
        full_key = f"{parent_key}.{key}" if parent_key else key
        if isinstance(value, dict):
            yield from _flatten_report_paths(value, full_key)
            continue
        yield full_key, value


def _validate_daily_review_inputs(inputs: Any) -> dict[str, Any]:
    if not isinstance(inputs, dict):
        raise ValueError("daily review inputs must be a dict")

    missing_keys = [key for key in REQUIRED_INPUT_KEYS if key not in inputs]
    if missing_keys:
        raise ValueError(f"daily review inputs missing required keys: {', '.join(missing_keys)}")

    validated_inputs = {key: inputs[key] for key in REQUIRED_INPUT_KEYS}
    if not isinstance(validated_inputs["holding_reviews"], list):
        raise ValueError("daily review inputs holding_reviews must be a list")
    if any(not isinstance(row, dict) for row in validated_inputs["holding_reviews"]):
        raise ValueError("daily review inputs holding_reviews rows must be dict objects")

    for key in REQUIRED_INPUT_KEYS:
        if key == "holding_reviews":
            continue
        if not isinstance(validated_inputs[key], dict):
            raise ValueError(f"daily review inputs {key} must be a dict")

    if all(not validated_inputs[key] for key in REQUIRED_INPUT_KEYS):
        raise ValueError("daily review inputs cannot be an all-empty placeholder bundle")

    return validated_inputs


def _load_data_readiness(trade_date: str) -> dict[str, Any]:
    pipeline_row = _load_pipeline_status_row(trade_date)
    latest_ready_trade_date = str(pipeline_row.get("latest_ready_trade_date") or trade_date)
    bar_count = _count_rows(
        "SELECT count(*) AS row_count FROM market_daily_bar WHERE trade_date = %s",
        [trade_date],
    )
    score_count = _count_rows(
        "SELECT count(*) AS row_count FROM factor.stock_score_daily WHERE trade_date = %s AND score_version = %s",
        [trade_date, "manual_v1"],
    )
    technical_count = _count_rows(
        "SELECT count(*) AS row_count FROM factor.stock_technical_features_daily WHERE trade_date = %s",
        [trade_date],
    )
    pipeline_status = str(pipeline_row.get("pipeline_status") or "unknown")
    return {
        "daily_bars": _build_readiness_entry(
            trade_date=trade_date,
            latest_available_date=trade_date if bar_count > 0 else latest_ready_trade_date,
            status="ready" if bar_count > 0 else "missing",
            summary=f"market_daily_bar rows={bar_count}",
            required=True,
            confidence_impact="core daily bar coverage missing" if bar_count == 0 else "none",
            blocking_modules=["market_review", "mid_trend_review", "technical_bottleneck_review"] if bar_count == 0 else [],
            source_refs=["market_daily_bar"],
        ),
        "top_scores": _build_readiness_entry(
            trade_date=trade_date,
            latest_available_date=trade_date if score_count > 0 else latest_ready_trade_date,
            status="ready" if score_count > 0 else "missing",
            summary=f"factor.stock_score_daily rows={score_count}",
            required=False,
            confidence_impact="mid_trend candidate coverage reduced" if score_count == 0 else "none",
            blocking_modules=["mid_trend_review"] if score_count == 0 else [],
            source_refs=["factor.stock_score_daily"],
        ),
        "technical_features": _build_readiness_entry(
            trade_date=trade_date,
            latest_available_date=trade_date if technical_count > 0 else latest_ready_trade_date,
            status="ready" if technical_count > 0 else "missing",
            summary=f"factor.stock_technical_features_daily rows={technical_count}",
            required=False,
            confidence_impact="technical bottleneck review coverage reduced" if technical_count == 0 else "none",
            blocking_modules=["technical_bottleneck_review"] if technical_count == 0 else [],
            source_refs=["factor.stock_technical_features_daily"],
        ),
        "pipeline_status": _build_readiness_entry(
            trade_date=trade_date,
            latest_available_date=trade_date if pipeline_row else latest_ready_trade_date,
            status="ready" if pipeline_status in {"READY", "DEGRADED_READY"} else "partial",
            summary=(
                f"ops.daily_pipeline_status pipeline_status={pipeline_status} "
                f"daily={pipeline_row.get('daily_status', 'unknown')} "
                f"minute5={pipeline_row.get('minute5_status', 'unknown')} "
                f"deps={pipeline_row.get('deps_status', 'unknown')}"
            ),
            required=False,
            confidence_impact="overall review confidence reduced" if pipeline_status not in {"READY", "DEGRADED_READY"} else "none",
            blocking_modules=["market_review", "lhb_review", "mid_trend_review", "technical_bottleneck_review"]
            if pipeline_status not in {"READY", "DEGRADED_READY"}
            else [],
            source_refs=["ops.daily_pipeline_status"],
        ),
        "lhb_feed": _build_readiness_entry(
            trade_date=trade_date,
            latest_available_date=latest_ready_trade_date,
            status="missing",
            summary="no live LHB feed loader wired in daily_review_v1",
            required=False,
            confidence_impact="LHB conclusion confidence reduced",
            blocking_modules=["lhb_review"],
            source_refs=["daily_review_v1_stub_lhb_loader"],
        ),
    }


def _load_market_review(trade_date: str, data_readiness: dict[str, Any]) -> dict[str, Any]:
    pipeline_status = str(data_readiness["pipeline_status"]["summary"]).lower()
    top_score_count = _extract_count(data_readiness["top_scores"]["summary"])
    technical_count = _extract_count(data_readiness["technical_features"]["summary"])
    if "degraded_ready" in pipeline_status:
        target_exposure = "defensive"
        risk_state = "defensive"
        emotion_state = "mixed"
        trend_environment = "contraction"
    elif "ready" in pipeline_status:
        target_exposure = "neutral"
        risk_state = "normal"
        emotion_state = "neutral"
        trend_environment = "rotation"
    else:
        target_exposure = "defensive"
        risk_state = "high"
        emotion_state = "cold"
        trend_environment = "retreat"
    return {
        "market_regime_score": float(min(100, top_score_count / 100.0 + technical_count / 500.0)),
        "emotion_state": emotion_state,
        "risk_state": risk_state,
        "trend_environment": trend_environment,
        "liquidity_state": "available" if data_readiness["daily_bars"]["status"] == "ready" else "missing",
        "style_bias": "unknown",
        "target_exposure": target_exposure,
        "market_comment": (
            f"{trade_date} review built from daily_bars={data_readiness['daily_bars']['status']}, "
            f"top_scores={data_readiness['top_scores']['status']}, "
            f"technical_features={data_readiness['technical_features']['status']}."
        ),
    }


def _load_lhb_review(trade_date: str, data_readiness: dict[str, Any]) -> dict[str, Any]:
    short_allowed = data_readiness["lhb_feed"]["status"] == "ready"
    return {
        "short_allowed": short_allowed,
        "short_market_state": "manual_review" if short_allowed else "no_trade",
        "emotion_phase": "unknown",
        "lhb_watchlist": [],
        "yesterday_lhb_feedback": [],
        "auction_focus_list": [],
        "allowed_list": [],
        "trial_list": [],
        "defense_list": [],
        "no_trade_list": [
            {
                "rule": "missing_lhb_feed",
                "action": "forbidden",
                "summary": "skip LHB decisions until a live feed is wired",
            }
        ]
        if not short_allowed
        else [],
        "forbidden_actions": ["skip LHB decisions until a live feed is wired"] if not short_allowed else [],
        "as_of_trade_date": trade_date,
    }


def _load_mid_trend_review(
    top_scores: list[dict[str, Any]],
    names_by_asset: dict[str, str],
) -> dict[str, Any]:
    candidate_adds = []
    for idx, row in enumerate(top_scores[:3], start=1):
        asset_id = str(row.get("asset_id") or "")
        candidate_adds.append(
            {
                "asset_id": asset_id,
                "ts_code": "",
                "stock_name": names_by_asset.get(asset_id, asset_id),
                "bucket": "top_score_watch",
                "state": "watch",
                "action": "add_candidate",
                "review_priority": "P1" if idx == 1 else "P2",
                "reason": {"score_total": row.get("score_total"), "rank": row.get("rank")},
                "source_refs": ["factor.stock_score_daily"],
            }
        )
    return {
        "portfolio_health": "stable" if top_scores else "unknown",
        "holding_health_list": [],
        "topn_relation": "top scores loaded" if top_scores else "top scores missing",
        "top50_relation": "top scores loaded" if top_scores else "top scores missing",
        "protection_events": [],
        "candidate_adds": candidate_adds,
        "candidate_reduces": [],
        "candidate_exits": [],
        "rebalance_suggestion": "review top score candidates" if top_scores else "manual_review",
    }


def _load_technical_bottleneck_review(trade_date: str) -> dict[str, Any]:
    rows = _load_top_technical_rows(trade_date, limit=3)
    upgraded_items = [
        {
            "asset_id": str(row.get("asset_id") or ""),
            "ts_code": str(row.get("ts_code") or ""),
            "stock_name": "",
            "from_layer": "S1_observation",
            "to_layer": "S2_prepare",
            "action": "watch",
            "review_priority": "P2",
            "reason": {
                "amount_vs_20d": row.get("amount_vs_20d"),
                "close_position_in_day": row.get("close_position_in_day"),
            },
            "source_refs": ["factor.stock_technical_features_daily"],
        }
        for row in rows
    ]
    return {
        "new_observations": [],
        "upgraded_items": upgraded_items,
        "downgraded_items": [],
        "near_breakout_items": [],
        "failed_breakout_items": [],
        "research_required_items": [],
        "migration_summary": "monitor upgrades only" if upgraded_items else "no technical upgrades loaded",
    }


def _load_pipeline_status_row(trade_date: str) -> dict[str, Any]:
    sql = """
        SELECT trade_date::text AS trade_date, pipeline_status, daily_status, minute5_status,
               deps_status, latest_ready_trade_date::text AS latest_ready_trade_date
        FROM ops.daily_pipeline_status
        WHERE trade_date = %s
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [trade_date])
    return rows[0] if rows else {}


def _count_rows(sql: str, params: list[Any]) -> int:
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, params)
    return int(rows[0].get("row_count") or 0) if rows else 0


def _load_asset_names(asset_ids: list[str]) -> dict[str, str]:
    cleaned = [asset_id for asset_id in asset_ids if asset_id]
    if not cleaned:
        return {}
    sql = """
        SELECT asset_id, name
        FROM core.asset_master
        WHERE asset_id = ANY(%s)
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [cleaned])
    return {str(row.get("asset_id") or ""): str(row.get("name") or "") for row in rows}


def _load_top_technical_rows(trade_date: str, *, limit: int) -> list[dict[str, Any]]:
    sql = """
        SELECT asset_id, ts_code, amount_vs_20d, close_position_in_day
        FROM factor.stock_technical_features_daily
        WHERE trade_date = %s
        ORDER BY amount_vs_20d DESC NULLS LAST, close_position_in_day DESC NULLS LAST, asset_id
        LIMIT %s
    """
    with connect(SETTINGS.research_service) as conn:
        return fetch_all(conn, sql, [trade_date, limit])


def _build_readiness_entry(
    *,
    trade_date: str,
    latest_available_date: str,
    status: str,
    summary: str,
    required: bool,
    confidence_impact: str,
    blocking_modules: list[str],
    source_refs: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "required": required,
        "summary": summary,
        "freshness": {
            "latest_available_date": latest_available_date,
            "expected_date": trade_date,
            "is_fresh": latest_available_date == trade_date,
            "max_allowed_lag_days": 0,
        },
        "confidence_impact": confidence_impact,
        "blocking_modules": blocking_modules,
        "source_refs": source_refs,
    }


def _extract_count(summary: str) -> int:
    marker = "rows="
    if marker not in summary:
        return 0
    raw = summary.split(marker, 1)[1].split()[0]
    try:
        return int(raw)
    except ValueError:
        return 0


def main(runner=run_daily_review_report) -> None:
    args = build_parser().parse_args()
    result = runner(
        trade_date=args.trade_date,
        output_root=Path(args.output_root),
        apply_report_run_schema_first=args.apply_report_run_schema,
        record_run=args.record_run,
    )
    for line in iter_daily_review_report_path_lines(result["report_paths"]):
        print(line)


if __name__ == "__main__":
    main()
