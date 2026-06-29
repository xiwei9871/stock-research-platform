import math
import time
from datetime import datetime, timezone
from numbers import Integral, Real
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.data_run_manifest import load_latest_data_run_manifest
from stock_research.dashboard.strategy_catalog import list_strategy_catalog
from stock_research.dashboard.strategy_backtest_adapters import (
    STRATEGY_BACKTEST_REGISTRY,
    StrategyBacktestParams,
)
from stock_research.db import connect, fetch_all
from stock_research.lhb_shortline_v1 import run_lhb_shortline_v1_backtest_for_dashboard
from stock_research.mid_trend_v1 import run_mid_trend_v1_backtest_for_dashboard
from stock_research.tech_bottleneck_eod import run_tech_bottleneck_eod
from stock_research.tech_bottleneck_v1 import (
    TECH_BOTTLENECK_V1_CANDIDATES_PATH,
    run_tech_bottleneck_v1_backtest_for_dashboard,
)
from stock_research.vectorized_topn_backtest import (
    VectorizedTopNConfig,
    run_vectorized_topn_backtest,
)

BACKTEST_LAB_STRATEGY_IDS = {
    "lhb_shortline",
    "mid_trend",
    "tech_bottleneck",
}
TECH_BOTTLENECK_LAB_OUTPUT_ROOT = Path(getattr(SETTINGS, "output_root", "/Users/xiwei/stock_research/outputs")) / "research" / "strategy_lab_tech_bottleneck"


def load_strategy_contracts(profile: str = "balanced") -> dict[str, Any]:
    from stock_research.strategy_contracts import (
        load_strategy_contracts as _load_strategy_contracts,
    )

    return _load_strategy_contracts(profile=profile)


def strategy_contract_run_config(contract: Any) -> dict[str, Any]:
    from stock_research.strategy_contracts import (
        strategy_contract_run_config as _strategy_contract_run_config,
    )

    return _strategy_contract_run_config(contract)


def validate_strategy_summary_against_contract(summary: dict[str, Any], contract: Any) -> Any:
    from stock_research.strategy_contracts import (
        validate_strategy_summary_against_contract as _validate_strategy_summary_against_contract,
    )

    return _validate_strategy_summary_against_contract(summary, contract)


def list_backtest_strategies() -> list[dict[str, Any]]:
    strategies = [
        strategy
        for strategy in list_strategy_catalog()
        if strategy["strategy_id"] in BACKTEST_LAB_STRATEGY_IDS and strategy["status"] == "runnable"
    ]
    strategies = _apply_strategy_contract_defaults(strategies)
    return _enrich_strategies_with_latest_eod_metrics(_enrich_strategies_with_latest_db_metrics(strategies))


def _apply_strategy_contract_defaults(strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        contracts = load_strategy_contracts(profile="balanced")
    except Exception:
        return strategies
    next_strategies: list[dict[str, Any]] = []
    for strategy in strategies:
        contract = contracts.get(str(strategy.get("strategy_id") or ""))
        if contract is None:
            next_strategies.append(strategy)
            continue
        contract_config = strategy_contract_run_config(contract)
        default_parameters = dict(strategy.get("default_parameters") or {})
        for key, value in contract_config.items():
            default_parameters[key] = value
        next_strategy = dict(strategy)
        next_strategy["default_parameters"] = default_parameters
        next_strategies.append(next_strategy)
    return next_strategies


def _enrich_strategies_with_latest_db_metrics(strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        with connect(SETTINGS.research_service) as conn:
            return [_with_latest_db_metrics(conn, strategy) for strategy in strategies]
    except Exception:
        return strategies


def _enrich_strategies_with_latest_eod_metrics(strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_with_latest_eod_strategy_metrics(strategy) for strategy in strategies]


def _with_latest_eod_strategy_metrics(strategy: dict[str, Any]) -> dict[str, Any]:
    module = _latest_eod_strategy_module(str(strategy.get("strategy_id") or ""))
    if not module:
        return strategy

    latest_trade_date = str(module.get("latest_trade_date") or module.get("trade_date") or "")
    if str(module.get("status") or "") != "success":
        return _with_failed_eod_strategy_metrics(strategy, module, latest_trade_date=latest_trade_date)

    rows = _read_eod_strategy_rows(module, latest_trade_date=latest_trade_date, strategy_id=str(strategy["strategy_id"]))
    signal_count = len(rows) or _optional_int(module.get("row_count"))
    metrics = dict(strategy.get("latest_metrics") or {})
    summary = _eod_summary(module)
    performance_as_of_date = _performance_as_of_date(summary, fallback=latest_trade_date)
    metrics.update(
        {
            "as_of_date": performance_as_of_date or metrics.get("as_of_date"),
            "signal_as_of_date": latest_trade_date or metrics.get("signal_as_of_date"),
            "signal_status": "candidate_rows" if strategy["strategy_id"] == "lhb_shortline" else "current_holdings",
            "signal_count": signal_count,
        }
    )

    contract_status = _validate_eod_summary_contract(str(strategy["strategy_id"]), summary)
    if contract_status:
        status, reason = contract_status
        if status != "success":
            next_strategy = dict(strategy)
            next_strategy["latest_metrics"] = {
                "as_of_date": performance_as_of_date or metrics.get("as_of_date"),
                "signal_as_of_date": latest_trade_date or metrics.get("signal_as_of_date"),
                "signal_status": "contract_mismatch",
                "signal_count": signal_count,
                "contract_status": status,
                "contract_reason": reason,
            }
            next_strategy["latest_evidence"] = f"策略产物未通过正式身份合同校验：{reason}"
            return next_strategy
        metrics["contract_status"] = status
    equity_metrics = _metrics_from_eod_equity_path(module, strategy)
    if summary:
        metrics.update(_metrics_from_eod_summary(summary))
        for key in [
            "latest_day_return_pct",
            "latest_day_drawdown_pct",
            "latest_period_return_pct",
            "latest_period_label",
        ]:
            if key in equity_metrics:
                metrics[key] = equity_metrics[key]
    else:
        metrics.update(equity_metrics)

    next_strategy = dict(strategy)
    next_strategy["latest_metrics"] = metrics
    next_strategy["latest_evidence"] = _eod_strategy_evidence(
        strategy=strategy,
        module=module,
        rows=rows,
        latest_trade_date=latest_trade_date,
        performance_as_of_date=performance_as_of_date,
        signal_count=signal_count,
    )
    return next_strategy


def _with_failed_eod_strategy_metrics(
    strategy: dict[str, Any],
    module: dict[str, Any],
    *,
    latest_trade_date: str,
) -> dict[str, Any]:
    error_message = str(module.get("error_message") or "")
    next_strategy = dict(strategy)
    next_strategy["latest_metrics"] = {
        "as_of_date": latest_trade_date or str(module.get("trade_date") or ""),
        "signal_status": "strategy_failed",
        "signal_count": 0,
        "error_message": error_message,
    }
    strategy_name = str(strategy.get("strategy_name") or strategy.get("strategy_id") or "策略")
    next_strategy["latest_evidence"] = (
        f"{strategy_name} 正式策略产物失败"
        f"：{error_message}" if error_message else f"{strategy_name} 正式策略产物失败。"
    )
    return next_strategy


def _validate_eod_summary_contract(strategy_id: str, summary: dict[str, Any]) -> tuple[str, str] | None:
    if not summary:
        return None
    try:
        contract = load_strategy_contracts(profile="balanced").get(strategy_id)
    except Exception:
        return None
    if contract is None:
        return None
    result = validate_strategy_summary_against_contract(summary, contract)
    return result.status, result.reason


def _latest_eod_strategy_module(strategy_id: str) -> dict[str, Any] | None:
    module_name = {
        "lhb_shortline": "strategy_lhb_shortline",
        "mid_trend": "strategy_mid_trend",
        "tech_bottleneck": "strategy_tech_bottleneck",
    }.get(strategy_id)
    if not module_name:
        return None
    try:
        modules = list(load_latest_data_run_manifest())
    except Exception:
        return None
    for module in modules:
        if str(module.get("module") or "") == module_name:
            return module
    return None


def _read_eod_strategy_rows(
    module: dict[str, Any],
    *,
    latest_trade_date: str,
    strategy_id: str,
) -> list[dict[str, Any]]:
    artifact_path = Path(str(module.get("artifact_path") or ""))
    if not artifact_path.exists() or artifact_path.is_dir():
        return []
    try:
        frame = pd.read_csv(artifact_path)
    except Exception:
        return []
    if frame.empty:
        return []
    if "trade_date" in frame.columns and latest_trade_date:
        frame = frame.loc[frame["trade_date"].astype(str).str[:10].eq(latest_trade_date)]
    if "strategy_id" in frame.columns:
        frame = frame.loc[frame["strategy_id"].astype(str).eq(strategy_id)]
    if "rank" in frame.columns:
        frame = frame.sort_values("rank", kind="stable")
    return frame.to_dict("records")


def _eod_summary(module: dict[str, Any]) -> dict[str, Any]:
    metadata = module.get("metadata") if isinstance(module.get("metadata"), dict) else {}
    summary = metadata.get("summary") if isinstance(metadata.get("summary"), dict) else {}
    return dict(summary)


def _metrics_from_eod_summary(summary: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    total_return = summary.get("total_return")
    if total_return is None and _finite_or_none(summary.get("final_equity")) is not None:
        total_return = float(summary["final_equity"]) - 1.0
    if total_return is not None:
        metrics["total_return_pct"] = _percent_metric(total_return)
    if summary.get("max_drawdown") is not None:
        metrics["max_drawdown_pct"] = _percent_metric(summary.get("max_drawdown"))
    if summary.get("latest_day_return") is not None:
        metrics["latest_day_return_pct"] = _percent_metric(summary.get("latest_day_return"))
    if summary.get("latest_day_drawdown") is not None:
        metrics["latest_day_drawdown_pct"] = _percent_metric(summary.get("latest_day_drawdown"))
    if summary.get("latest_period_return") is not None:
        metrics["latest_period_return_pct"] = _percent_metric(summary.get("latest_period_return"))
    if summary.get("latest_period_label"):
        metrics["latest_period_label"] = str(summary.get("latest_period_label"))
    return metrics


def _performance_as_of_date(summary: dict[str, Any], *, fallback: str) -> str:
    return str(
        summary.get("performance_effective_date")
        or summary.get("actual_end_date")
        or summary.get("equity_latest_date")
        or summary.get("end_date")
        or fallback
        or ""
    )


def _metrics_from_eod_equity_path(module: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    metadata = module.get("metadata") if isinstance(module.get("metadata"), dict) else {}
    output_paths = metadata.get("output_paths") if isinstance(metadata.get("output_paths"), dict) else {}
    equity_path = Path(str(metadata.get("equity_path") or output_paths.get("equity_path") or ""))
    if not equity_path.exists():
        return {}
    try:
        frame = pd.read_csv(equity_path)
    except Exception:
        return {}
    if frame.empty or "equity" not in frame.columns:
        return {}
    if "trade_date" in frame.columns:
        frame = frame.sort_values("trade_date", kind="stable")
        scoped_frame = _latest_year_equity_frame(frame)
        latest_first_frame = frame.sort_values("trade_date", ascending=False, kind="stable")
    else:
        scoped_frame = frame
        latest_first_frame = frame.iloc[::-1]
    equity_rows = latest_first_frame.head(8).to_dict("records")
    latest = equity_rows[0]
    previous = equity_rows[1] if len(equity_rows) > 1 else None
    latest_equity = _finite_or_none(latest.get("equity"))
    previous_equity = _finite_or_none(previous.get("equity")) if previous else None
    latest_daily_return = _finite_or_none(latest.get("daily_return") or latest.get("net_return"))
    if latest_daily_return is None and latest_equity is not None and previous_equity not in (None, 0.0):
        latest_daily_return = latest_equity / previous_equity - 1.0
    scoped_return, scoped_drawdown = _scoped_equity_return_and_drawdown(scoped_frame)
    latest_period_return, latest_period_label = _latest_period_return(
        strategy=strategy,
        equity_rows=equity_rows,
        latest_equity=latest_equity,
        latest_daily_return=latest_daily_return,
    )
    return {
        "total_return_pct": _percent_metric(scoped_return),
        "max_drawdown_pct": _percent_metric(scoped_drawdown),
        "latest_day_return_pct": _percent_metric(latest_daily_return),
        "latest_day_drawdown_pct": _percent_metric(_finite_or_none(latest.get("drawdown"))),
        "latest_period_return_pct": _percent_metric(latest_period_return),
        "latest_period_label": latest_period_label,
    }


def _latest_year_equity_frame(frame: pd.DataFrame) -> pd.DataFrame:
    parsed_dates = pd.to_datetime(frame["trade_date"], errors="coerce")
    latest_date = parsed_dates.max()
    if pd.isna(latest_date):
        return frame
    scoped = frame.loc[parsed_dates.dt.year.eq(latest_date.year)]
    return scoped if not scoped.empty else frame


def _scoped_equity_return_and_drawdown(frame: pd.DataFrame) -> tuple[float | None, float | None]:
    equity = [_finite_or_none(value) for value in frame.get("equity", [])]
    equity = [value for value in equity if value is not None]
    if not equity or equity[0] == 0.0:
        return None, None
    rebased = [value / equity[0] for value in equity]
    high_water = rebased[0]
    drawdowns: list[float] = []
    for value in rebased:
        high_water = max(high_water, value)
        drawdowns.append(value / high_water - 1.0 if high_water else 0.0)
    return rebased[-1] - 1.0, min(drawdowns) if drawdowns else None


def _eod_strategy_evidence(
    *,
    strategy: dict[str, Any],
    module: dict[str, Any],
    rows: list[dict[str, Any]],
    latest_trade_date: str,
    performance_as_of_date: str,
    signal_count: int | None,
) -> str:
    strategy_id = str(strategy.get("strategy_id") or "")
    metadata = module.get("metadata") if isinstance(module.get("metadata"), dict) else {}
    row_position_date = next((str(row.get("source_position_date") or "") for row in rows if row.get("source_position_date")), "")
    source_position_date = str(metadata.get("source_position_date") or row_position_date or "")
    names = [str(row.get("stock_name") or "") for row in rows if str(row.get("stock_name") or "")]
    name_text = f"；名单：{'、'.join(names[:5])}" if names else ""
    if strategy_id == "lhb_shortline":
        if performance_as_of_date and performance_as_of_date != latest_trade_date:
            return (
                f"LHB Shortline 真策略候选产物：候选日期 {latest_trade_date}，当日候选 {signal_count or 0} 只；"
                f"收益估值截止 {performance_as_of_date}{name_text}。"
            )
        return f"LHB Shortline 真策略候选产物：{latest_trade_date} 当日候选 {signal_count or 0} 只{name_text}。"
    if strategy_id == "mid_trend":
        return (
            f"Mid Trend V1 真回测已估值截止 {performance_as_of_date or latest_trade_date}；"
            f"复盘标的为当前持仓，持仓来源日 {source_position_date or '未记录'}{name_text}。"
        )
    if strategy_id == "tech_bottleneck":
        return (
            f"Tech Bottleneck V1 真回测已估值截止 {performance_as_of_date or latest_trade_date}；"
            f"复盘标的为当前持仓，持仓来源日 {source_position_date or '未记录'}{name_text}。"
        )
    return str(strategy.get("latest_evidence") or "")


def _with_latest_db_metrics(conn: Any, strategy: dict[str, Any]) -> dict[str, Any]:
    run_rows = fetch_all(
        conn,
        """
        SELECT run_id, summary_json
        FROM backtest.strategy_backtest_run
        WHERE strategy_id = %s
        ORDER BY end_date DESC, created_at DESC
        LIMIT 1
        """,
        [strategy["strategy_id"]],
    )
    if not run_rows:
        return strategy

    run = run_rows[0]
    equity_rows = fetch_all(
        conn,
        """
        SELECT trade_date::text AS trade_date, equity, drawdown, daily_return
        FROM (
            SELECT DISTINCT ON (trade_date)
                   trade_date, equity, drawdown, daily_return
            FROM backtest.strategy_backtest_equity
            WHERE run_id = %s
            ORDER BY trade_date DESC, row_index DESC
        ) latest_days
        ORDER BY trade_date DESC
        LIMIT 8
        """,
        [run["run_id"]],
    )
    if not equity_rows:
        return strategy

    latest = equity_rows[0]
    previous = equity_rows[1] if len(equity_rows) > 1 else None
    signal_status, signal_count = _latest_position_signal_metrics(conn, str(run["run_id"]))
    summary = run.get("summary_json") if isinstance(run.get("summary_json"), dict) else {}
    metrics = dict(strategy.get("latest_metrics") or {})
    latest_equity = _finite_or_none(latest.get("equity"))
    previous_equity = _finite_or_none(previous.get("equity")) if previous else None
    latest_daily_return = _finite_or_none(latest.get("daily_return"))
    if latest_daily_return is None and latest_equity is not None and previous_equity not in (None, 0.0):
        latest_daily_return = latest_equity / previous_equity - 1.0
    latest_period_return, latest_period_label = _latest_period_return(
        strategy=strategy,
        equity_rows=equity_rows,
        latest_equity=latest_equity,
        latest_daily_return=latest_daily_return,
    )

    next_strategy = dict(strategy)
    next_strategy["latest_metrics"] = {
        **metrics,
        "as_of_date": str(latest.get("trade_date") or metrics.get("as_of_date") or ""),
        "total_return_pct": _percent_metric(
            summary.get("total_return"),
            fallback=(latest_equity - 1.0 if latest_equity is not None else None),
        ),
        "max_drawdown_pct": _percent_metric(summary.get("max_drawdown"), fallback=_finite_or_none(latest.get("drawdown"))),
        "latest_day_return_pct": _percent_metric(latest_daily_return),
        "latest_day_drawdown_pct": _percent_metric(_finite_or_none(latest.get("drawdown"))),
        "latest_period_return_pct": _percent_metric(latest_period_return),
        "latest_period_label": latest_period_label,
        "signal_status": signal_status,
        "signal_count": signal_count,
    }
    return next_strategy


def _latest_period_return(
    *,
    strategy: dict[str, Any],
    equity_rows: list[dict[str, Any]],
    latest_equity: float | None,
    latest_daily_return: float | None,
) -> tuple[float | None, str]:
    frequency = str(
        (strategy.get("default_parameters") or {}).get("rebalance_frequency") or ""
    ).lower()
    if frequency == "weekly":
        anchor = equity_rows[5] if len(equity_rows) > 5 else (equity_rows[-1] if len(equity_rows) > 1 else None)
        anchor_equity = _finite_or_none(anchor.get("equity")) if anchor else None
        if latest_equity is not None and anchor_equity not in (None, 0.0):
            return latest_equity / anchor_equity - 1.0, "最近调仓周期"
        return latest_daily_return, "最近调仓周期"
    return latest_daily_return, "最近交易日"


def _latest_position_signal_metrics(conn: Any, run_id: str) -> tuple[str, int | None]:
    rows = fetch_all(
        conn,
        """
        WITH latest_position_date AS (
            SELECT MAX(trade_date) AS trade_date
            FROM backtest.strategy_backtest_position
            WHERE run_id = %s
        )
        SELECT COUNT(p.asset_id) AS signal_count
        FROM latest_position_date latest
        LEFT JOIN backtest.strategy_backtest_position p
          ON p.run_id = %s
         AND p.trade_date = latest.trade_date
        """,
        [run_id, run_id],
    )
    count = int(rows[0]["signal_count"] or 0) if rows else 0
    return ("connected", count) if count > 0 else ("no_position_rows", None)


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _percent_metric(value: Any, *, fallback: float | None = None) -> float | None:
    number = _finite_or_none(value)
    if number is None:
        number = fallback
    return round(number * 100.0, 2) if number is not None else None


def load_vectorized_topn_prices(start_date: str, end_date: str, adjust_type: str) -> pd.DataFrame:
    sql = """
    SELECT trade_date, asset_id, open, close, amount, trade_status,
           false AS is_limit_up,
           false AS is_limit_down,
           trade_status <> '1' AS is_suspended
    FROM market_daily_bar
    WHERE adjust_type = %s
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, start_date, end_date])
    return pd.DataFrame(rows)


def _parse_backtest_request(
    payload: dict[str, Any],
) -> tuple[str, StrategyBacktestParams, dict[str, Any], VectorizedTopNConfig]:
    strategy_id = _required_text(payload, "strategy_id")
    start_date = _required_text(payload, "start_date")
    end_date = _required_text(payload, "end_date")
    score_version = _optional_text(payload.get("score_version"), "manual_v1")
    adjust_type = _optional_text(payload.get("adjust_type"), "hfq")
    top_n = _positive_int(payload.get("top_n"), "top_n", 20)
    max_positions = _optional_positive_int(payload.get("max_positions"), "max_positions")
    max_position_weight = _optional_position_weight(payload.get("max_position_weight"))
    risk_profile = _optional_text(payload.get("risk_profile"), "balanced")
    rebalance_frequency = _default_rebalance_frequency(strategy_id)
    transaction_cost_bps = _finite_float(
        payload.get("transaction_cost_bps"),
        "transaction_cost_bps",
        0.0,
    )

    params = StrategyBacktestParams(
        start_date=start_date,
        end_date=end_date,
        score_version=score_version,
        adjust_type=adjust_type,
    )
    run_config = {
        "score_version": score_version,
        "top_n": top_n,
        "rebalance_frequency": rebalance_frequency,
        "transaction_cost_bps": transaction_cost_bps,
        "max_positions": max_positions,
        "max_position_weight": max_position_weight,
        "risk_profile": risk_profile,
        "adjust_type": adjust_type,
    }
    vector_config = VectorizedTopNConfig(
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
        rebalance_frequency=rebalance_frequency,
        transaction_cost_bps=transaction_cost_bps,
        max_positions=max_positions,
        max_position_weight=max_position_weight,
    )
    return strategy_id, params, run_config, vector_config


def _with_execution_metadata(
    payload: dict[str, Any],
    *,
    mode: str,
    source: str,
    started_at: str,
    elapsed_ms: float,
) -> dict[str, Any]:
    result = dict(payload)
    result["execution_mode"] = mode
    result["result_source"] = source
    result["run_started_at"] = started_at
    result["run_finished_at"] = datetime.now(timezone.utc).isoformat()
    result["elapsed_ms"] = round(float(elapsed_ms), 3)
    summary = dict(result.get("summary") or {})
    summary["execution_mode"] = mode
    summary["result_source"] = source
    summary["elapsed_ms"] = result["elapsed_ms"]
    result["summary"] = summary
    return result


def run_replay_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    strategy_id, params, run_config, _vector_config = _parse_backtest_request(payload)
    adapter = STRATEGY_BACKTEST_REGISTRY.get(strategy_id)
    if adapter is None:
        raise ValueError(f"unsupported strategy: {strategy_id}")
    replay_runner = getattr(adapter, "run_replay", None)
    if not callable(replay_runner):
        raise ValueError(f"strategy does not support replay: {strategy_id}")
    result = to_json_safe(replay_runner(params, run_config))
    return _with_execution_metadata(
        result,
        mode="replay",
        source=str(result.get("source_kind") or "database_replay"),
        started_at=started_at,
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )


def run_fresh_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    strategy_id, params, run_config, config = _parse_backtest_request(payload)
    run_config = _apply_strategy_contract_run_config(strategy_id, run_config, payload)
    if strategy_id == "lhb_shortline":
        result = run_lhb_shortline_v1_backtest_for_dashboard(
            {
                "start_date": params.start_date,
                "end_date": params.end_date,
                **run_config,
            }
        )
        return _with_execution_metadata(
            _with_contract_config(to_json_safe(result), run_config),
            mode="fresh",
            source=str(result.get("source_kind") or "lhb_shortline_v1"),
            started_at=started_at,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )
    if strategy_id == "mid_trend":
        result = run_mid_trend_v1_backtest_for_dashboard(
            {
                "start_date": params.start_date,
                "end_date": params.end_date,
                **run_config,
            }
        )
        return _with_execution_metadata(
            _with_contract_config(to_json_safe(result), run_config),
            mode="fresh",
            source=str(result.get("source_kind") or "mid_trend_v1"),
            started_at=started_at,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )
    if strategy_id == "tech_bottleneck":
        tech_payload = {
            "start_date": params.start_date,
            "end_date": params.end_date,
            **run_config,
        }
        try:
            result = run_tech_bottleneck_v1_backtest_for_dashboard(tech_payload)
            source = str(result.get("source_kind") or "tech_bottleneck_v1")
        except FileNotFoundError as exc:
            if "candidate snapshot" not in str(exc):
                raise
            result = _run_tech_bottleneck_eod_backtest_for_lab(tech_payload)
            source = "tech_bottleneck_eod"
        return _with_execution_metadata(
            _with_contract_config(to_json_safe(result), run_config),
            mode="fresh",
            source=source,
            started_at=started_at,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )

    adapter = STRATEGY_BACKTEST_REGISTRY.get(strategy_id)
    if adapter is None:
        raise ValueError(f"unsupported strategy: {strategy_id}")

    scores = adapter.load_scores(params)
    prices = load_vectorized_topn_prices(
        start_date=params.start_date,
        end_date=params.end_date,
        adjust_type=params.adjust_type,
    )
    result = run_vectorized_topn_backtest(scores, prices, config)

    payload_result = {
        "strategy_id": strategy_id,
        "strategy_name": _strategy_name(strategy_id),
        "read_only": False,
        "config": {
            "start_date": params.start_date,
            "end_date": params.end_date,
            "score_version": params.score_version,
            "top_n": config.top_n,
            "rebalance_frequency": config.rebalance_frequency,
            "transaction_cost_bps": config.transaction_cost_bps,
            "max_positions": config.max_positions,
            "max_position_weight": config.max_position_weight,
            "adjust_type": params.adjust_type,
        },
        "summary": {
            **to_json_safe(result.summary),
            "fresh_engine_note": "live score rebuild from selected strategy factors and market prices",
        },
        "equity_curve": _frame_records(result.equity_curve),
        "positions": _frame_records(result.positions),
        "trades": _frame_records(result.trades),
    }
    return _with_execution_metadata(
        payload_result,
        mode="fresh",
        source="live_vectorized_backtest",
        started_at=started_at,
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )


def _apply_strategy_contract_run_config(
    strategy_id: str,
    run_config: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        contract = load_strategy_contracts(profile="balanced").get(strategy_id)
    except Exception:
        contract = None
    if contract is None:
        return run_config
    contract_config = strategy_contract_run_config(contract)
    merged = dict(run_config)
    for key, value in contract_config.items():
        if key.startswith("contract_") or _payload_missing(payload, key):
            merged[key] = value
    return merged


def _run_tech_bottleneck_eod_backtest_for_lab(payload: dict[str, Any]) -> dict[str, Any]:
    end_date = str(payload["end_date"])
    start_date = str(payload["start_date"])
    output_dir = TECH_BOTTLENECK_LAB_OUTPUT_ROOT / end_date
    base_candidates_path = _prepare_tech_bottleneck_base_candidate_source(
        trade_date=end_date,
        output_dir=output_dir,
    )
    eod_result = run_tech_bottleneck_eod(
        start_date=start_date,
        end_date=end_date,
        output_dir=output_dir,
        base_candidates_path=base_candidates_path,
        manifest_upsert=lambda entry: entry,
    )
    strategy_entry = next(
        (
            entry
            for entry in eod_result.get("manifest_entries", [])
            if str(entry.get("module") or "") == "strategy_tech_bottleneck"
        ),
        {},
    )
    metadata = dict(strategy_entry.get("metadata") or {})
    output_paths = dict(metadata.get("output_paths") or {})
    summary = dict(metadata.get("summary") or {})
    config = {
        "start_date": start_date,
        "end_date": end_date,
        "top_n": payload.get("top_n"),
        "rebalance_frequency": payload.get("rebalance_frequency"),
        "transaction_cost_bps": payload.get("transaction_cost_bps"),
        "max_position_weight": payload.get("max_position_weight"),
        "adjust_type": payload.get("adjust_type"),
        "engine_version": "tech_bottleneck_v1",
    }
    return {
        "strategy_id": "tech_bottleneck",
        "strategy_name": "Tech Bottleneck Combo",
        "read_only": False,
        "source_kind": "tech_bottleneck_eod",
        "config": config,
        "summary": summary,
        "equity_curve": _csv_records(output_paths.get("equity_path")),
        "positions": _csv_records(output_paths.get("positions_path")),
        "trades": _csv_records(output_paths.get("trades_path")),
    }


def _prepare_tech_bottleneck_base_candidate_source(*, trade_date: str, output_dir: Path) -> Path:
    legacy = pd.read_csv(TECH_BOTTLENECK_V1_CANDIDATES_PATH, low_memory=False)
    if legacy.empty:
        raise ValueError("tech bottleneck legacy candidate seed is empty")
    missing = [column for column in ["asset_id", "first_hit_date"] if column not in legacy.columns]
    if missing:
        raise ValueError(f"tech bottleneck legacy candidate seed missing columns: {missing}")

    source = legacy.copy()
    source["candidate_trade_date"] = source["first_hit_date"]
    source["filter_decision"] = "pass"
    if "fundamental_trade_date" in source.columns:
        fundamental_dates = pd.to_datetime(source["fundamental_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        source["financial_as_of_date"] = fundamental_dates.fillna(source["first_hit_date"].astype(str))
    else:
        source["financial_as_of_date"] = source["first_hit_date"]
    if "technical_as_of_date" not in source.columns:
        source["technical_as_of_date"] = source["first_hit_date"]
    source["source_latest_trade_date"] = trade_date
    source["data_as_of_date"] = trade_date
    source["generated_trade_date"] = trade_date
    source["candidate_source_mode"] = "legacy_static_seed_daily_pit"

    output = output_dir / "tech_bottleneck_candidate_source" / "strict_153_st_only_financial_state_candidates.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    source.to_csv(output, index=False)
    return output


def _csv_records(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    source = Path(path)
    if not source.exists():
        return []
    return pd.read_csv(source, low_memory=False).to_dict("records")


def _payload_missing(payload: dict[str, Any], key: str) -> bool:
    return key not in payload or payload.get(key) is None or payload.get(key) == ""


def _with_contract_config(result: dict[str, Any], run_config: dict[str, Any]) -> dict[str, Any]:
    if not any(str(key).startswith("contract_") for key in run_config):
        return result
    next_result = dict(result)
    config = dict(next_result.get("config") or {})
    for key, value in run_config.items():
        if str(key).startswith("contract_"):
            config[key] = value
    next_result["config"] = config
    summary = dict(next_result.get("summary") or {})
    summary_fields = {
        "top_n": run_config.get("top_n"),
        "frequency": run_config.get("rebalance_frequency"),
        "protection_name": run_config.get("protection_name"),
        "transaction_cost_bps": run_config.get("transaction_cost_bps"),
        "adjust_type": run_config.get("adjust_type"),
    }
    for key, value in summary_fields.items():
        if value is not None and (key not in summary or summary.get(key) in (None, "")):
            summary[key] = value
    next_result["summary"] = summary
    return next_result


def run_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    return run_replay_backtest(payload)


def to_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_json_safe(item) for item in value]
    if isinstance(value, pd.Series | pd.Index):
        return [to_json_safe(item) for item in value.to_list()]
    if _is_missing(value):
        return None
    if isinstance(value, pd.Timestamp):
        if value.time() == pd.Timestamp(value.date()).time():
            return value.date().isoformat()
        return value.isoformat()
    if isinstance(value, bool):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            return None
        return numeric_value
    if isinstance(value, str):
        return value
    return str(value)


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if value is None or value == "":
        raise ValueError(f"{field} is required")
    return str(value)


def _optional_text(value: Any, default: str) -> str:
    if value is None or value == "":
        return default
    return str(value)


def _positive_int(value: Any, field: str, default: int) -> int:
    if value is None or value == "":
        value = default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _optional_positive_int(value: Any, field: str) -> int | None:
    if value is None or value == "":
        return None
    return _positive_int(value, field, 0)


def _finite_float(value: Any, field: str, default: float) -> float:
    if value is None or value == "":
        value = default
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field} must be finite")
    return parsed


def _optional_position_weight(value: Any) -> float | None:
    if value is None or value == "":
        return None
    parsed = _finite_float(value, "max_position_weight", 0.0)
    if parsed > 1:
        parsed = parsed / 100.0
    if not (0 < parsed <= 1):
        raise ValueError("max_position_weight must be greater than 0 and at most 100%")
    return parsed


def _rebalance_frequency(value: Any) -> str:
    frequency = _optional_text(value, "weekly")
    if frequency not in {"daily", "weekly"}:
        raise ValueError("rebalance_frequency must be daily or weekly")
    return frequency


def _default_rebalance_frequency(strategy_id: str) -> str:
    if strategy_id == "lhb_shortline":
        return "daily"
    return "weekly"


def _frame_records(frame: pd.DataFrame | None) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    return [to_json_safe(row) for row in frame.to_dict("records")]


def _is_missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _strategy_name(strategy_id: str) -> str:
    for row in list_strategy_catalog():
        if row["strategy_id"] == strategy_id:
            return str(row["strategy_name"])
    return strategy_id
