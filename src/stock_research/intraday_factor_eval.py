from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
from stock_research.factor_eval.multi_horizon import generate_multi_horizon_report
from stock_research.intraday_features import INTRADAY_FEATURE_CALC_VERSION


DEFAULT_STOCK_INTRADAY_FACTOR_FEATURES = [
    "intraday_return",
    "morning_return",
    "afternoon_return",
    "last_30m_return",
    "intraday_volatility_5min",
    "max_intraday_drawdown",
    "close_position_in_day",
    "amount_front_1h_ratio",
    "amount_tail_1h_ratio",
    "close_to_vwap",
]

DEFAULT_INDUSTRY_INTRADAY_FACTOR_FEATURES = [
    "industry_intraday_return_median",
    "industry_up_ratio",
    "industry_tail_strength_median",
    "industry_intraday_volatility_median",
    "industry_amount_tail_1h_ratio_median",
]

DEFAULT_INTRADAY_FACTOR_FEATURES = [
    *DEFAULT_STOCK_INTRADAY_FACTOR_FEATURES,
    *DEFAULT_INDUSTRY_INTRADAY_FACTOR_FEATURES,
]


def classify_intraday_factor_signal(
    *,
    mean_rank_ic: float | None,
    rank_icir: float | None,
    mean_top_bottom_spread: float | None,
    ic_count: int,
    min_abs_rank_ic: float = 0.02,
    min_abs_rank_icir: float = 0.2,
    min_ic_count: int = 20,
) -> str:
    if ic_count < min_ic_count:
        return "insufficient_sample"
    rank_ic = _float_or_none(mean_rank_ic)
    rank_ir = _float_or_none(rank_icir)
    spread = _float_or_none(mean_top_bottom_spread)
    if rank_ic is None:
        return "reject"
    if abs(rank_ic) < min_abs_rank_ic:
        return "reject"
    if rank_ir is not None and abs(rank_ir) < min_abs_rank_icir:
        return "reject"
    if rank_ic > 0 and (spread is None or spread >= 0):
        return "candidate_long"
    if rank_ic < 0 and (spread is None or spread <= 0):
        return "candidate_short_or_risk_filter"
    return "mixed_direction"


def evaluate_intraday_factor_frames(
    *,
    factors_by_feature: dict[str, pd.DataFrame],
    returns: pd.DataFrame,
    horizons: list[int],
    quantiles: int = 5,
    top_n: int = 30,
    min_abs_rank_ic: float = 0.02,
    min_abs_rank_icir: float = 0.2,
    min_ic_count: int = 20,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for feature_name, factors in sorted(factors_by_feature.items()):
        if factors.empty:
            continue
        available_horizons = [
            horizon
            for horizon in horizons
            if f"forward_return_{int(horizon)}d" in returns.columns
        ]
        if not available_horizons:
            continue
        report = generate_multi_horizon_report(
            factors=factors,
            returns=returns,
            factor_name=feature_name,
            horizons=available_horizons,
            quantiles=quantiles,
            top_n=top_n,
        )
        rows.extend(
            _summarize_feature_report(
                feature_name,
                report,
                min_abs_rank_ic=min_abs_rank_ic,
                min_abs_rank_icir=min_abs_rank_icir,
                min_ic_count=min_ic_count,
            )
        )
    result = pd.DataFrame(rows)
    if result.empty:
        return pd.DataFrame(
            columns=[
                "feature_name",
                "horizon",
                "sample_rows",
                "date_count",
                "ic_count",
                "mean_ic",
                "icir",
                "mean_rank_ic",
                "rank_icir",
                "mean_top_bottom_spread",
                "mean_turnover",
                "recommendation",
            ]
        )
    return result.sort_values(
        ["recommendation", "horizon", "feature_name"],
        kind="stable",
    ).reset_index(drop=True)


def load_stock_intraday_factor_frame(
    *,
    feature_name: str,
    start_date: str,
    end_date: str,
    freq: str = "5min",
    adjust_type: str = "raw",
    calc_version: str = INTRADAY_FEATURE_CALC_VERSION,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT trade_date, asset_id, feature_value AS factor_value
    FROM factor.stock_intraday_features_daily
    WHERE feature_name = %s
      AND freq = %s
      AND adjust_type = %s
      AND calc_version = %s
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            sql,
            [feature_name, freq, adjust_type, calc_version, start_date, end_date],
        )
    return _numeric_frame(pd.DataFrame(rows), ["factor_value"])


def load_industry_intraday_factor_frame(
    *,
    feature_name: str,
    start_date: str,
    end_date: str,
    freq: str = "5min",
    adjust_type: str = "raw",
    industry_system: str = "csrc",
    calc_version: str = INTRADAY_FEATURE_CALC_VERSION,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    WITH membership AS (
        SELECT DISTINCT ON (asset_id)
            asset_id,
            industry_code
        FROM core.industry_membership
        WHERE industry_system = %s
          AND start_date <= %s
          AND (end_date IS NULL OR %s < end_date)
        ORDER BY asset_id, level DESC, start_date DESC
    )
    SELECT
        f.trade_date,
        m.asset_id,
        f.feature_value AS factor_value
    FROM factor.industry_intraday_features_daily f
    JOIN membership m
      ON m.industry_code = f.industry_code
    WHERE f.feature_name = %s
      AND f.freq = %s
      AND f.adjust_type = %s
      AND f.industry_system = %s
      AND f.calc_version = %s
      AND f.trade_date BETWEEN %s AND %s
    ORDER BY f.trade_date, m.asset_id
    """
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            sql,
            [
                industry_system,
                end_date,
                end_date,
                feature_name,
                freq,
                adjust_type,
                industry_system,
                calc_version,
                start_date,
                end_date,
            ],
        )
    return _numeric_frame(pd.DataFrame(rows), ["factor_value"])


def load_intraday_factor_frames(
    *,
    feature_names: list[str],
    start_date: str,
    end_date: str,
    freq: str = "5min",
    adjust_type: str = "raw",
    industry_system: str = "csrc",
    calc_version: str = INTRADAY_FEATURE_CALC_VERSION,
    service: str = SETTINGS.research_service,
) -> dict[str, pd.DataFrame]:
    result = {}
    for feature_name in feature_names:
        if feature_name in DEFAULT_INDUSTRY_INTRADAY_FACTOR_FEATURES:
            frame = load_industry_intraday_factor_frame(
                feature_name=feature_name,
                start_date=start_date,
                end_date=end_date,
                freq=freq,
                adjust_type=adjust_type,
                industry_system=industry_system,
                calc_version=calc_version,
                service=service,
            )
        else:
            frame = load_stock_intraday_factor_frame(
                feature_name=feature_name,
                start_date=start_date,
                end_date=end_date,
                freq=freq,
                adjust_type=adjust_type,
                calc_version=calc_version,
                service=service,
            )
        result[feature_name] = frame
    return result


def load_forward_returns_for_intraday_eval(
    *,
    start_date: str,
    end_date: str,
    horizons: list[int],
    label_set: str = "forward_return",
    label_version: str = "v1",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    if not horizons:
        raise ValueError("horizons must not be empty")
    sql = """
    SELECT
        trade_date,
        asset_id,
        horizon,
        label_value AS forward_return
    FROM label_snapshot
    WHERE label_set = %s
      AND label_version = %s
      AND horizon = ANY(%s)
      AND label_name IN ('forward_return', 'future_return')
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id, horizon
    """
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            sql,
            [label_set, label_version, horizons, start_date, end_date],
        )
    long_frame = pd.DataFrame(rows)
    columns = ["trade_date", "asset_id", *[f"forward_return_{int(h)}d" for h in horizons]]
    if long_frame.empty:
        return pd.DataFrame(columns=columns)
    returns = (
        long_frame.pivot_table(
            index=["trade_date", "asset_id"],
            columns="horizon",
            values="forward_return",
            aggfunc="last",
        )
        .reset_index()
        .rename(columns={horizon: f"forward_return_{int(horizon)}d" for horizon in horizons})
        .sort_values(["trade_date", "asset_id"])
        .reset_index(drop=True)
    )
    return _numeric_frame(returns, [f"forward_return_{int(h)}d" for h in horizons])


def run_intraday_factor_eval(
    *,
    start_date: str,
    end_date: str,
    horizons: list[int],
    output_dir: str | Path,
    feature_names: list[str] | None = None,
    freq: str = "5min",
    adjust_type: str = "raw",
    industry_system: str = "csrc",
    calc_version: str = INTRADAY_FEATURE_CALC_VERSION,
    quantiles: int = 5,
    top_n: int = 30,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    selected_features = feature_names or DEFAULT_INTRADAY_FACTOR_FEATURES
    factors_by_feature = load_intraday_factor_frames(
        feature_names=selected_features,
        start_date=start_date,
        end_date=end_date,
        freq=freq,
        adjust_type=adjust_type,
        industry_system=industry_system,
        calc_version=calc_version,
        service=service,
    )
    returns = load_forward_returns_for_intraday_eval(
        start_date=start_date,
        end_date=end_date,
        horizons=horizons,
        service=service,
    )
    summary = evaluate_intraday_factor_frames(
        factors_by_feature=factors_by_feature,
        returns=returns,
        horizons=horizons,
        quantiles=quantiles,
        top_n=top_n,
    )
    paths = write_intraday_factor_eval_report(
        summary=summary,
        output_dir=output_dir,
        start_date=start_date,
        end_date=end_date,
        horizons=horizons,
    )
    return {
        "summary": summary,
        "paths": paths,
        "features": selected_features,
        "horizons": horizons,
    }


def write_intraday_factor_eval_report(
    *,
    summary: pd.DataFrame,
    output_dir: str | Path,
    start_date: str,
    end_date: str,
    horizons: list[int],
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    summary_csv_path = output_path / "intraday_factor_eval_summary.csv"
    markdown_path = output_path / "intraday_factor_eval.md"
    summary.to_csv(summary_csv_path, index=False)
    markdown_path.write_text(
        format_intraday_factor_markdown(
            summary=summary,
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
        ),
        encoding="utf-8",
    )
    return {
        "summary_csv_path": str(summary_csv_path),
        "markdown_path": str(markdown_path),
    }


def format_intraday_factor_markdown(
    *,
    summary: pd.DataFrame,
    start_date: str,
    end_date: str,
    horizons: list[int],
) -> str:
    lines = [
        "# Intraday Factor Evaluation",
        "",
        f"- date_range: {start_date} to {end_date}",
        f"- horizons: {','.join(str(int(value)) for value in horizons)}",
        "",
    ]
    if summary.empty:
        lines.append("No evaluable intraday factor rows.")
        return "\n".join(lines) + "\n"

    display = summary.copy()
    display["_abs_rank_ic"] = pd.to_numeric(display["mean_rank_ic"], errors="coerce").abs()
    display = display.sort_values(
        ["recommendation", "_abs_rank_ic", "horizon", "feature_name"],
        ascending=[True, False, True, True],
    ).drop(columns=["_abs_rank_ic"])

    lines.extend(
        [
            "| Feature | Horizon | Recommendation | RankIC | RankICIR | IC | Spread | Samples |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in display.to_dict("records"):
        lines.append(
            "| "
            f"{row['feature_name']} | "
            f"{int(row['horizon'])} | "
            f"{row['recommendation']} | "
            f"{_format_float(row.get('mean_rank_ic'))} | "
            f"{_format_float(row.get('rank_icir'))} | "
            f"{_format_float(row.get('mean_ic'))} | "
            f"{_format_float(row.get('mean_top_bottom_spread'))} | "
            f"{int(row.get('sample_rows') or 0)} |"
        )
    return "\n".join(lines) + "\n"


def _summarize_feature_report(
    feature_name: str,
    report: dict[str, Any],
    *,
    min_abs_rank_ic: float = 0.02,
    min_abs_rank_icir: float = 0.2,
    min_ic_count: int = 20,
) -> list[dict[str, Any]]:
    rows = []
    for horizon, horizon_report in report.get("reports", {}).items():
        ic_summary = horizon_report.get("ic_summary", {})
        rank_summary = horizon_report.get("rank_ic_summary", {})
        ic_frame = horizon_report.get("ic", pd.DataFrame())
        spread_frame = horizon_report.get("top_bottom_spread", pd.DataFrame())
        turnover_frame = horizon_report.get("turnover", pd.DataFrame())
        sample_rows = 0
        date_count = 0
        if isinstance(ic_frame, pd.DataFrame) and not ic_frame.empty:
            sample_rows = int(pd.to_numeric(ic_frame["n"], errors="coerce").fillna(0).sum())
            date_count = int(len(ic_frame))
        ic_count = int(rank_summary.get("ic_count") or 0)
        mean_rank_ic = _float_or_none(rank_summary.get("mean_ic"))
        rank_icir = _float_or_none(rank_summary.get("icir"))
        mean_spread = _mean_or_none(spread_frame, "top_bottom_spread")
        rows.append(
            {
                "feature_name": feature_name,
                "horizon": int(horizon),
                "sample_rows": sample_rows,
                "date_count": date_count,
                "ic_count": ic_count,
                "mean_ic": _float_or_none(ic_summary.get("mean_ic")),
                "icir": _float_or_none(ic_summary.get("icir")),
                "mean_rank_ic": mean_rank_ic,
                "rank_icir": rank_icir,
                "mean_top_bottom_spread": mean_spread,
                "mean_turnover": _mean_or_none(turnover_frame, "turnover"),
                "recommendation": classify_intraday_factor_signal(
                    mean_rank_ic=mean_rank_ic,
                    rank_icir=rank_icir,
                    mean_top_bottom_spread=mean_spread,
                    ic_count=ic_count,
                    min_abs_rank_ic=min_abs_rank_ic,
                    min_abs_rank_icir=min_abs_rank_icir,
                    min_ic_count=min_ic_count,
                ),
            }
        )
    return rows


def _numeric_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        return frame
    result = frame.copy()
    for column in columns:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def _mean_or_none(frame: Any, column: str) -> float | None:
    if not isinstance(frame, pd.DataFrame) or frame.empty or column not in frame.columns:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.mean())


def _float_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _format_float(value: Any) -> str:
    numeric = _float_or_none(value)
    if numeric is None:
        return ""
    return f"{numeric:.6f}"
