import json
from datetime import datetime
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.daily_close_pipeline import resolve_strategy_trade_date
from stock_research.db import connect, fetch_all
from stock_research.run_card import write_run_card
from stock_research.services.universe_service import UniverseResult, get_universe_allowed_ids


SCORE_VERSION = "baseline_rules_v1"
FEATURE_SNAPSHOT_VERSION = "p0_daily:v1"


def score_asset(features: dict[str, float]) -> float:
    score = 0.0
    score += features.get("ret_20d", 0.0) * 100.0
    score += features.get("ret_60d", 0.0) * 80.0
    score += min(features.get("amount_20d_avg", 0.0) / 100000000.0, 5.0)
    score -= max(features.get("volatility_20d", 0.0) - 0.04, 0.0) * 100.0
    score += max(features.get("max_drawdown_20d", 0.0), -0.30) * 20.0
    return round(score, 4)


def risk_tags_for_features(features: dict[str, float]) -> list[str]:
    tags: list[str] = []
    if features.get("volatility_20d", 0.0) >= 0.06:
        tags.append("high_volatility")
    if features.get("max_drawdown_20d", 0.0) <= -0.15:
        tags.append("large_drawdown")
    if features.get("amount_20d_avg", 0.0) < 30000000.0:
        tags.append("low_liquidity")
    return tags


def reasons_for_features(features: dict[str, float]) -> list[str]:
    reasons: list[str] = []
    if features.get("ret_20d", 0.0) > 0:
        reasons.append(f"20日动量为正：{features['ret_20d']:.2%}")
    if features.get("ret_60d", 0.0) > 0:
        reasons.append(f"60日趋势为正：{features['ret_60d']:.2%}")
    if features.get("amount_20d_avg", 0.0) >= 100000000.0:
        reasons.append(f"20日平均成交额较高：{features['amount_20d_avg']:.0f}")
    max_drawdown_20d = features.get("max_drawdown_20d")
    if max_drawdown_20d is not None and max_drawdown_20d > -0.10:
        reasons.append(f"20日回撤可控：{max_drawdown_20d:.2%}")
    while len(reasons) < 3:
        reasons.append("基础流动性和趋势条件满足入池要求")
    return reasons[:3]


def load_feature_matrix(trade_date: str) -> dict[str, dict[str, float]]:
    sql = """
    SELECT asset_id, feature_name, feature_value
    FROM feature_snapshot
    WHERE trade_date = %s
      AND feature_set = 'p0_daily'
      AND feature_version = 'v1'
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [trade_date])

    matrix: dict[str, dict[str, float]] = {}
    for row in rows:
        matrix.setdefault(row["asset_id"], {})[row["feature_name"]] = float(
            row["feature_value"]
        )
    return matrix


def load_trade_status(trade_date: str) -> dict[str, dict[str, object]]:
    sql = """
    SELECT asset_id, is_st, trade_status
    FROM market_daily_bar
    WHERE trade_date = %s
      AND adjust_type = 'hfq'
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [trade_date])

    return {
        row["asset_id"]: {
            "is_st": bool(row["is_st"]),
            "trade_status": str(row["trade_status"]),
        }
        for row in rows
    }


def generate_selection(
    trade_date: str,
    top_n: int = SETTINGS.selection_top_n,
    universe_result: UniverseResult | None = None,
    output_dir: str | Path | None = None,
    use_pipeline_ready_date: bool = True,
) -> list[dict[str, Any]]:
    if use_pipeline_ready_date:
        trade_date = resolve_strategy_trade_date(trade_date)
    matrix = load_feature_matrix(trade_date)
    trade_status = load_trade_status(trade_date)
    allowed_ids = get_universe_allowed_ids(universe_result)
    scored: list[dict[str, Any]] = []

    for asset_id, features in matrix.items():
        if allowed_ids is not None and str(asset_id) not in allowed_ids:
            continue
        status = trade_status.get(asset_id, {})
        # Selection applies hard ST/suspension filters from market_daily_bar.
        if status.get("is_st") is True or str(status.get("trade_status")) != "1":
            continue
        if features.get("amount_20d_avg", 0.0) < 30000000.0:
            continue
        scored.append(
            {
                "asset_id": asset_id,
                "score": score_asset(features),
                "reasons": reasons_for_features(features),
                "risk_tags": risk_tags_for_features(features),
            }
        )

    scored.sort(key=lambda row: (-row["score"], row["asset_id"]))
    run_id = f"{trade_date}:{SCORE_VERSION}:{datetime.now().strftime('%H%M%S')}"

    results: list[dict[str, Any]] = []
    for rank, row in enumerate(scored[:top_n], start=1):
        results.append(
            {
                "run_id": run_id,
                "trade_date": trade_date,
                "asset_id": row["asset_id"],
                "rank": rank,
                "score": row["score"],
                "score_version": SCORE_VERSION,
                "reasons": row["reasons"],
                "risk_tags": row["risk_tags"],
                "feature_snapshot_version": FEATURE_SNAPSHOT_VERSION,
            }
        )
    if output_dir is not None:
        run_card = write_selection_run_card(
            trade_date=trade_date,
            top_n=top_n,
            results=results,
            output_dir=output_dir,
        )
        for row in results:
            row.update(run_card)
    return results


def store_selection(results: list[dict[str, Any]]) -> int:
    if not results:
        return 0

    sql = """
    INSERT INTO selection_result (
        run_id, trade_date, asset_id, rank, score, score_version,
        reasons, risk_tags, feature_snapshot_version
    )
    VALUES (
        %(run_id)s, %(trade_date)s, %(asset_id)s, %(rank)s, %(score)s,
        %(score_version)s, %(reasons)s::jsonb, %(risk_tags)s::jsonb,
        %(feature_snapshot_version)s
    )
    ON CONFLICT (run_id, asset_id) DO UPDATE SET
        rank = EXCLUDED.rank,
        score = EXCLUDED.score,
        reasons = EXCLUDED.reasons,
        risk_tags = EXCLUDED.risk_tags,
        feature_snapshot_version = EXCLUDED.feature_snapshot_version,
        created_at = now()
    """

    rows = []
    for result in results:
        row = dict(result)
        row["reasons"] = json.dumps(row["reasons"], ensure_ascii=False)
        row["risk_tags"] = json.dumps(row["risk_tags"], ensure_ascii=False)
        rows.append(row)

    with connect(SETTINGS.research_service) as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
    return len(results)


def write_selection_run_card(
    *,
    trade_date: str,
    top_n: int,
    results: list[dict[str, Any]],
    output_dir: str | Path,
) -> dict[str, str]:
    top_score = max((float(row["score"]) for row in results), default=None)
    asset_ids = [str(row["asset_id"]) for row in results if row.get("asset_id")]
    return write_run_card(
        output_dir=Path(output_dir) / "run_card",
        run_type="selection",
        run_id=f"selection:{trade_date}:{SCORE_VERSION}:top{top_n}",
        title="Daily Selection",
        config={
            "trade_date": trade_date,
            "top_n": int(top_n),
            "score_version": SCORE_VERSION,
            "feature_snapshot_version": FEATURE_SNAPSHOT_VERSION,
        },
        metrics={
            "selected_count": len(results),
            "top_score": top_score,
        },
        artifact_paths={},
        warnings=["selection_empty"] if not results else [],
        data_coverage={
            "input_start_date": trade_date,
            "input_end_date": trade_date,
            "actual_dates": [trade_date] if results else [],
            "row_count": len(results),
            "asset_count": len(set(asset_ids)),
        },
    )
