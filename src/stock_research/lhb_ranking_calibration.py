from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


LHB_SELECTION_SCORE_V2 = "lhb_selection_score_v2"
LHB_CALIBRATION_FEATURES = [
    "lhb_net_buy_amount",
    "lhb_net_buy_ratio",
    "institution_net_buy",
    "top_seat_concentration",
    "repeat_on_list_count_3d",
    "lhb_after_limit_up",
    "lhb_after_break_limit",
    "lhb_after_reversal",
    "lhb_one_day_pump_risk",
    "high_to_close_drawdown",
]
FUTURE_OR_OUTCOME_PREFIXES = (
    "future_",
    "entry_",
    "exit_",
    "realized_",
    "auction_",
    "confirmation_",
    "fill_",
    "pnl",
)


@dataclass(frozen=True)
class Formula:
    formula_id: str
    weights: dict[str, float]


FORMULAS = [
    Formula("capital_balanced", {"net_ratio": 35, "net_amount": 20, "institution": 15, "repeat": 5, "after_limit": 8, "reversal": 3, "concentration": -8, "pump": -10, "drawdown": -15, "after_break": -12}),
    Formula("capital_concentrated", {"net_ratio": 45, "net_amount": 25, "institution": 10, "repeat": 3, "after_limit": 7, "reversal": 2, "concentration": -10, "pump": -8, "drawdown": -12, "after_break": -14}),
    Formula("institution_quality", {"net_ratio": 30, "net_amount": 15, "institution": 25, "repeat": 6, "after_limit": 8, "reversal": 3, "concentration": -10, "pump": -8, "drawdown": -15, "after_break": -12}),
    Formula("drawdown_control", {"net_ratio": 30, "net_amount": 15, "institution": 15, "repeat": 5, "after_limit": 8, "reversal": 2, "concentration": -10, "pump": -15, "drawdown": -30, "after_break": -18}),
    Formula("pump_control", {"net_ratio": 35, "net_amount": 18, "institution": 12, "repeat": 5, "after_limit": 8, "reversal": 2, "concentration": -8, "pump": -25, "drawdown": -18, "after_break": -15}),
    Formula("repeat_structure", {"net_ratio": 30, "net_amount": 15, "institution": 12, "repeat": 12, "after_limit": 12, "reversal": 5, "concentration": -10, "pump": -12, "drawdown": -18, "after_break": -18}),
    Formula("low_concentration", {"net_ratio": 32, "net_amount": 18, "institution": 15, "repeat": 5, "after_limit": 8, "reversal": 2, "concentration": -22, "pump": -10, "drawdown": -18, "after_break": -15}),
    Formula("defensive_balanced", {"net_ratio": 28, "net_amount": 15, "institution": 18, "repeat": 6, "after_limit": 7, "reversal": 2, "concentration": -15, "pump": -18, "drawdown": -25, "after_break": -20}),
]


def validate_lhb_calibration_features(feature_columns: list[str]) -> None:
    invalid = [
        column
        for column in feature_columns
        if str(column).lower().startswith(FUTURE_OR_OUTCOME_PREFIXES)
    ]
    if invalid:
        raise ValueError(f"future/outcome feature is not allowed: {', '.join(invalid)}")
    unknown = sorted(set(feature_columns).difference(LHB_CALIBRATION_FEATURES))
    if unknown:
        raise ValueError(f"unknown LHB calibration feature: {', '.join(unknown)}")


def chronological_lhb_calibration_split(
    frame: pd.DataFrame,
    *,
    holdout_fraction: float = 0.20,
    min_holdout_dates: int = 20,
    fold_count: int = 3,
) -> dict[str, Any]:
    dates = sorted(pd.to_datetime(frame["trade_date"], errors="coerce").dropna().dt.strftime("%Y-%m-%d").unique())
    if len(dates) < max(min_holdout_dates + fold_count + 1, 10):
        raise ValueError("insufficient chronological dates for LHB calibration")
    holdout_count = max(int(min_holdout_dates), int(math.ceil(len(dates) * float(holdout_fraction))))
    holdout_count = min(holdout_count, len(dates) - (fold_count + 1))
    preholdout_dates = dates[:-holdout_count]
    holdout_dates = dates[-holdout_count:]
    block = max(1, len(preholdout_dates) // (fold_count + 1))
    folds: list[tuple[list[str], list[str]]] = []
    for index in range(fold_count):
        train_end = min(block * (index + 1), len(preholdout_dates) - 1)
        validation_end = len(preholdout_dates) if index == fold_count - 1 else min(block * (index + 2), len(preholdout_dates))
        train_dates = preholdout_dates[:train_end]
        validation_dates = preholdout_dates[train_end:validation_end]
        if train_dates and validation_dates:
            folds.append((train_dates, validation_dates))
    if not folds:
        raise ValueError("unable to build chronological LHB calibration folds")
    return {
        "preholdout_dates": preholdout_dates,
        "holdout_dates": holdout_dates,
        "folds": folds,
    }


def evaluate_lhb_holdout_gates(
    *,
    baseline: dict[str, float],
    candidate: dict[str, float],
    candidate_rank6_10: dict[str, float],
    monthly_excess_concentration: float,
) -> dict[str, bool]:
    return_gate = candidate["mean_future_5d_return"] > baseline["mean_future_5d_return"]
    up_rate_gate = candidate["up_rate_1d"] >= baseline["up_rate_1d"] - 0.02
    drawdown_gate = (
        candidate["mean_future_5d_max_drawdown"]
        >= baseline["mean_future_5d_max_drawdown"] - 0.005
    )
    rank_separation_gate = not (
        candidate["mean_future_5d_return"] < candidate_rank6_10["mean_future_5d_return"]
        and candidate["up_rate_1d"] < candidate_rank6_10["up_rate_1d"]
    )
    month_concentration_gate = float(monthly_excess_concentration) <= 0.40
    gates = {
        "return_gate": bool(return_gate),
        "up_rate_gate": bool(up_rate_gate),
        "drawdown_gate": bool(drawdown_gate),
        "rank_separation_gate": bool(rank_separation_gate),
        "month_concentration_gate": bool(month_concentration_gate),
    }
    gates["promote"] = all(gates.values())
    return gates


def build_lhb_ranking_calibration_v2(
    *,
    eligible_candidates: pd.DataFrame,
    output_dir: str | Path,
    holdout_fraction: float = 0.20,
    min_holdout_dates: int = 20,
    fold_count: int = 3,
) -> dict[str, Any]:
    validate_lhb_calibration_features(LHB_CALIBRATION_FEATURES)
    frame = _normalize_calibration_frame(eligible_candidates)
    split = chronological_lhb_calibration_split(
        frame,
        holdout_fraction=holdout_fraction,
        min_holdout_dates=min_holdout_dates,
        fold_count=fold_count,
    )
    scored = _attach_formula_scores(frame)
    preholdout_metrics = _walk_forward_formula_metrics(scored, split["folds"])
    passing = preholdout_metrics[
        preholdout_metrics["validation_up_rate_gate"]
        & preholdout_metrics["validation_drawdown_gate"]
    ]
    selection_pool = passing if not passing.empty else preholdout_metrics
    winner = selection_pool.sort_values(
        ["mean_validation_future_5d_return", "formula_id"],
        ascending=[False, True],
        kind="stable",
    ).iloc[0]
    formula_id = str(winner["formula_id"])
    holdout = scored[scored["trade_date"].isin(split["holdout_dates"])].copy()
    baseline_top5 = _ranked_slice(holdout, score_column="selection_score", start_rank=1, end_rank=5)
    candidate_top5 = _ranked_slice(holdout, score_column=f"formula_score__{formula_id}", start_rank=1, end_rank=5)
    candidate_rank6_10 = _ranked_slice(holdout, score_column=f"formula_score__{formula_id}", start_rank=6, end_rank=10)
    baseline_metrics = _selection_metrics(baseline_top5)
    candidate_metrics = _selection_metrics(candidate_top5)
    rank6_10_metrics = _selection_metrics(candidate_rank6_10)
    if baseline_metrics["sample_count"] == 0 or candidate_metrics["sample_count"] == 0:
        raise ValueError("holdout outcome coverage is zero; verify candidate and daily-bar keys")
    monthly_concentration = _monthly_excess_concentration(
        baseline_top5=baseline_top5,
        candidate_top5=candidate_top5,
    )
    gates = evaluate_lhb_holdout_gates(
        baseline=baseline_metrics,
        candidate=candidate_metrics,
        candidate_rank6_10=rank6_10_metrics,
        monthly_excess_concentration=monthly_concentration,
    )

    selected_score_column = f"formula_score__{formula_id}"
    shadow = scored.copy()
    shadow["selection_score_v2"] = shadow[selected_score_column]
    shadow["baseline_rank"] = shadow.groupby("trade_date")["selection_score"].rank(
        method="first", ascending=False
    ).astype(int)
    shadow["selection_rank_v2"] = shadow.groupby("trade_date")["selection_score_v2"].rank(
        method="first", ascending=False
    ).astype(int)
    shadow["score_version"] = LHB_SELECTION_SCORE_V2
    shadow["formula_id"] = formula_id
    shadow["promotion_status"] = "promoted" if gates["promote"] else "shadow_only"
    shadow_columns = [
        "trade_date",
        "ts_code",
        "eligibility_contract_version",
        "selection_score",
        "baseline_rank",
        "selection_score_v2",
        "selection_rank_v2",
        "score_version",
        "formula_id",
        "promotion_status",
        "future_1d_return",
        "future_5d_return",
        "future_5d_max_drawdown",
    ]
    shadow = shadow.reindex(columns=shadow_columns).sort_values(
        ["trade_date", "selection_rank_v2", "ts_code"], kind="stable"
    ).reset_index(drop=True)

    report = {
        "score_version": LHB_SELECTION_SCORE_V2,
        "selected_formula_id": formula_id,
        "selected_formula_weights": next(formula.weights for formula in FORMULAS if formula.formula_id == formula_id),
        "selection_status": "preholdout_gate_passed" if not passing.empty else "no_preholdout_formula_passed_all_validation_gates",
        "promotion_status": "promoted" if gates["promote"] else "shadow_only",
        "holdout_window": {"start": split["holdout_dates"][0], "end": split["holdout_dates"][-1], "date_count": len(split["holdout_dates"])},
        "eligible_universe_rows": int(len(frame)),
        "eligible_universe_dates": int(frame["trade_date"].nunique()),
        "missing_feature_coverage": _missing_feature_coverage(frame),
        "baseline_holdout": baseline_metrics,
        "candidate_holdout": candidate_metrics,
        "candidate_rank6_10_holdout": rank6_10_metrics,
        "monthly_excess_concentration": monthly_concentration,
        "gates": gates,
    }

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "shadow_scores": str(out / "lhb_selection_score_v2_shadow.csv"),
        "formula_metrics": str(out / "lhb_selection_score_v2_formula_metrics.csv"),
        "holdout_report": str(out / "lhb_selection_score_v2_holdout_report.json"),
        "markdown_report": str(out / "lhb_selection_score_v2_holdout_report.md"),
    }
    shadow.to_csv(paths["shadow_scores"], index=False)
    preholdout_metrics.to_csv(paths["formula_metrics"], index=False)
    Path(paths["holdout_report"]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(paths["markdown_report"]).write_text(_calibration_markdown(report), encoding="utf-8")
    return {
        "shadow_scores": shadow,
        "formula_metrics": preholdout_metrics,
        "holdout_report": report,
        "paths": paths,
    }


def run_lhb_ranking_calibration_v2_from_db(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    adjust_type: str = "hfq",
    service: str | None = None,
) -> dict[str, Any]:
    from stock_research.config import SETTINGS
    from stock_research.db import connect, fetch_all
    from stock_research.lhb_data import build_lhb_full_market_pool_backtest_v1

    db_service = service or SETTINGS.research_service
    with connect(db_service) as conn:
        lhb_rows = fetch_all(
            conn,
            """
            WITH same_day_top AS (
                SELECT trade_date, ts_code, max(NULLIF(name, '')) AS stock_name,
                       max(pct_change) AS pct_chg
                FROM market.lhb_top_list_daily
                WHERE trade_date BETWEEN %s::date AND %s::date
                GROUP BY trade_date, ts_code
            )
            SELECT
                f.trade_date::text AS trade_date,
                f.ts_code,
                t.stock_name,
                CASE WHEN t.stock_name IS NULL THEN 'unavailable' ELSE 'lhb_same_day_name' END AS stock_name_source,
                t.pct_chg,
                a.name AS current_name,
                a.list_date::text AS list_date,
                s.is_st AS stored_is_st,
                CASE
                    WHEN s.source LIKE '%%status_quality=same_day_lhb_name' THEN 'trusted'
                    WHEN s.source LIKE '%%status_quality=daily_bar' THEN 'trusted'
                    ELSE 'unverified'
                END AS stored_status_quality,
                tech.amount_vs_20d,
                tech.high_to_close_drawdown,
                f.on_lhb,
                f.lhb_reason,
                f.lhb_net_buy_amount,
                f.lhb_net_buy_ratio,
                f.institution_net_buy,
                f.top_seat_concentration,
                f.repeat_on_list_count_3d,
                f.repeat_on_list_count_5d,
                f.lhb_after_limit_up,
                f.lhb_after_break_limit,
                f.lhb_after_reversal,
                f.lhb_one_day_pump_risk
            FROM factor.lhb_event_features_daily f
            LEFT JOIN same_day_top t ON t.trade_date = f.trade_date AND t.ts_code = f.ts_code
            LEFT JOIN core.asset_master a ON a.ts_code = f.ts_code
            LEFT JOIN core.asset_status_daily s ON s.trade_date = f.trade_date AND s.asset_id = a.asset_id
            LEFT JOIN factor.stock_technical_features_daily tech
              ON tech.trade_date = f.trade_date
             AND tech.asset_id = a.asset_id
             AND tech.adjust_type = %s
            WHERE f.trade_date BETWEEN %s::date AND %s::date
            ORDER BY f.trade_date, f.ts_code
            """,
            [start_date, end_date, adjust_type, start_date, end_date],
        )
        daily_rows = fetch_all(
            conn,
            """
            SELECT
                b.trade_date::text AS trade_date,
                COALESCE(a.ts_code, b.asset_id) AS ts_code,
                b.close,
                b.low,
                b.preclose,
                b.pct_chg,
                b.is_st AS stored_is_st,
                CASE WHEN b.is_st THEN 'trusted' ELSE 'unverified' END AS stored_status_quality
            FROM market_daily_bar b
            LEFT JOIN core.asset_master a ON a.asset_id = b.asset_id
            WHERE b.trade_date BETWEEN %s::date AND (%s::date + INTERVAL '20 days')
              AND b.adjust_type = %s
              AND COALESCE(b.trade_status, '') <> '停牌'
            ORDER BY b.asset_id, b.trade_date
            """,
            [start_date, end_date, adjust_type],
        )
    pool = build_lhb_full_market_pool_backtest_v1(
        lhb_features=pd.DataFrame(lhb_rows),
        daily_bars=pd.DataFrame(daily_rows),
        start_date=start_date,
        end_date=end_date,
        top_n_values=[10],
        output_dir=output_dir,
        pool_mode="raw_lhb_positive",
    )
    result = build_lhb_ranking_calibration_v2(
        eligible_candidates=pool["eligible_candidates"],
        output_dir=output_dir,
    )
    result["pool_paths"] = pool["paths"]
    return result


def _normalize_calibration_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "trade_date",
        "ts_code",
        "backtest_entry_eligible",
        "eligibility_contract_version",
        "selection_score",
        "future_1d_return",
        "future_5d_return",
        "future_5d_max_drawdown",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"missing LHB calibration columns: {', '.join(missing)}")
    result = frame.copy()
    if not result["backtest_entry_eligible"].fillna(False).astype(bool).all():
        raise ValueError("LHB calibration universe contains ineligible candidates")
    if not result["eligibility_contract_version"].fillna("").eq("lhb_eligibility_v2").all():
        raise ValueError("LHB calibration universe has invalid eligibility contract version")
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    result["ts_code"] = result["ts_code"].fillna("").astype(str)
    result = result.dropna(subset=["trade_date"]).drop_duplicates(["trade_date", "ts_code"], keep="last")
    for column in ["selection_score", *LHB_CALIBRATION_FEATURES, "future_1d_return", "future_5d_return", "future_5d_max_drawdown"]:
        if column not in result.columns:
            result[column] = pd.NA
    return result.sort_values(["trade_date", "ts_code"], kind="stable").reset_index(drop=True)


def _attach_formula_scores(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    by_date = result.groupby("trade_date", sort=False)
    result["_net_ratio"] = by_date["lhb_net_buy_ratio"].rank(pct=True).fillna(0.0)
    result["_net_amount"] = by_date["lhb_net_buy_amount"].rank(pct=True).fillna(0.0)
    result["_institution"] = by_date["institution_net_buy"].rank(pct=True).fillna(0.0)
    result["_repeat"] = pd.to_numeric(result["repeat_on_list_count_3d"], errors="coerce").fillna(0.0).clip(0, 3) / 3.0
    result["_after_limit"] = _bool_series(result["lhb_after_limit_up"]).astype(float)
    result["_after_break"] = _bool_series(result["lhb_after_break_limit"]).astype(float)
    result["_reversal"] = _bool_series(result["lhb_after_reversal"]).astype(float)
    result["_concentration"] = pd.to_numeric(result["top_seat_concentration"], errors="coerce").fillna(0.0).clip(0, 1)
    result["_pump"] = pd.to_numeric(result["lhb_one_day_pump_risk"], errors="coerce").fillna(0.0).clip(0, 1)
    result["_drawdown"] = pd.to_numeric(result["high_to_close_drawdown"], errors="coerce").fillna(0.0).clip(0, 1)
    feature_map = {
        "net_ratio": "_net_ratio",
        "net_amount": "_net_amount",
        "institution": "_institution",
        "repeat": "_repeat",
        "after_limit": "_after_limit",
        "after_break": "_after_break",
        "reversal": "_reversal",
        "concentration": "_concentration",
        "pump": "_pump",
        "drawdown": "_drawdown",
    }
    for formula in FORMULAS:
        score = pd.Series(0.0, index=result.index)
        for feature, weight in formula.weights.items():
            score += result[feature_map[feature]] * float(weight)
        result[f"formula_score__{formula.formula_id}"] = score
    return result


def _walk_forward_formula_metrics(scored: pd.DataFrame, folds: list[tuple[list[str], list[str]]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for formula in FORMULAS:
        formula_metrics: list[dict[str, float]] = []
        baseline_metrics: list[dict[str, float]] = []
        for _, validation_dates in folds:
            validation = scored[scored["trade_date"].isin(validation_dates)]
            formula_metrics.append(_selection_metrics(_ranked_slice(validation, score_column=f"formula_score__{formula.formula_id}", start_rank=1, end_rank=5)))
            baseline_metrics.append(_selection_metrics(_ranked_slice(validation, score_column="selection_score", start_rank=1, end_rank=5)))
        candidate = _average_metrics(formula_metrics)
        baseline = _average_metrics(baseline_metrics)
        rows.append(
            {
                "formula_id": formula.formula_id,
                "fold_count": len(formula_metrics),
                "mean_validation_future_5d_return": candidate["mean_future_5d_return"],
                "baseline_validation_future_5d_return": baseline["mean_future_5d_return"],
                "validation_excess_future_5d_return": candidate["mean_future_5d_return"] - baseline["mean_future_5d_return"],
                "validation_up_rate_1d": candidate["up_rate_1d"],
                "baseline_validation_up_rate_1d": baseline["up_rate_1d"],
                "validation_drawdown": candidate["mean_future_5d_max_drawdown"],
                "baseline_validation_drawdown": baseline["mean_future_5d_max_drawdown"],
                "validation_up_rate_gate": candidate["up_rate_1d"] >= baseline["up_rate_1d"] - 0.02,
                "validation_drawdown_gate": candidate["mean_future_5d_max_drawdown"] >= baseline["mean_future_5d_max_drawdown"] - 0.005,
            }
        )
    return pd.DataFrame(rows)


def _ranked_slice(frame: pd.DataFrame, *, score_column: str, start_rank: int, end_rank: int) -> pd.DataFrame:
    ranked = frame.sort_values(["trade_date", score_column, "ts_code"], ascending=[True, False, True], kind="stable").copy()
    ranked["_rank"] = ranked.groupby("trade_date").cumcount() + 1
    return ranked[ranked["_rank"].between(start_rank, end_rank)].copy()


def _selection_metrics(frame: pd.DataFrame) -> dict[str, float]:
    future_1d = pd.to_numeric(frame.get("future_1d_return"), errors="coerce")
    future_5d = pd.to_numeric(frame.get("future_5d_return"), errors="coerce")
    drawdown = pd.to_numeric(frame.get("future_5d_max_drawdown"), errors="coerce")
    return {
        "sample_count": int(future_5d.notna().sum()),
        "mean_future_5d_return": float(future_5d.mean()) if future_5d.notna().any() else 0.0,
        "up_rate_1d": float(future_1d.gt(0).mean()) if future_1d.notna().any() else 0.0,
        "mean_future_5d_max_drawdown": float(drawdown.mean()) if drawdown.notna().any() else 0.0,
    }


def _average_metrics(metrics: list[dict[str, float]]) -> dict[str, float]:
    keys = ["mean_future_5d_return", "up_rate_1d", "mean_future_5d_max_drawdown"]
    return {key: sum(item[key] for item in metrics) / len(metrics) for key in keys}


def _monthly_excess_concentration(*, baseline_top5: pd.DataFrame, candidate_top5: pd.DataFrame) -> float:
    def daily(frame: pd.DataFrame, value_name: str) -> pd.DataFrame:
        values = frame.groupby("trade_date", as_index=False)["future_5d_return"].mean()
        return values.rename(columns={"future_5d_return": value_name})

    merged = daily(candidate_top5, "candidate").merge(daily(baseline_top5, "baseline"), on="trade_date", how="inner")
    merged["month"] = merged["trade_date"].astype(str).str[:7]
    merged["excess"] = merged["candidate"] - merged["baseline"]
    positive = merged.groupby("month")["excess"].sum().clip(lower=0.0)
    total = float(positive.sum())
    return float(positive.max() / total) if total > 0.0 else 1.0


def _missing_feature_coverage(frame: pd.DataFrame) -> dict[str, float]:
    return {
        column: float(frame[column].isna().mean()) if column in frame.columns else 1.0
        for column in LHB_CALIBRATION_FEATURES
    }


def _bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.fillna(False).map(lambda value: str(value).strip().lower() in {"true", "1", "yes"})


def _calibration_markdown(report: dict[str, Any]) -> str:
    gates = report["gates"]
    return "\n".join(
        [
            "# LHB Selection Score v2 Holdout Report",
            "",
            f"- Formula: {report['selected_formula_id']}",
            f"- Promotion: {report['promotion_status']}",
            f"- Holdout: {report['holdout_window']['start']} to {report['holdout_window']['end']}",
            f"- Eligible rows: {report['eligible_universe_rows']}",
            "",
            "## Gates",
            "",
            *[f"- {name}: {value}" for name, value in gates.items()],
            "",
            "## Holdout Metrics",
            "",
            f"- Baseline: `{json.dumps(report['baseline_holdout'], ensure_ascii=False)}`",
            f"- Candidate: `{json.dumps(report['candidate_holdout'], ensure_ascii=False)}`",
            f"- Candidate ranks 6-10: `{json.dumps(report['candidate_rank6_10_holdout'], ensure_ascii=False)}`",
            f"- Monthly excess concentration: {report['monthly_excess_concentration']:.6f}",
            "",
        ]
    )
