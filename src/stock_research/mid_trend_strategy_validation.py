from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pandas as pd
from stock_research.config import SETTINGS

SEVERE_DRAWDOWN_THRESHOLD = 0.20

REPO_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_OUTPUT_ROOT = REPO_ROOT / "outputs/research"

DEFAULT_CURRENT_VALIDATION_CONFIG: dict[str, object] = {
    "top_n": 5,
    "adjust_type": "hfq",
    "service": SETTINGS.research_service,
}
DEFAULT_SHADOW_VALIDATION_CONFIG: dict[str, object] = {
    "top_n": 10,
    "rebalance_frequency": "daily",
    "transaction_cost_bps": 20.0,
    "adjust_type": "hfq",
    "service": SETTINGS.research_service,
}
SCORECARD_COLUMNS = [
    "strategy_id",
    "total_return",
    "max_drawdown",
    "return_drawdown_ratio",
    "monthly_win_rate",
    "turnover_penalized_stability",
]


def discover_mid_trend_strategy_candidates() -> list[dict[str, object]]:
    return [
        {
            "strategy_id": "current_mid_trend_strategy_v1",
            "module_name": "stock_research.current_mid_trend_strategy_v1",
            "group": "portfolio",
            "runner_name": "run_current_mid_trend_strategy_v1_backtest",
            "result_keys": {"holdings", "trades", "equity", "summary"},
        },
        {
            "strategy_id": "mid_trend_shadow_backtest",
            "module_name": "stock_research.mid_trend_shadow_backtest",
            "group": "portfolio",
            "runner_name": "run_mid_trend_shadow_backtest",
            "result_keys": {"positions", "trades", "equity_curve", "summary"},
        },
    ]


def filter_complete_mid_trend_candidates(
    candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    complete: list[dict[str, object]] = []
    for candidate in candidates:
        result_keys = set(candidate.get("result_keys", set()))
        if {"trades", "summary"} - result_keys:
            continue
        if not (
            {"holdings", "equity"} <= result_keys
            or {"positions", "equity_curve"} <= result_keys
        ):
            continue
        if candidate.get("group") != "portfolio":
            continue
        complete.append(candidate)
    return complete


def _normalize_mid_trend_validation_result(item: dict[str, object]) -> dict[str, object]:
    strategy_id = str(item["strategy_id"])
    if "summary_frame" in item and "equity_frame" in item:
        return {
            "strategy_id": strategy_id,
            "summary_frame": _normalize_summary_frame(item["summary_frame"]),
            "equity_frame": _normalize_equity_frame(item["equity_frame"]),
        }

    summary = item.get("summary")
    if not isinstance(summary, pd.DataFrame):
        raise ValueError(f"{strategy_id} is missing a DataFrame summary payload")

    if strategy_id == "current_mid_trend_strategy_v1":
        equity = item.get("equity")
        if not isinstance(equity, pd.DataFrame):
            raise ValueError(f"{strategy_id} is missing a DataFrame equity payload")
        return {
            "strategy_id": strategy_id,
            "summary_frame": _wide_summary_to_metric_frame(summary, strategy_id),
            "equity_frame": _normalize_equity_frame(equity),
        }

    if strategy_id == "mid_trend_shadow_backtest":
        equity_curve = item.get("equity_curve")
        if not isinstance(equity_curve, pd.DataFrame):
            raise ValueError(f"{strategy_id} is missing a DataFrame equity_curve payload")
        return {
            "strategy_id": strategy_id,
            "summary_frame": _normalize_summary_frame(summary),
            "equity_frame": _normalize_equity_frame(equity_curve),
        }

    raise ValueError(f"Unsupported mid-trend validation strategy output: {strategy_id}")


def build_mid_trend_validation_scorecard(results: list[dict[str, object]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for item in results:
        normalized = _normalize_mid_trend_validation_result(item)
        summary = normalized["summary_frame"]
        summary_map = _numeric_summary_map(summary)
        equity = normalized["equity_frame"].copy()
        equity["date"] = pd.to_datetime(equity["date"])
        equity = equity.sort_values("date").reset_index(drop=True)
        equity["month"] = equity["date"].dt.to_period("M")
        monthly_equity = equity.groupby("month")["equity"].last().pct_change().dropna()
        total_return = summary_map.get("total_return", float("nan"))
        max_drawdown = summary_map.get("max_drawdown", float("nan"))
        average_turnover = summary_map.get("average_turnover", float("nan"))
        monthly_win_rate = (
            float((monthly_equity > 0).mean()) if len(monthly_equity) else float("nan")
        )
        rows.append(
            {
                "strategy_id": normalized["strategy_id"],
                "total_return": total_return,
                "max_drawdown": max_drawdown,
                "return_drawdown_ratio": (
                    total_return / abs(max_drawdown)
                    if max_drawdown < 0
                    else float("inf")
                    if max_drawdown == 0 and total_return > 0
                    else float("nan")
                ),
                "monthly_win_rate": monthly_win_rate,
                "turnover_penalized_stability": _turnover_penalized_stability(
                    monthly_win_rate,
                    average_turnover,
                ),
            }
        )
    return pd.DataFrame(rows)


def build_mid_trend_replay_audit(
    *,
    strategy_id: str,
    holdings: pd.DataFrame,
    trades: pd.DataFrame,
    prices: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    daily_target_snapshot, daily_rebalance_actions, normalized_prices = (
        _normalize_mid_trend_replay_inputs(
            strategy_id=strategy_id,
            holdings=holdings,
            trades=trades,
            prices=prices,
        )
    )
    trade_audit_detail = _build_mid_trend_trade_audit_detail(
        strategy_id=strategy_id,
        trades=daily_rebalance_actions,
        prices=normalized_prices,
    )
    monthly_issue_summary = (
        trade_audit_detail.assign(
            month=pd.to_datetime(trade_audit_detail["trade_date"])
            .dt.to_period("M")
            .astype(str)
        )
        .loc[lambda frame: frame["audit_label"].astype(str).ne("")]
        .groupby(["month", "audit_label"], as_index=False)
        .size()
        .rename(columns={"size": "issue_count"})
    )
    return {
        "daily_target_snapshot": daily_target_snapshot,
        "daily_rebalance_actions": daily_rebalance_actions,
        "trade_audit_detail": trade_audit_detail,
        "monthly_issue_summary": monthly_issue_summary,
    }


def _normalize_mid_trend_replay_inputs(
    *,
    strategy_id: str,
    holdings: pd.DataFrame,
    trades: pd.DataFrame,
    prices: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    normalized_prices = _normalize_mid_trend_replay_prices(prices)
    if strategy_id == "current_mid_trend_strategy_v1":
        return (
            _normalize_current_replay_holdings(holdings),
            _normalize_current_replay_trades(trades),
            normalized_prices,
        )
    if strategy_id == "mid_trend_shadow_backtest":
        return (
            _normalize_shadow_replay_positions(holdings),
            _normalize_shadow_replay_trades(trades),
            normalized_prices,
        )
    raise ValueError(f"Unsupported replay audit strategy family: {strategy_id}")


def _normalize_current_replay_holdings(holdings: pd.DataFrame) -> pd.DataFrame:
    _require_replay_columns(
        holdings,
        required={"trade_date", "asset_id", "target_weight"},
        label="current holdings",
    )
    frame = holdings.copy()
    frame["trade_date"] = _normalize_date_series(frame["trade_date"], "current holdings trade_date")
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["target_weight"] = pd.to_numeric(frame["target_weight"], errors="coerce").fillna(0.0)
    return frame.sort_values(["trade_date", "asset_id"]).reset_index(drop=True)


def _normalize_shadow_replay_positions(positions: pd.DataFrame) -> pd.DataFrame:
    _require_replay_columns(
        positions,
        required={"rebalance_date", "asset_id", "weight"},
        label="shadow positions",
    )
    frame = positions.copy().rename(
        columns={"rebalance_date": "trade_date", "weight": "target_weight"}
    )
    frame["trade_date"] = _normalize_date_series(frame["trade_date"], "shadow positions rebalance_date")
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["target_weight"] = pd.to_numeric(frame["target_weight"], errors="coerce").fillna(0.0)
    return frame.sort_values(["trade_date", "asset_id"]).reset_index(drop=True)


def _normalize_current_replay_trades(trades: pd.DataFrame) -> pd.DataFrame:
    _require_replay_columns(
        trades,
        required={"trade_date", "asset_id", "action"},
        label="current trades",
    )
    frame = trades.copy()
    frame["trade_date"] = _normalize_date_series(frame["trade_date"], "current trades trade_date")
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["side"] = _map_replay_trade_side(frame["action"], label="current trades action")
    return frame.sort_values(["trade_date", "asset_id"]).reset_index(drop=True)


def _normalize_shadow_replay_trades(trades: pd.DataFrame) -> pd.DataFrame:
    trade_date_column = _first_present_column(
        trades,
        ["execution_date", "rebalance_date", "signal_date"],
        label="shadow trades",
    )
    side_column = _first_present_column(
        trades,
        ["side", "action"],
        label="shadow trades",
    )
    _require_replay_columns(
        trades,
        required={"asset_id", trade_date_column, side_column},
        label="shadow trades",
    )
    frame = trades.copy().rename(columns={trade_date_column: "trade_date"})
    frame["trade_date"] = _normalize_date_series(frame["trade_date"], "shadow trades trade date")
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["side"] = _map_replay_trade_side(frame[side_column], label="shadow trades side")
    return frame.sort_values(["trade_date", "asset_id"]).reset_index(drop=True)


def _normalize_mid_trend_replay_prices(prices: pd.DataFrame) -> pd.DataFrame:
    date_column = _first_present_column(prices, ["trade_date", "date"], label="replay prices")
    _require_replay_columns(
        prices,
        required={"asset_id", "close", date_column},
        label="replay prices",
    )
    frame = prices.copy().rename(columns={date_column: "trade_date"})
    frame["trade_date"] = _normalize_date_series(frame["trade_date"], "replay prices trade date")
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["close"])
    if frame.empty:
        raise ValueError("replay prices contain no valid close rows")
    return frame.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)


def _build_mid_trend_trade_audit_detail(
    *,
    strategy_id: str,
    trades: pd.DataFrame,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for trade in trades.to_dict("records"):
        forward_return, entry_date, exit_date = _compute_replay_forward_return(
            prices=prices,
            asset_id=str(trade["asset_id"]),
            trade_date=str(trade["trade_date"]),
        )
        side = str(trade["side"])
        audit_label = ""
        if pd.notna(forward_return):
            if side == "buy" and float(forward_return) < 0.0:
                audit_label = "bad_buy"
            elif side == "sell" and float(forward_return) > 0.02:
                audit_label = "bad_sell"
        row = dict(trade)
        row["strategy_id"] = strategy_id
        row["forward_return"] = forward_return
        row["replay_entry_date"] = entry_date
        row["replay_exit_date"] = exit_date
        row["audit_label"] = audit_label
        rows.append(row)
    return pd.DataFrame(rows)


def _compute_replay_forward_return(
    *,
    prices: pd.DataFrame,
    asset_id: str,
    trade_date: str,
) -> tuple[float, str | None, str | None]:
    asset_prices = prices[prices["asset_id"].astype(str) == asset_id].copy()
    if asset_prices.empty:
        return float("nan"), None, None
    trade_ts = pd.Timestamp(trade_date)
    asset_prices["trade_date_ts"] = pd.to_datetime(asset_prices["trade_date"], errors="coerce")
    future = asset_prices[asset_prices["trade_date_ts"] >= trade_ts].sort_values("trade_date_ts")
    if len(future) < 2:
        return float("nan"), None, None
    entry = future.iloc[0]
    exit_row = future.iloc[-1]
    entry_close = float(entry["close"])
    exit_close = float(exit_row["close"])
    if entry_close == 0:
        return float("nan"), None, None
    return (
        exit_close / entry_close - 1.0,
        str(entry["trade_date_ts"].date()),
        str(exit_row["trade_date_ts"].date()),
    )


def _require_replay_columns(
    frame: pd.DataFrame,
    *,
    required: set[str],
    label: str,
) -> None:
    missing = sorted(column for column in required if column not in frame.columns)
    if missing:
        raise ValueError(f"{label} missing required columns: {', '.join(missing)}")


def _first_present_column(frame: pd.DataFrame, candidates: list[str], *, label: str) -> str:
    for column in candidates:
        if column in frame.columns:
            return column
    raise ValueError(f"{label} missing any of expected columns: {', '.join(candidates)}")


def _normalize_date_series(series: pd.Series, label: str) -> pd.Series:
    dates = pd.to_datetime(series, errors="coerce")
    if dates.isna().any():
        raise ValueError(f"{label} contains invalid dates")
    return dates.dt.strftime("%Y-%m-%d")


def _map_replay_trade_side(series: pd.Series, *, label: str) -> pd.Series:
    normalized = series.astype(str).str.lower().map(
        {
            "buy": "buy",
            "increase": "buy",
            "enter": "buy",
            "sell": "sell",
            "decrease": "sell",
            "exit": "sell",
        }
    )
    if normalized.isna().any():
        unsupported = sorted(series[normalized.isna()].astype(str).unique().tolist())
        raise ValueError(f"{label} contains unsupported trade actions: {', '.join(unsupported)}")
    return normalized


def rank_mid_trend_validation_scorecard(scorecard: pd.DataFrame) -> pd.DataFrame:
    if scorecard.empty:
        return scorecard.reindex(columns=[*SCORECARD_COLUMNS, "drawdown_penalty", "severe_drawdown"])
    ranked = scorecard.copy()
    ranked["drawdown_penalty"] = ranked["max_drawdown"].abs()
    # Treat clearly bad drawdown as a coarse filter, then rank on efficiency and stability.
    ranked["severe_drawdown"] = ranked["drawdown_penalty"] > SEVERE_DRAWDOWN_THRESHOLD
    return ranked.sort_values(
        [
            "severe_drawdown",
            "return_drawdown_ratio",
            "monthly_win_rate",
            "turnover_penalized_stability",
            "drawdown_penalty",
            "total_return",
        ],
        ascending=[True, False, False, False, True, False],
    ).reset_index(drop=True)


def execute_mid_trend_candidate(
    candidate: dict[str, object],
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    current_regime_path: str | Path | None = None,
    funnel_detail_path: str | Path | None = None,
    shadow_top10_path: str | Path | None = None,
) -> dict[str, object]:
    strategy_id = str(candidate["strategy_id"])
    module_name = str(candidate["module_name"])
    runner_name = str(candidate["runner_name"])
    runner = getattr(import_module(module_name), runner_name)
    candidate_output_dir = _resolve_output_dir(output_dir) / strategy_id
    current_regime_path = resolve_default_current_regime_path(current_regime_path)
    funnel_detail_path = resolve_default_funnel_detail_path(funnel_detail_path)
    shadow_top10_path = resolve_default_shadow_top10_path(shadow_top10_path)

    if strategy_id == "current_mid_trend_strategy_v1":
        return runner(
            start_date=start_date,
            end_date=end_date,
            regime_path=current_regime_path,
            funnel_detail_path=funnel_detail_path,
            output_dir=candidate_output_dir,
            **DEFAULT_CURRENT_VALIDATION_CONFIG,
        )

    if strategy_id == "mid_trend_shadow_backtest":
        return runner(
            shadow_top10_path=shadow_top10_path,
            start_date=start_date,
            end_date=end_date,
            output_dir=candidate_output_dir,
            **DEFAULT_SHADOW_VALIDATION_CONFIG,
        )

    raise ValueError(f"Unsupported mid-trend validation candidate: {strategy_id}")


def run_mid_trend_strategy_validation(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    current_regime_path: str | Path | None = None,
    funnel_detail_path: str | Path | None = None,
    shadow_top10_path: str | Path | None = None,
) -> dict[str, object]:
    output_path = _resolve_output_dir(output_dir)
    current_regime_path = resolve_default_current_regime_path(current_regime_path)
    funnel_detail_path = resolve_default_funnel_detail_path(funnel_detail_path)
    shadow_top10_path = resolve_default_shadow_top10_path(shadow_top10_path)
    candidates = filter_complete_mid_trend_candidates(
        discover_mid_trend_strategy_candidates()
    )
    effective_end_date = _resolve_validation_effective_end_date(
        requested_end_date=end_date,
        candidates=candidates,
        current_regime_path=current_regime_path,
        funnel_detail_path=funnel_detail_path,
        shadow_top10_path=shadow_top10_path,
    )
    results = [
        {
            "strategy_id": str(candidate["strategy_id"]),
            **execute_mid_trend_candidate(
                candidate,
                start_date=start_date,
                end_date=effective_end_date,
                output_dir=output_path,
                current_regime_path=current_regime_path,
                funnel_detail_path=funnel_detail_path,
                shadow_top10_path=shadow_top10_path,
            ),
        }
        for candidate in candidates
    ]
    scorecard = build_mid_trend_validation_scorecard(results)
    ranked = rank_mid_trend_validation_scorecard(scorecard)
    winner = ranked.iloc[0].to_dict() if not ranked.empty else {}
    scorecard_path = output_path / "mid_trend_validation_scorecard.csv"
    report_path = output_path / "mid_trend_validation_report.md"
    scorecard_path.parent.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(scorecard_path, index=False)
    report_path.write_text(
        "# Mid Trend Validation\n\n"
        f"Effective end date: {effective_end_date or 'none'}\n\n"
        f"Winner: {winner.get('strategy_id', 'none')}\n",
        encoding="utf-8",
    )
    return {
        "candidates": candidates,
        "ranked_scorecard": ranked,
        "winner": winner,
        "effective_end_date": effective_end_date,
        "paths": {"scorecard": str(scorecard_path), "report": str(report_path)},
    }


def _resolve_output_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def resolve_default_current_regime_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return _select_latest_artifact_path("market_regime_confirmation_daily.csv")


def resolve_default_funnel_detail_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return _select_latest_artifact_path("mid_trend_watch_funnel_detail.csv")


def resolve_default_shadow_top10_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return _select_latest_artifact_path("mid_trend_shadow_top10.csv")


def _select_latest_artifact_path(
    artifact_name: str,
    *,
    base_dir: str | Path = RESEARCH_OUTPUT_ROOT,
) -> Path:
    base_path = Path(base_dir)
    candidates = sorted(base_path.rglob(artifact_name))
    if not candidates:
        raise FileNotFoundError(f"No validation artifact found for {artifact_name} under {base_path}")

    ranked_candidates = [
        (
            _read_input_coverage_end_date(candidate),
            candidate.stat().st_mtime,
            str(candidate),
            candidate,
        )
        for candidate in candidates
    ]
    return max(ranked_candidates)[-1]


def _resolve_validation_effective_end_date(
    *,
    requested_end_date: str,
    candidates: list[dict[str, object]],
    current_regime_path: str | Path,
    funnel_detail_path: str | Path,
    shadow_top10_path: str | Path,
) -> str | None:
    if not candidates:
        return None

    candidate_coverage_ends: list[pd.Timestamp] = []
    for candidate in candidates:
        coverage_end = _candidate_coverage_end_date(
            candidate,
            current_regime_path=current_regime_path,
            funnel_detail_path=funnel_detail_path,
            shadow_top10_path=shadow_top10_path,
        )
        if coverage_end is not None:
            candidate_coverage_ends.append(coverage_end)

    effective_end = pd.Timestamp(requested_end_date)
    if candidate_coverage_ends:
        effective_end = min([effective_end, *candidate_coverage_ends])
    return effective_end.date().isoformat()


def _candidate_coverage_end_date(
    candidate: dict[str, object],
    *,
    current_regime_path: str | Path,
    funnel_detail_path: str | Path,
    shadow_top10_path: str | Path,
) -> pd.Timestamp | None:
    strategy_id = str(candidate.get("strategy_id", ""))
    if strategy_id == "current_mid_trend_strategy_v1":
        return min(
            _read_input_coverage_end_date(current_regime_path),
            _read_input_coverage_end_date(funnel_detail_path),
        )
    if strategy_id == "mid_trend_shadow_backtest":
        return _read_input_coverage_end_date(shadow_top10_path)
    return None


def _read_input_coverage_end_date(path: str | Path) -> pd.Timestamp:
    frame = pd.read_csv(path, usecols=lambda column: column in {"trade_date", "date"})
    if "trade_date" in frame.columns:
        series = frame["trade_date"]
    elif "date" in frame.columns:
        series = frame["date"]
    else:
        raise ValueError(f"Input artifact has no coverage date column: {path}")
    dates = pd.to_datetime(series, errors="coerce").dropna()
    if dates.empty:
        raise ValueError(f"Input artifact has no valid coverage dates: {path}")
    return dates.max().normalize()


def _normalize_summary_frame(summary: object) -> pd.DataFrame:
    if not isinstance(summary, pd.DataFrame):
        raise ValueError("summary_frame must be a pandas DataFrame")
    if {"metric", "value"} <= set(summary.columns):
        return summary.loc[:, ["metric", "value"]].copy()
    return _wide_summary_to_metric_frame(summary)


def _wide_summary_to_metric_frame(summary: pd.DataFrame, strategy_id: str | None = None) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame(columns=["metric", "value"])

    row = summary.iloc[0]
    if strategy_id and "strategy_family" in summary.columns:
        matched = summary[summary["strategy_family"].astype(str) == strategy_id]
        if not matched.empty:
            row = matched.iloc[0]
    records = [{"metric": str(column), "value": row[column]} for column in summary.columns]
    return pd.DataFrame(records, columns=["metric", "value"])


def _normalize_equity_frame(equity: object) -> pd.DataFrame:
    if not isinstance(equity, pd.DataFrame):
        raise ValueError("equity_frame must be a pandas DataFrame")
    frame = equity.copy()
    if "date" not in frame.columns and "trade_date" in frame.columns:
        frame = frame.rename(columns={"trade_date": "date"})
    return frame


def _numeric_summary_map(summary: pd.DataFrame) -> dict[str, float]:
    summary_frame = summary.copy()
    summary_frame["metric"] = summary_frame["metric"].astype(str)
    summary_frame["numeric_value"] = pd.to_numeric(summary_frame["value"], errors="coerce")
    numeric_rows = summary_frame.dropna(subset=["numeric_value"])
    return {
        row["metric"]: float(row["numeric_value"])
        for row in numeric_rows.to_dict("records")
    }


def _turnover_penalized_stability(
    monthly_win_rate: float,
    average_turnover: float,
) -> float:
    if pd.isna(monthly_win_rate) or pd.isna(average_turnover):
        return float("nan")
    turnover = min(max(float(average_turnover), 0.0), 1.0)
    return (1.0 - turnover) * float(monthly_win_rate)
